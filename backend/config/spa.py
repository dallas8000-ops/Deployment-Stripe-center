from django.conf import settings
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET


@require_GET
def spa_index(_request):
    index = settings.FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise Http404("Frontend not built — run npm run build in frontend/")
    return FileResponse(index.open("rb"), content_type="text/html")
