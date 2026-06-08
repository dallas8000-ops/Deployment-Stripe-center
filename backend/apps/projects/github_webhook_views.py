import json

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.projects.github_webhook import dispatch_github_event, verify_github_signature


@csrf_exempt
def github_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    payload = request.body
    sig = request.META.get("HTTP_X_HUB_SIGNATURE_256")
    if not verify_github_signature(payload, sig):
        return HttpResponse("Invalid signature", status=401)

    event_type = request.META.get("HTTP_X_GITHUB_EVENT", "")
    try:
        data = json.loads(payload.decode())
    except json.JSONDecodeError:
        return HttpResponse("Invalid JSON", status=400)

    result = dispatch_github_event(event_type, data)
    return HttpResponse(json.dumps(result), content_type="application/json")
