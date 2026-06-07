from django.contrib import admin

from .models import ProjectVault, VaultSecret


@admin.register(ProjectVault)
class ProjectVaultAdmin(admin.ModelAdmin):
    list_display = ("project", "initialized_at")


@admin.register(VaultSecret)
class VaultSecretAdmin(admin.ModelAdmin):
    list_display = ("project", "key_name", "updated_at")
    readonly_fields = ("encrypted_value", "iv", "auth_tag")
    list_filter = ("project",)
