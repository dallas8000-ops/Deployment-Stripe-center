from pathlib import Path

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import ProjectOwnedMixin
from apps.projects.models import Project
from apps.stripe_installer.readiness import readiness_label, run_readiness_checks, score_readiness
from apps.stripe_installer.repair import run_auto_fix, run_repair_action

from .diagnostics import run_diagnostics


def _require_local_path(project: Project) -> Path:
    if not project.local_path:
        raise ValueError("Set project local_path first.")
    root = Path(project.local_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Project path not found: {root}")
    return root


class DiagnoseView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        try:
            root = _require_local_path(project)
        except (ValueError, FileNotFoundError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        report = run_diagnostics(project, root)
        scan_data = dict(project.scan_data or {})
        scan_data["lastHealthScore"] = report.health_score
        scan_data["lastDiagnosedAt"] = report.scanned_at
        project.scan_data = scan_data
        project.save(update_fields=["scan_data", "updated_at"])
        return Response(report.to_dict())


class ReadinessView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug)
        try:
            root = _require_local_path(project)
        except (ValueError, FileNotFoundError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        app_url = (
            request.query_params.get("app_url")
            or (project.scan_data or {}).get("productionUrl")
            or request.build_absolute_uri("/").rstrip("/")
        )
        checks = run_readiness_checks(project, root, production_url=app_url)
        score = score_readiness(checks)
        scan_data = dict(project.scan_data or {})
        scan_data["lastReadinessScore"] = score
        scan_data["lastReadinessLabel"] = readiness_label(score)
        project.scan_data = scan_data
        project.save(update_fields=["scan_data", "updated_at"])
        return Response(
            {
                "score": score,
                "label": readiness_label(score),
                "checks": [c.to_dict() for c in checks],
            }
        )


class FixView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        try:
            _require_local_path(project)
        except (ValueError, FileNotFoundError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data or {}
        action = data.get("action")
        issue_ids = data.get("issue_ids") or data.get("issueIds")
        force = bool(data.get("force"))
        app_url = data.get("app_url") or request.build_absolute_uri("/").rstrip("/")

        if action:
            try:
                repair = run_repair_action(project, action, force=force, app_url=app_url)
                report = run_diagnostics(project, Path(project.local_path).resolve())
                return Response(
                    {
                        "repairs": [repair.to_dict()],
                        "report": report.to_dict(),
                    }
                )
            except Exception as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if data.get("all"):
            repairs, report = run_auto_fix(project, force=force, app_url=app_url)
        else:
            repairs, report = run_auto_fix(
                project,
                issue_ids=issue_ids,
                force=force,
                app_url=app_url,
            )

        return Response(
            {
                "repairs": [r.to_dict() for r in repairs],
                "report": report.to_dict(),
            }
        )
