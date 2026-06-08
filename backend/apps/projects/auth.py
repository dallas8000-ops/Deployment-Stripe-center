"""Authentication for project API keys (CI / automation)."""

from __future__ import annotations

from rest_framework import authentication, exceptions

from apps.projects.api_keys import ProjectApiKey


class ProjectApiKeyAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        auth = authentication.get_authorization_header(request).decode()
        if not auth.startswith(f"{self.keyword} "):
            return None

        raw_key = auth[len(self.keyword) + 1 :].strip()
        if not raw_key.startswith("si_"):
            return None

        project = ProjectApiKey.authenticate(raw_key)
        if not project:
            raise exceptions.AuthenticationFailed("Invalid or revoked API key")

        request.stripe_installer_project = project
        return (None, raw_key)
