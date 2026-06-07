# Generated migration for billing app

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stripe_customer_id", models.CharField(blank=True, max_length=64)),
                ("stripe_subscription_id", models.CharField(blank=True, max_length=64)),
                ("stripe_price_id", models.CharField(blank=True, max_length=64)),
                ("tier", models.CharField(blank=True, max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("trialing", "Trialing"),
                            ("past_due", "Past due"),
                            ("canceled", "Canceled"),
                            ("incomplete", "Incomplete"),
                            ("none", "None"),
                        ],
                        default="none",
                        max_length=32,
                    ),
                ),
                ("current_period_end", models.DateTimeField(blank=True, null=True)),
                ("cancel_at_period_end", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscription",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
    ]
