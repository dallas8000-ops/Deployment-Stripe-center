from django.apps import AppConfig


class StripeCoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.stripe_core"
    label = "stripe_engine"
    verbose_name = "Stripe Core"
