"""Platform setup audit and verify actions."""

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .platform_setup import audit_platform, run_setup_action
from .redaction import redact_sensitive_values


class PlatformSetupAuditView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        scan = str(request.query_params.get("scanRailwayStripe", "")).lower() in {"1", "true", "yes"}
        return Response(redact_sensitive_values(audit_platform(scan_railway_stripe=scan)))


class PlatformSetupRunView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        action_id = (request.data.get("actionId") or request.data.get("action_id") or "").strip()
        if not action_id:
            return Response({"error": "actionId is required."}, status=400)
        result = run_setup_action(action_id)
        status = 200 if result.get("ok") else 400
        return Response(redact_sensitive_values(result), status=status)
