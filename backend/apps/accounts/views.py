from django.contrib.auth import authenticate, get_user_model
from django.shortcuts import redirect
from rest_framework import generics, permissions, status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .mfa import (
    MfaEnrollStart,
    consume_recovery_code,
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_recovery_codes,
    generate_totp_secret,
    issue_mfa_challenge,
    mfa_issuer_name,
    provisioning_uri,
    resolve_mfa_challenge,
    verify_totp,
)
from .serializers import RegisterSerializer, UserSerializer
from .sso import (
    build_authorize_url,
    exchange_code_for_userinfo,
    frontend_redirect_with_tokens,
    provision_user_from_oidc,
    sso_enabled,
    verify_sso_state,
)
from .tokens import EmailTokenObtainPairSerializer, issue_tokens_for_user

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class EmailTokenObtainPairView(TokenObtainPairView):
    """POST { email, password } → access + refresh, or mfa_required + mfa_token."""

    serializer_class = EmailTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.user
        if user.mfa_enabled:
            return Response(
                {
                    "mfa_required": True,
                    "mfa_token": issue_mfa_challenge(user.pk),
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class MfaVerifyLoginView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        mfa_token = str(request.data.get("mfa_token") or "").strip()
        code = str(request.data.get("code") or "").strip()
        recovery_code = str(request.data.get("recovery_code") or "").strip()
        if not mfa_token:
            raise ValidationError({"mfa_token": "Required"})
        if not code and not recovery_code:
            raise ValidationError({"code": "Enter authenticator code or recovery code"})

        try:
            user_id = resolve_mfa_challenge(mfa_token)
        except Exception as exc:
            raise AuthenticationFailed("MFA session expired — sign in again") from exc

        user = User.objects.filter(pk=user_id, is_active=True).first()
        if not user or not user.mfa_enabled or not user.mfa_secret_encrypted:
            raise AuthenticationFailed("Invalid MFA session")

        verified = False
        if code:
            secret = decrypt_mfa_secret(user.pk, user.mfa_secret_encrypted)
            verified = verify_totp(secret, code)
        elif recovery_code:
            verified = consume_recovery_code(user, recovery_code)

        if not verified:
            raise AuthenticationFailed("Invalid authenticator or recovery code")

        return Response(issue_tokens_for_user(user))


class MfaStatusView(APIView):
    def get(self, request):
        return Response({"mfa_enabled": bool(request.user.mfa_enabled)})


class MfaEnrollStartView(APIView):
    def post(self, request):
        if request.user.mfa_enabled:
            raise ValidationError({"detail": "MFA is already enabled"})
        secret = generate_totp_secret()
        request.user.mfa_pending_secret_encrypted = encrypt_mfa_secret(request.user.pk, secret)
        request.user.save(update_fields=["mfa_pending_secret_encrypted"])
        issuer = mfa_issuer_name()
        start = MfaEnrollStart(
            secret=secret,
            provisioning_uri=provisioning_uri(secret, email=request.user.email, issuer=issuer),
            issuer=issuer,
        )
        return Response(
            {
                "secret": start.secret,
                "provisioning_uri": start.provisioning_uri,
                "issuer": start.issuer,
            }
        )


class MfaEnrollConfirmView(APIView):
    def post(self, request):
        if request.user.mfa_enabled:
            raise ValidationError({"detail": "MFA is already enabled"})
        code = str(request.data.get("code") or "").strip()
        if not code:
            raise ValidationError({"code": "Required"})
        pending = request.user.mfa_pending_secret_encrypted
        if not pending:
            raise ValidationError({"detail": "Call /auth/mfa/enroll/start/ first"})
        secret = decrypt_mfa_secret(request.user.pk, pending)
        if not verify_totp(secret, code):
            raise ValidationError({"code": "Invalid code — check device time sync"})

        plain_codes, hashed_codes = generate_recovery_codes()
        request.user.mfa_secret_encrypted = pending
        request.user.mfa_pending_secret_encrypted = ""
        request.user.mfa_recovery_codes_hash = hashed_codes
        request.user.mfa_enabled = True
        request.user.save(
            update_fields=[
                "mfa_secret_encrypted",
                "mfa_pending_secret_encrypted",
                "mfa_recovery_codes_hash",
                "mfa_enabled",
            ]
        )
        return Response(
            {
                "mfa_enabled": True,
                "recovery_codes": plain_codes,
            }
        )


class MfaDisableView(APIView):
    def post(self, request):
        password = str(request.data.get("password") or "")
        code = str(request.data.get("code") or "").strip()
        if not password:
            raise ValidationError({"password": "Required"})
        if not code:
            raise ValidationError({"code": "Required"})
        if not request.user.mfa_enabled:
            return Response({"mfa_enabled": False})

        authed = authenticate(
            request=request,
            email=request.user.email,
            password=password,
        )
        if not authed:
            raise AuthenticationFailed("Incorrect password")

        secret = decrypt_mfa_secret(request.user.pk, request.user.mfa_secret_encrypted)
        if not verify_totp(secret, code):
            raise AuthenticationFailed("Invalid authenticator code")

        request.user.mfa_enabled = False
        request.user.mfa_secret_encrypted = ""
        request.user.mfa_pending_secret_encrypted = ""
        request.user.mfa_recovery_codes_hash = []
        request.user.save(
            update_fields=[
                "mfa_enabled",
                "mfa_secret_encrypted",
                "mfa_pending_secret_encrypted",
                "mfa_recovery_codes_hash",
            ]
        )
        return Response({"mfa_enabled": False})


class SsoConfigView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        if not sso_enabled():
            return Response({"enabled": False})
        return Response({"enabled": True, "login_url": "/api/v1/auth/sso/login/"})


class SsoLoginView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        if not sso_enabled():
            raise ValidationError({"detail": "SSO is not configured"})
        return redirect(build_authorize_url())


class SsoCallbackView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        if not sso_enabled():
            raise ValidationError({"detail": "SSO is not configured"})
        error = request.query_params.get("error")
        if error:
            raise AuthenticationFailed(request.query_params.get("error_description") or error)
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or not state:
            raise ValidationError({"detail": "Missing OIDC code or state"})
        try:
            verify_sso_state(state)
            userinfo = exchange_code_for_userinfo(code)
            user = provision_user_from_oidc(userinfo)
        except Exception as exc:
            raise AuthenticationFailed(str(exc)) from exc
        tokens = issue_tokens_for_user(user)
        return redirect(frontend_redirect_with_tokens(tokens["access"], tokens["refresh"]))


# Re-export for urls
TokenRefreshViewAlias = TokenRefreshView
