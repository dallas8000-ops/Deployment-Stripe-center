from datetime import datetime, timezone

from django.http import JsonResponse


def health(_request):
    return JsonResponse(
        {
            "status": "healthy",
            "checks": {"app": "ok"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        status=200,
    )
