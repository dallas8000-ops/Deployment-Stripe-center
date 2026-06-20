from django.contrib import admin

from .models import AuditEntry, DeploymentRun, TransferRun


@admin.register(TransferRun)
class TransferRunAdmin(admin.ModelAdmin):
    list_display = ("run_id", "mode", "status", "step", "project", "organization", "created_at")
    search_fields = ("run_id", "requested_by")
    list_filter = ("status", "mode")


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ("sequence", "action", "actor", "reference", "created_at")
    ordering = ("-sequence",)


@admin.register(DeploymentRun)
class DeploymentRunAdmin(admin.ModelAdmin):
    list_display = ("deployment_id", "app_name", "target_provider", "status", "live", "project", "created_at")
    search_fields = ("deployment_id", "app_name")
    list_filter = ("target_provider", "live", "status")
