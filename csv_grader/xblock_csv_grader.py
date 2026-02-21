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

        options_html = ""
        for block in problem_blocks:
            options_html += "<option value='{bid}'>{name}</option>".format(
                bid=str(block["usage_key"]),
                name=block["display_name"]
            )

        html = self.resource_string("templates_xblock/csv_grader.html")
        frag = Fragment(html.format(
            block_id=str(self.location),
            options=options_html,
            last_summary=self.last_import_summary or "",
        ))
        frag.add_css(self.resource_string("static/css/csv_grader.css"))
        frag.add_javascript(self.resource_string("static/js/csv_grader.js"))
        frag.initialize_js("CsvGraderXBlock")
        return frag

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

    @XBlock.json_handler
    def import_grades(self, data, suffix=""):
        from django.contrib.auth import get_user_model
        from lms.djangoapps.courseware.models import StudentModule
        from opaque_keys.edx.keys import UsageKey

        User = get_user_model()

        csv_content = data.get("csv_content", "")
        target_block = data.get("target_block", "").strip()

        if not csv_content:
            return {"success": False, "error": "No CSV data received"}
        if not target_block:
            return {"success": False, "error": "Please select a target problem block"}

        try:
            usage_key = UsageKey.from_string(target_block)
        except Exception:
            return {"success": False, "error": "Invalid block ID: " + target_block}

        course_key = usage_key.course_key
        max_grade = float(data.get("max_grade", 1.0))

        results = []
        errors = []
        created_count = 0
        updated_count = 0

        reader = csv.reader(io.StringIO(csv_content))
        for line_num, row in enumerate(reader, 1):
            if not row or len(row) < 2:
                continue
            username = row[0].strip()
            grade_str = row[1].strip()

            try:
                User = get_user_model()
                user = User.objects.get(username=username)
                grade = float(grade_str)
            except Exception as e:
                errors.append("Line {}: {}".format(line_num, str(e)))
                continue

            obj, created = StudentModule.objects.update_or_create(
                student=user,
                course_id=course_key,
                module_state_key=usage_key,
                defaults={
                    "grade": grade,
                    "max_grade": max_grade,
                    "module_type": "problem",
                    "state": json.dumps({
                        "score": {
                            "raw_earned": grade,
                            "raw_possible": max_grade
                        }
                    }),
                }
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
            results.append({
                "username": username,
                "grade": grade,
                "action": "created" if created else "updated"
            })

        summary = "{} created, {} updated".format(created_count, updated_count)
        if errors:
            summary += ", {} errors".format(len(errors))

        self.last_import_summary = summary
        self.last_import_count = len(results)

        return {
            "success": True,
            "summary": summary,
            "results": results,
            "errors": errors,
            "created": created_count,
            "updated": updated_count,
        }

    @staticmethod
    def workbench_scenarios():
        return [("CsvGraderXBlock", "<csv-grader/>")]