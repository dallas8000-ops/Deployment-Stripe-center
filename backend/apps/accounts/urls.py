from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    EmailTokenObtainPairView,
    MeView,
    MfaDisableView,
    MfaEnrollConfirmView,
    MfaEnrollStartView,
    MfaStatusView,
    MfaVerifyLoginView,
    RegisterView,
    SsoCallbackView,
    SsoConfigView,
    SsoLoginView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", EmailTokenObtainPairView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("mfa/verify/", MfaVerifyLoginView.as_view(), name="auth-mfa-verify"),
    path("mfa/status/", MfaStatusView.as_view(), name="auth-mfa-status"),
    path("mfa/enroll/start/", MfaEnrollStartView.as_view(), name="auth-mfa-enroll-start"),
    path("mfa/enroll/confirm/", MfaEnrollConfirmView.as_view(), name="auth-mfa-enroll-confirm"),
    path("mfa/disable/", MfaDisableView.as_view(), name="auth-mfa-disable"),
    path("sso/config/", SsoConfigView.as_view(), name="auth-sso-config"),
    path("sso/login/", SsoLoginView.as_view(), name="auth-sso-login"),
    path("sso/callback/", SsoCallbackView.as_view(), name="auth-sso-callback"),
]
