from django.contrib import admin

from .models import PipelineRun, PipelineRunLog


class PipelineRunLogInline(admin.TabularInline):
    model = PipelineRunLog
    extra = 0
    readonly_fields = ("step", "status", "message", "detail", "score", "created_at")


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "status", "readiness_score", "created_at")
    list_filter = ("status",)
    inlines = [PipelineRunLogInline]


@admin.register(PipelineRunLog)
class PipelineRunLogAdmin(admin.ModelAdmin):
    list_display = ("run", "step", "status", "message", "created_at")
    list_filter = ("status",)
