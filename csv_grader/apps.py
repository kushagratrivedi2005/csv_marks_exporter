from django.apps import AppConfig

class CsvGraderConfig(AppConfig):
    name = "csv_grader"
    verbose_name = "CSV Grader"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Register the XBlock entry point programmatically
        pass