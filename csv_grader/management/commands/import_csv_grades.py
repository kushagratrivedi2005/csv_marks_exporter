import csv
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from opaque_keys.edx.keys import CourseKey, UsageKey
from lms.djangoapps.courseware.models import StudentModule

User = get_user_model()

class Command(BaseCommand):
    help = "Import grades from a CSV into a problem block via StudentModule"

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=True, help="Path to marks CSV file")
        parser.add_argument("--block", required=True, help="Usage key of the problem block")
        parser.add_argument("--course", required=True, help="Course key e.g. course-v1:DEMO+CSV101+2026")
        parser.add_argument("--max-grade", type=float, default=1.0)

    def handle(self, *args, **options):
        course_key = CourseKey.from_string(options["course"])
        usage_key  = UsageKey.from_string(options["block"])
        max_grade  = options["max_grade"]

        with open(options["csv"], newline="") as f:
            for row in csv.reader(f):
                if len(row) < 2:
                    continue
                username, grade_str = row[0].strip(), row[1].strip()
                try:
                    user  = User.objects.get(username=username)
                    grade = float(grade_str)
                except (User.DoesNotExist, ValueError) as e:
                    self.stderr.write("Skipping {}: {}".format(username, e))
                    continue

                obj, created = StudentModule.objects.update_or_create(
                    student=user,
                    course_id=course_key,
                    module_state_key=usage_key,
                    defaults={
                        "grade": grade,
                        "max_grade": max_grade,
                        "module_type": "problem",
                        "state": '{"score": {"raw_earned": ' + str(grade) + ', "raw_possible": ' + str(max_grade) + '}}',
                    }
                )
                verb = "Created" if created else "Updated"
                self.stdout.write("{} grade for {}: {}/{}".format(verb, username, grade, max_grade))

        self.stdout.write(self.style.SUCCESS("Done!"))
