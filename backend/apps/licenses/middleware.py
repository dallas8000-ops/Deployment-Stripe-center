"""License enforcement middleware — readonly or block when invalid."""

from __future__ import annotations

import logging
from typing import Callable

from django.conf import settings
from django.http import JsonResponse

from apps.licenses.service import check_license_valid, license_enforcement_enabled

logger = logging.getLogger(__name__)

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

SKIP_PREFIXES = (
    "/health/",
    "/api/v1/license/validate/",
    "/api/v1/billing/webhook/",
    "/api/v1/webhooks/",
    "/admin/",
    "/static/",
)


class LicenseEnforcementMiddleware:
    def __init__(self, get_response: Callable):
        self.get_response = get_response
        self.mode = getattr(settings, "LICENSE_ENFORCEMENT_MODE", "readonly")
        self.read_only_message = getattr(
            settings, "LICENSE_READ_ONLY_MESSAGE", "License invalid - running in read-only mode"
        )

    def __call__(self, request):
        if not license_enforcement_enabled():
            return self.get_response(request)

        path = request.path
        if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
            return self.get_response(request)

        license_valid = check_license_valid()

        if not license_valid:
            if self.mode == "block":
                return JsonResponse({"error": "License invalid - access denied"}, status=403)
            if request.method in WRITE_METHODS:
                return JsonResponse(
                    {"error": self.read_only_message, "code": "license_readonly"},
                    status=402,
                )
            request.license_readonly = True

        response = self.get_response(request)
        if not license_valid and self.mode == "readonly":
            response["X-License-Status"] = "invalid"
            response["X-License-Mode"] = "readonly"
        return response
