from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "display_name", "mfa_enabled", "is_staff", "date_joined")
    search_fields = ("email", "display_name")
    ordering = ("-date_joined",)
