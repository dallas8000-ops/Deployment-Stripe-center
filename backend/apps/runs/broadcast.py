"""Broadcast pipeline events to Channels group + persist logs."""

from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.stripe_installer.events import PipelineEvent

from .models import PipelineRun, PipelineRunLog


def run_group_name(run_id: str) -> str:
    return f"pipeline_run_{run_id}"


def make_run_emitter(run: PipelineRun):
    channel_layer = get_channel_layer()

    def emit(event: PipelineEvent) -> None:
        PipelineRunLog.objects.create(
            run=run,
            step=event.step,
            status=event.status,
            message=event.message,
            detail=event.detail,
            score=event.score,
        )
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                run_group_name(str(run.id)),
                {
                    "type": "pipeline.event",
                    "payload": {
                        "type": "pipeline.event",
                        "runId": str(run.id),
                        "event": event.to_dict(),
                    },
                },
            )

    return emit
