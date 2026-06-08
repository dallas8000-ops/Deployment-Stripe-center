from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AgencyDashboardView, InvitePreviewView, OrganizationViewSet

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="organization")

urlpatterns = [
    path("agency/dashboard/", AgencyDashboardView.as_view(), name="agency-dashboard"),
    path("invites/<str:token>/", InvitePreviewView.as_view(), name="invite-preview"),
    path("", include(router.urls)),
]
