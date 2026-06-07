from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "framework", "language", "last_scanned_at")
    list_filter = ("framework", "language")
    search_fields = ("name", "slug", "owner__email")
