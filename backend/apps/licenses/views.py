import json
import logging

from datetime import datetime, timezone

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InstanceRegistry, License
from .utils import normalize_domain, validate_domain_format

logger = logging.getLogger(__name__)


def _parse_body(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return {}
    return request.POST.dict() if request.POST else {}


@csrf_exempt
@require_http_methods(["POST"])
def validate_license(request):
    """POST /api/v1/license/validate/ — instance heartbeat."""
    data = _parse_body(request)
    license_key = data.get("license_key")
    domain = normalize_domain(data.get("domain") or "")
    instance_id = data.get("instance_id")

    if not all([license_key, domain, instance_id]):
        return JsonResponse(
            {"valid": False, "message": "Missing required fields: license_key, domain, instance_id"},
            status=400,
        )

    if not validate_domain_format(domain):
        return JsonResponse({"valid": False, "message": "Invalid domain format"}, status=400)

    try:
        license_obj = License.objects.get(key=license_key)
    except License.DoesNotExist:
        logger.warning("License validation failed: key not found - %s...", license_key[:8])
        return JsonResponse({"valid": False, "message": "Invalid license key"}, status=404)

    if not license_obj.is_active:
        message = f"License is {license_obj.status}"
        if license_obj.status == License.Status.EXPIRED:
            message = "License has expired"
        return JsonResponse({"valid": False, "message": message}, status=403)

    registered = normalize_domain(license_obj.registered_domain)
    if registered != domain:
        logger.warning(
            "Domain mismatch for license %s...: expected %s, got %s",
            license_obj.key[:8],
            registered,
            domain,
        )
        return JsonResponse(
            {"valid": False, "message": f"Domain mismatch. Registered domain: {license_obj.registered_domain}"},
            status=403,
        )

    active_instances = license_obj.active_instance_count
    if active_instances >= license_obj.max_instances:
        try:
            existing = InstanceRegistry.objects.get(instance_id=instance_id, license=license_obj)
            existing.last_seen = datetime.now(timezone.utc)
            existing.save(update_fields=["last_seen"])
        except InstanceRegistry.DoesNotExist:
            return JsonResponse(
                {
                    "valid": False,
                    "message": f"Instance limit exceeded ({active_instances}/{license_obj.max_instances})",
                },
                status=403,
            )

    instance, created = InstanceRegistry.objects.get_or_create(
        instance_id=instance_id,
        license=license_obj,
        defaults={
            "domain": domain,
            "ip_address": request.META.get("REMOTE_ADDR"),
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
        },
    )

    if not created:
        instance.last_seen = datetime.now(timezone.utc)
        instance.domain = domain
        instance.ip_address = request.META.get("REMOTE_ADDR")
        instance.user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        instance.save(update_fields=["last_seen", "domain", "ip_address", "user_agent"])

    logger.info("License validated: %s... for %s", license_obj.key[:8], domain)

    return JsonResponse(
        {
            "valid": True,
            "expiry_date": license_obj.expiry_date.isoformat() if license_obj.expiry_date else None,
            "max_instances": license_obj.max_instances,
            "active_instances": license_obj.active_instance_count,
            "message": "License valid",
        }
    )


class MyLicenseView(APIView):
    """Licenses for the authenticated user (post-checkout)."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        rows = License.objects.filter(
            customer_email__iexact=request.user.email,
            status=License.Status.ACTIVE,
        ).order_by("-created_at")
        return Response(
            {
                "licenses": [
                    {
                        "key": lic.key,
                        "domain": lic.registered_domain,
                        "status": lic.status,
                        "maxInstances": lic.max_instances,
                        "activeInstances": lic.active_instance_count,
                        "expiryDate": lic.expiry_date.isoformat() if lic.expiry_date else None,
                        "createdAt": lic.created_at.isoformat(),
                    }
                    for lic in rows
                ]
            }
        )


class LicenseDetailView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    def get(self, request, license_key):
        try:
            license_obj = License.objects.get(key=license_key)
        except License.DoesNotExist:
            return Response({"error": "License not found"}, status=status.HTTP_404_NOT_FOUND)

        instances = [
            {
                "instance_id": inst.instance_id,
                "domain": inst.domain,
                "last_seen": inst.last_seen.isoformat(),
                "is_active": inst.is_active,
            }
            for inst in license_obj.instances.all()
        ]

        return Response(
            {
                "key": license_obj.key,
                "customer_email": license_obj.customer_email,
                "status": license_obj.status,
                "registered_domain": license_obj.registered_domain,
                "max_instances": license_obj.max_instances,
                "expiry_date": license_obj.expiry_date.isoformat() if license_obj.expiry_date else None,
                "is_active": license_obj.is_active,
                "active_instance_count": license_obj.active_instance_count,
                "instances": instances,
            }
        )


class LicenseRevokeView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    def post(self, request, license_key):
        try:
            license_obj = License.objects.get(key=license_key)
        except License.DoesNotExist:
            return Response({"error": "License not found"}, status=status.HTTP_404_NOT_FOUND)

        license_obj.status = License.Status.REVOKED
        license_obj.save(update_fields=["status", "updated_at"])
        logger.info("License revoked: %s...", license_obj.key[:8])
        return Response({"message": "License revoked successfully"})
