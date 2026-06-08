from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import ProjectOwnedMixin
from apps.deploy.config import write_deploy_config
from apps.deploy.postgres import get_production_url
from apps.projects.audit import log_audit
from apps.stripe_engine.drift import detect_drift, persist_drift_snapshot
from apps.stripe_engine.repair import run_repair_action
from apps.stripe_engine.webhook_events import fetch_stripe_event
from apps.stripe_engine.readiness import readiness_label, run_readiness_checks, score_readiness
from apps.stripe_engine.stripe_config import write_stripe_config
from apps.stripe_engine.webhook_health import webhook_health
from apps.stripe_engine.diagnostics import run_diagnostics

from .copilot import (
    catalog_strategist,
    fix_copilot,
    handoff_pack,
    nl_to_configs,
    readiness_coach,
    webhook_incident_assistant,
)
from .providers import generate_recommendations


class RecommendView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        try:
            text, provider = generate_recommendations(project)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"recommendations": text, "provider": provider})


class FixCopilotView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        from pathlib import Path

        project = self.get_project(project_slug)
        report = None
        if project.local_path:
            root = Path(project.local_path).resolve()
            if root.is_dir():
                report = run_diagnostics(project, root)
        try:
            items, provider = fix_copilot(project, report)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"items": items, "provider": provider})


class ReadinessCoachView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        from pathlib import Path

        project = self.get_project(project_slug)
        checks = None
        if project.local_path:
            root = Path(project.local_path).resolve()
            if root.is_dir():
                prod = get_production_url(project, request.build_absolute_uri("/").rstrip("/"))
                checks = run_readiness_checks(project, root, production_url=prod)
        try:
            items, provider = readiness_coach(project, checks)
            score = score_readiness(checks) if checks else None
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "items": items,
                "provider": provider,
                "score": score,
                "label": readiness_label(score) if score is not None else None,
            }
        )


class NlConfigView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        instruction = request.data.get("instruction", "")
        apply = bool(request.data.get("apply", False))
        try:
            stripe_cfg, deploy_cfg, provider = nl_to_configs(project, instruction)
        except (ValueError, RuntimeError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        written = []
        if apply and project.local_path:
            from pathlib import Path

            root = Path(project.local_path).resolve()
            if root.is_dir():
                write_stripe_config(root, stripe_cfg)
                write_deploy_config(root, deploy_cfg)
                written = ["stripe.config.json", "deploy.config.json"]

        return Response(
            {
                "stripeConfig": stripe_cfg,
                "deployConfig": deploy_cfg,
                "provider": provider,
                "written": written,
            }
        )


class CatalogStrategistView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        apply = bool(request.data.get("apply", False))
        try:
            cfg, summary, provider = catalog_strategist(
                project, request.data.get("business_description", "")
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        written = []
        if apply and project.local_path:
            from pathlib import Path

            root = Path(project.local_path).resolve()
            if root.is_dir():
                write_stripe_config(root, cfg)
                written.append("stripe.config.json")

        return Response({"stripeConfig": cfg, "summary": summary, "provider": provider, "written": written})


class HandoffPackView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        prod = request.data.get("production_url") or get_production_url(
            project, request.build_absolute_uri("/").rstrip("/")
        )
        try:
            pack, provider = handoff_pack(project, production_url=prod)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({**pack, "provider": provider})


class WebhookIncidentView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        import json

        project = self.get_project(project_slug)
        event_id = (request.data.get("event_id") or "").strip()
        payload = request.data.get("payload", "")
        fetched = False
        try:
            if event_id:
                sanitized = fetch_stripe_event(project, event_id)
                payload = json.dumps(sanitized)
                fetched = True
            analysis, provider = webhook_incident_assistant(
                project, payload, fetched_from_stripe=fetched
            )
        except (ValueError, RuntimeError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "analysis": analysis,
                "provider": provider,
                "eventId": event_id or None,
                "fetchedFromStripe": fetched,
            }
        )


class DriftView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug)
        try:
            result = detect_drift(project)
            persist_drift_snapshot(project, result)
            return Response(result)
        except RuntimeError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class DriftResyncView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        from pathlib import Path

        project = self.get_project(project_slug)
        if not project.local_path:
            return Response(
                {"error": "Project local_path is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        root = Path(project.local_path).resolve()
        if not root.is_dir():
            return Response(
                {"error": f"Project path not found: {root}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        app_url = get_production_url(project, request.build_absolute_uri("/").rstrip("/"))
        try:
            before = detect_drift(project)
            repair = run_repair_action(project, "provision-stripe", app_url=app_url)
            after = detect_drift(project)
            persist_drift_snapshot(project, after)
            log_audit(
                project,
                "drift.resync",
                actor=request.user,
                detail={
                    "beforeCount": before.get("driftCount"),
                    "afterCount": after.get("driftCount"),
                    "repair": repair.to_dict(),
                },
            )
        except (RuntimeError, ValueError, FileNotFoundError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "before": before,
                "after": after,
                "repair": repair.to_dict(),
            }
        )


class WebhookHealthView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug)
        try:
            return Response(webhook_health(project))
        except RuntimeError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
