from django.apps import AppConfig


class StripeInstallerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.stripe_installer"
    label = "stripe_engine"
    verbose_name = "Stripe Installer"
