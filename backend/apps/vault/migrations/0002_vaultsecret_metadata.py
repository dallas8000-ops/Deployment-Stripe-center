# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vault", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="vaultsecret",
            name="display_mask",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="vaultsecret",
            name="key_mode",
            field=models.CharField(blank=True, default="unknown", max_length=16),
        ),
        migrations.AddField(
            model_name="vaultsecret",
            name="verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="vaultsecret",
            name="verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="vaultsecret",
            name="verification_message",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
