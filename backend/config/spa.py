import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET


def _file_response(asset: Path, content_type: str) -> FileResponse:
    response = FileResponse(asset.open("rb"), content_type=content_type)
    # Vite emits crossorigin on module scripts and stylesheets — needs ACAO or the browser blocks them.
    response["Access-Control-Allow-Origin"] = "*"
    return response


@require_GET
def spa_index(_request):
    index = settings.FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise Http404("Frontend not built — run npm run build in frontend/")
    return _file_response(index, "text/html")


@require_GET
def spa_asset(_request, path: str):
    """Serve Vite-built /assets/* — must not fall through to spa_index (returns HTML)."""
    if ".." in path or path.startswith("/"):
        raise Http404
    asset = settings.FRONTEND_DIST / "assets" / path
    if not asset.is_file():
        raise Http404
    content_type, _ = mimetypes.guess_type(str(asset))
    return _file_response(asset, content_type or "application/octet-stream")
