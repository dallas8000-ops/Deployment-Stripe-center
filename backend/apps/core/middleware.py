"""Attach a stable request ID to every HTTP request/response."""

from __future__ import annotations

import uuid

from apps.core.logging_context import request_id_ctx


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = (request.headers.get("X-Request-ID") or "").strip() or str(uuid.uuid4())
        request.request_id = request_id
        token = request_id_ctx.set(request_id)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
        finally:
            request_id_ctx.reset(token)
