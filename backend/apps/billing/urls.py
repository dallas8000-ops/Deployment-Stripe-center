from django.urls import path

from .views import CheckoutView, PlansView, PortalView, SubscriptionView, billing_webhook

urlpatterns = [
    path("billing/plans/", PlansView.as_view(), name="billing-plans"),
    path("billing/subscription/", SubscriptionView.as_view(), name="billing-subscription"),
    path("billing/checkout/", CheckoutView.as_view(), name="billing-checkout"),
    path("billing/portal/", PortalView.as_view(), name="billing-portal"),
    path("billing/webhook/", billing_webhook, name="billing-webhook"),
]
