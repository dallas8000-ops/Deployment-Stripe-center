from django.http import JsonResponse


def root(_request):
    return JsonResponse(
        {
            "service": "Stripe Installer SaaS API",
            "status": "ok",
            "ui": "http://localhost:5173",
            "api": "/api/v1/",
        }
    )


def health(_request):
    return JsonResponse({"status": "ok"})
