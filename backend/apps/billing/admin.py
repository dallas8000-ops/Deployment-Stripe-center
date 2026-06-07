from django.contrib import admin

from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "tier", "status", "stripe_customer_id", "updated_at")
    search_fields = ("user__email", "stripe_customer_id", "stripe_subscription_id")
