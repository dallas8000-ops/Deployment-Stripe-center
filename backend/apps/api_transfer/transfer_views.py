"""Render → Railway transfer run control APIs."""

from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import ProjectOwnedMixin

from .audit import record_audit
from .models import TransferRun
from .org_context import organization_for_user
from .serializers import TransferStartSerializer
from .transfer_control import (
    replay_transfer_run,
    start_transfer_run,
    stop_transfer_run,
    transfer_history,
    transfer_metrics,
    transfer_status_payload,
    _transfer_history_item,
)


class TransferStartView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        serializer = TransferStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        org = organization_for_user(request.user)
        try:
            payload = start_transfer_run(
                data,
                requested_by=request.user.email,
                organization=org,
                queue_only=bool(data.get("queueOnly")),
            )
        except RuntimeError as exc:
            return Response({"error": str(exc), "run": transfer_status_payload()}, status=409)

        record_audit(
            "apply",
            request.user.email,
            {"kind": "transfer-start", "runId": payload.get("id"), "mode": data.get("mode")},
            "transfer",
        )
        if data.get("queueOnly"):
            return Response({"run": payload})
        return Response({"run": payload})


class ProjectTransferStartView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    project_min_role = "admin"

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug, min_role="admin")
        serializer = TransferStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        org = organization_for_user(request.user, project)
        try:
            payload = start_transfer_run(
                data,
                requested_by=request.user.email,
                organization=org,
                project=project,
                queue_only=bool(data.get("queueOnly")),
            )
        except RuntimeError as exc:
            return Response({"error": str(exc), "run": transfer_status_payload()}, status=409)

        record_audit(
            "apply",
            request.user.email,
            {"kind": "transfer-start", "project": project.slug, "runId": payload.get("id")},
            project.slug,
        )
        if data.get("queueOnly"):
            return Response({"run": payload})
        return Response({"run": payload})


class TransferStopView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        stopped, payload, message = stop_transfer_run()
        if not stopped:
            return Response({"stopped": False, "message": message, "run": payload})
        record_audit("apply", request.user.email, {"kind": "transfer-stop", "runId": payload.get("id")}, "transfer")
        return Response({"stopped": True, "run": payload})


class TransferStatusView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        return Response({"run": transfer_status_payload()})


class TransferHistoryView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        raw_limit = str(request.query_params.get("limit") or "10")
        raw_cursor = str(request.query_params.get("cursor") or "").strip()
        try:
            limit = max(1, min(100, int(raw_limit)))
        except ValueError:
            return Response({"error": "limit must be an integer."}, status=400)
        cursor_id = None
        if raw_cursor:
            try:
                cursor_id = int(raw_cursor)
            except ValueError:
                return Response({"error": "cursor must be an integer id."}, status=400)

        org = organization_for_user(request.user)
        return Response(transfer_history(limit, cursor_id, organization=org))


class ProjectTransferHistoryView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug)
        raw_limit = str(request.query_params.get("limit") or "10")
        try:
            limit = max(1, min(100, int(raw_limit)))
        except ValueError:
            return Response({"error": "limit must be an integer."}, status=400)
        org = organization_for_user(request.user, project)
        return Response(transfer_history(limit, None, organization=org))


class TransferMetricsView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        org = organization_for_user(request.user)
        return Response(transfer_metrics(organization=org))


class TransferReplayView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, run_id: str):
        try:
            run = replay_transfer_run(run_id, request.user.email)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=404 if "not found" in str(exc).lower() else 409)

        record_audit("apply", request.user.email, {"kind": "transfer-replay", "runId": run_id}, "transfer")
        payload = _transfer_history_item(run, active_run_id="", active_running=False)
        return Response({"run": payload})
