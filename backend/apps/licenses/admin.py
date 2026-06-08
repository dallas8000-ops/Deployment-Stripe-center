from django.contrib import admin

from .models import InstanceRegistry, License


@admin.register(License)
class LicenseAdmin(admin.ModelAdmin):
    list_display = ["key", "customer_email", "status", "registered_domain", "max_instances", "expiry_date"]
    list_filter = ["status", "created_at"]
    search_fields = ["key", "customer_email", "stripe_subscription_id"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(InstanceRegistry)
class InstanceRegistryAdmin(admin.ModelAdmin):
    list_display = ["instance_id", "license", "domain", "last_seen", "is_active"]
    list_filter = ["last_seen"]
    search_fields = ["instance_id", "domain"]
    readonly_fields = ["first_registered", "last_seen"]
