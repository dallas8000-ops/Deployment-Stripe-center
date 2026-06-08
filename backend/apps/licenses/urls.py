from django.urls import path

from .views import LicenseDetailView, LicenseRevokeView, MyLicenseView, validate_license

urlpatterns = [
    path("license/me/", MyLicenseView.as_view(), name="license-me"),
    path("license/validate/", validate_license, name="license-validate"),
    path("license/<str:license_key>/", LicenseDetailView.as_view(), name="license-detail"),
    path("license/<str:license_key>/revoke/", LicenseRevokeView.as_view(), name="license-revoke"),
]
