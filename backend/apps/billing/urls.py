from django.urls import path

from .views import (
    CheckoutView,
    OrgCheckoutView,
    OrgPortalView,
    OrgSubscriptionView,
    PlansView,
    PortalView,
    SubscriptionView,
)
from .webhooks import billing_webhook

urlpatterns = [
    path("billing/plans/", PlansView.as_view(), name="billing-plans"),
    path("billing/subscription/", SubscriptionView.as_view(), name="billing-subscription"),
    path("billing/org/subscription/", OrgSubscriptionView.as_view(), name="billing-org-subscription"),
    path("billing/checkout/", CheckoutView.as_view(), name="billing-checkout"),
    path("billing/org/checkout/", OrgCheckoutView.as_view(), name="billing-org-checkout"),
    path("billing/portal/", PortalView.as_view(), name="billing-portal"),
    path("billing/org/portal/", OrgPortalView.as_view(), name="billing-org-portal"),
    path("billing/webhook/", billing_webhook, name="billing-webhook"),
]
