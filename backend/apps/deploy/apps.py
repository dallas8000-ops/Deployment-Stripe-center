from django.apps import AppConfig


class DeployConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.deploy"
    verbose_name = "Deploy & PostgreSQL"
