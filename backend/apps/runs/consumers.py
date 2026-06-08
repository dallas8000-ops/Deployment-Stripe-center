from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError

from apps.runs.broadcast import run_group_name
from apps.runs.models import PipelineRun


@database_sync_to_async
def get_run_for_user(run_id: str, user_id: int) -> PipelineRun | None:
    from django.contrib.auth import get_user_model

    from apps.core.access import projects_for_user

    User = get_user_model()
    user = User.objects.get(id=user_id)
    accessible = projects_for_user(user).values_list("id", flat=True)
    try:
        return PipelineRun.objects.select_related("project").get(
            id=run_id,
            project_id__in=accessible,
        )
    except PipelineRun.DoesNotExist:
        return None


@database_sync_to_async
def get_run_logs(run_id: str) -> list[dict]:
    run = PipelineRun.objects.get(id=run_id)
    return [
        {
            "type": "pipeline.event",
            "runId": str(run.id),
            "event": {
                "step": log.step,
                "status": log.status,
                "message": log.message,
                "detail": log.detail,
                **({"score": log.score} if log.score is not None else {}),
            },
        }
        for log in run.logs.all()
    ]


class PipelineRunConsumer(AsyncJsonWebsocketConsumer):
    run_id: str
    group: str

    async def connect(self):
        self.run_id = self.scope["url_route"]["kwargs"]["run_id"]
        user = await self._authenticate()
        if user is None or isinstance(user, AnonymousUser):
            await self.close(code=4401)
            return

        run = await get_run_for_user(self.run_id, user.id)
        if run is None:
            await self.close(code=4404)
            return

        self.group = run_group_name(self.run_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

        # Replay existing logs for late subscribers
        for msg in await get_run_logs(self.run_id):
            await self.send_json(msg)

    async def disconnect(self, close_code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def pipeline_event(self, event):
        await self.send_json(event["payload"])

    async def _authenticate(self):
        query = parse_qs(self.scope.get("query_string", b"").decode())
        token_list = query.get("token") or query.get("access")
        if token_list:
            try:
                access = AccessToken(token_list[0])
                user_id = access["user_id"]
                from django.contrib.auth import get_user_model

                User = get_user_model()
                return await database_sync_to_async(User.objects.get)(id=user_id)
            except (TokenError, KeyError, User.DoesNotExist):
                return AnonymousUser()

        user = self.scope.get("user")
        if user and user.is_authenticated:
            return user
        return AnonymousUser()
