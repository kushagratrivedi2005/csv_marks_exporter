import csv
import io
import json
import logging

from web_fragments.fragment import Fragment
from xblock.core import XBlock
from xblock.fields import Scope, String, Integer
from xblockutils.resources import ResourceLoader

log = logging.getLogger(__name__)
loader = ResourceLoader(__name__)


@XBlock.needs("i18n")
class CsvGraderXBlock(XBlock):

    display_name = String(
        display_name="Display Name",
        default="CSV Grade Importer",
        scope=Scope.settings,
    )

    last_import_summary = String(default="", scope=Scope.content)
    last_import_count = Integer(default=0, scope=Scope.content)

    def resource_string(self, path):
        return loader.load_unicode(path)

    def student_view(self, context=None):
        return Fragment("<div style='display:none'>CSV Grader (Studio only)</div>")

    def studio_view(self, context=None):
        problem_blocks = self._get_course_problems()
        subsections = self._get_course_subsections()  # NEW

        options_html = ""
        for block in problem_blocks:
            options_html += "<option value='{bid}'>{name}</option>".format(
                bid=str(block["usage_key"]),
                name=block["display_name"]
            )

        subsection_options_html = ""
        for s in subsections:
            subsection_options_html += "<option value='{bid}'>{name}</option>".format(
                bid=str(s["usage_key"]),
                name=s["display_name"]
            )

        html = self.resource_string("templates_xblock/csv_grader.html")
        frag = Fragment(html.format(
            block_id=str(self.location),
            options=options_html,
            subsection_options=subsection_options_html,
            last_summary=self.last_import_summary or "",
        ))
        frag.add_css(self.resource_string("static/css/csv_grader.css"))
        frag.add_javascript(self.resource_string("static/js/csv_grader.js"))
        frag.initialize_js("CsvGraderXBlock")
        return frag
    
    def _get_course_subsections(self):
        try:
            from xmodule.modulestore.django import modulestore
            course_key = self.location.course_key
            blocks = modulestore().get_items(course_key, qualifiers={"category": "sequential"})
            return [{"usage_key": b.location, "display_name": b.display_name or str(b.location)} for b in blocks]
        except Exception as e:
            log.error("csv_grader: could not fetch subsections: %s", e)
            return []

    def _get_course_problems(self):
        try:
            from xmodule.modulestore.django import modulestore
            course_key = self.location.course_key
            blocks = modulestore().get_items(
                course_key,
                qualifiers={"category": "problem"}
            )
            result = []
            for block in blocks:
                result.append({
                    "usage_key": block.location,
                    "display_name": block.display_name or str(block.location),
                })
            return result
        except Exception as e:
            log.error("csv_grader: could not fetch problem blocks: %s", e)
            return []
        
    def _write_persistent_grade(self, user, course_key, subsection_key, usage_key, grade, max_grade):
        from django.utils import timezone
        from lms.djangoapps.grades.models import PersistentSubsectionGrade, PersistentCourseGrade
        from lms.djangoapps.grades.models import BlockRecord
        from xmodule.modulestore.django import modulestore

        now = timezone.now()
        store = modulestore()

        # Build flat list of BlockRecord for all scorable blocks in the subsection
        try:
            subsection_block = store.get_item(subsection_key)
            block_records = []
            for unit in subsection_block.get_children():
                for child in unit.get_children():
                    if getattr(child, 'has_score', False):
                        block_records.append(BlockRecord(
                            locator=child.location,
                            weight=1,
                            raw_possible=max_grade if child.location == usage_key else 0,
                            graded=True,
                        ))
            if not block_records:
                raise ValueError("No scorable blocks found in subsection")
        except Exception as e:
            log.warning("csv_grader: subsection scan failed, using single block fallback: %s", e)
            block_records = [BlockRecord(
                locator=usage_key,
                weight=1,
                raw_possible=max_grade,
                graded=True,
            )]

        # update_or_create_grade expects:
        # - visible_blocks: plain list of BlockRecord (it calls BlockRecordList.from_list internally)
        # - course_id: optional, it derives from usage_key if missing
        # - NO 'course_key' or 'subtracted_earned' fields
        PersistentSubsectionGrade.update_or_create_grade(
            user_id=user.id,
            usage_key=subsection_key,
            course_id=course_key,
            subtree_edited_timestamp=now,
            course_version=None,
            first_attempted=now,
            visible_blocks=block_records,
            earned_all=grade,
            possible_all=max_grade,
            earned_graded=grade,
            possible_graded=max_grade,
        )

        # Delete stale course-level cache so gradebook recalculates the % correctly
        PersistentCourseGrade.objects.filter(
            user_id=user.id,
            course_id=course_key,
        ).delete()

    @XBlock.json_handler
    def import_grades(self, data, suffix=""):
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from lms.djangoapps.courseware.models import StudentModule
        from lms.djangoapps.grades.models import PersistentSubsectionGrade, PersistentCourseGrade, BlockRecord
        from opaque_keys.edx.keys import UsageKey
        import csv, io, json

        User = get_user_model()
        csv_content = data.get("csv_content", "")
        target_block = data.get("target_block", "").strip()
        subsection_id = data.get("subsection_id", "").strip()  # NEW
        max_grade = float(data.get("max_grade", 1.0))

        if not csv_content:
            return {"success": False, "error": "No CSV data received"}
        if not target_block:
            return {"success": False, "error": "Please select a target problem block"}
        if not subsection_id:
            return {"success": False, "error": "Please select a subsection"}

        try:
            usage_key = UsageKey.from_string(target_block)
            subsection_key = UsageKey.from_string(subsection_id)
        except Exception as e:
            return {"success": False, "error": "Invalid key: " + str(e)}

        course_key = usage_key.course_key
        now = timezone.now()

        # Single BlockRecord for our problem — no modulestore needed
        block_records = [BlockRecord(locator=usage_key, weight=1, raw_possible=max_grade, graded=True)]

        results = []
        errors = []
        created_count = 0
        updated_count = 0

        problem_id = usage_key.block_id
        reader = csv.reader(io.StringIO(csv_content))
        for line_num, row in enumerate(reader, 1):
            if not row or len(row) < 2:
                continue
            username = row[0].strip()
            grade_str = row[1].strip()
            try:
                user = User.objects.get(username=username)
                grade = float(grade_str)
            except Exception as e:
                errors.append("Line {}: {}".format(line_num, str(e)))
                continue

            # Write StudentModule
            user_state = {
                "input_state": {"{}_2_1".format(problem_id): {}},
                "seed": 1,
                "score": {"raw_earned": grade, "raw_possible": max_grade},
                "attempts": 1,
                "done": True,
            }
            sm_obj, sm_created = StudentModule.objects.update_or_create(
                student=user,
                course_id=course_key,
                module_state_key=usage_key,
                defaults={
                    "grade": grade,
                    "max_grade": max_grade,
                    "module_type": "problem",
                    "state": json.dumps(user_state),
                }
            )

            # Write PersistentSubsectionGrade directly
            try:
                PersistentSubsectionGrade.update_or_create_grade(
                    user_id=user.id,
                    usage_key=subsection_key,
                    course_id=course_key,
                    subtree_edited_timestamp=now,
                    course_version=None,
                    first_attempted=now,
                    visible_blocks=block_records,
                    earned_all=grade,
                    possible_all=max_grade,
                    earned_graded=grade,
                    possible_graded=max_grade,
                )
                
                # Auto-update course grade
                PersistentCourseGrade.objects.update_or_create(
                    user_id=user.id,
                    course_id=course_key,
                    defaults={
                        'percent_grade': (grade / max_grade) * 0.40,
                        'letter_grade': '',
                        'passed_timestamp': None,
                        'course_edited_timestamp': now,
                        'course_version': '',
                        'grading_policy_hash': '',
                    }
                )

                if sm_created:
                    created_count += 1
                else:
                    updated_count += 1
                results.append({"username": username, "grade": grade, "action": "created" if sm_created else "updated"})

            except Exception as e:
                log.error("csv_grader: persistent grade write failed for %s: %s", username, e)
                errors.append("Line {}: persistent grade failed: {}".format(line_num, str(e)))

        summary = "{} created, {} updated".format(created_count, updated_count)
        if errors:
            summary += ", {} errors".format(len(errors))
        self.last_import_summary = summary
        self.last_import_count = len(results)
        return {"success": True, "summary": summary, "results": results, "errors": errors,
                "created": created_count, "updated": updated_count}

    @staticmethod
    def workbench_scenarios():
        return [("CsvGraderXBlock", "<csv-grader/>")]
