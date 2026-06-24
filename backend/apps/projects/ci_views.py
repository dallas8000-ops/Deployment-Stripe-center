from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.audit import log_audit
from apps.projects.auth import ProjectApiKeyAuthentication
from apps.projects.github_ci import GITHUB_CI_WORKFLOW, get_github_ci_status, run_readiness_gate


class CiReadinessGateView(APIView):
    """POST with project API key — for GitHub Actions and external CI."""

    authentication_classes = (ProjectApiKeyAuthentication,)
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        project = getattr(request, "stripe_core_project", None)
        if not project:
            return Response({"error": "Invalid API key"}, status=401)

        body_slug = (request.data or {}).get("project")
        if body_slug and body_slug != project.slug:
            return Response({"error": "API key does not match project slug"}, status=403)

        try:
            result = run_readiness_gate(project, app_url=(request.data or {}).get("app_url", ""))
            log_audit(
                project,
                "ci.readiness_gate",
                detail={"passed": result["passed"], "score": result["score"]},
            )
        except (ValueError, FileNotFoundError) as exc:
            return Response({"error": str(exc), "passed": False}, status=400)

        return Response(result)


class ProjectGithubCiView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        from apps.core.access import get_project_for_user

        project = get_project_for_user(request.user, project_slug, min_role="viewer")
        ref = request.query_params.get("ref")
        try:
            status_payload = get_github_ci_status(project, ref=ref)
        except (RuntimeError, ValueError) as exc:
            return Response({"error": str(exc)}, status=400)
        return Response(status_payload)


class ProjectCiWorkflowView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        from apps.core.access import get_project_for_user

        get_project_for_user(request.user, project_slug, min_role="member")
        return Response({"workflow": GITHUB_CI_WORKFLOW, "filename": ".github/workflows/stripe-installer.yml"})


class ProjectReadinessGateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        from apps.core.access import get_project_for_user

        project = get_project_for_user(request.user, project_slug, min_role="member")
        try:
            result = run_readiness_gate(
                project,
                app_url=request.data.get("app_url") or request.build_absolute_uri("/").rstrip("/"),
            )
            log_audit(project, "readiness.gate", actor=request.user, detail=result)
        except (ValueError, FileNotFoundError) as exc:
            return Response({"error": str(exc), "passed": False}, status=400)
        return Response(result)
