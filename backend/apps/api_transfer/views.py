"""API Transfer — deploy, GitHub import, provider status (merged from API Transfer migrationengine)."""

from __future__ import annotations

from datetime import datetime, timezone

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import ProjectOwnedMixin

from .audit import list_audit, record_audit, verify_chain
from .deployments.framework_detector import detect_framework
from .deployments.pipeline import run_pipeline
from .github_import import GitHubImportError, import_repository
from .models import DeploymentRun
from .project_env import hydrate_deploy_request
from .provider_status import (
    deployment_live_summary,
    deploy_stage_data,
    initial_deployment_status,
    normalize_railway_status,
    normalize_render_status,
    provider_live_status,
    server_provider_config,
)
from .providers import ProviderApiError, backup_railway_env_snapshot, get_railway_deployment, get_render_deploy
from .redaction import redact_sensitive_values
from .serializers import DeploymentRequestSerializer, GitHubImportSerializer


class TransferModuleStatusView(APIView):
  permission_classes = (permissions.IsAuthenticated,)

  def get(self, request):
    return Response(
      {
        "module": "api_transfer",
        "status": "active",
        "message": "Deploy, GitHub import, and Railway env backup are available under /api/v1/transfer/ and per-project routes.",
        "capabilities": {
          "railwayDeploy": "active",
          "renderMigrate": "active",
          "envSync": "active",
          "githubImport": "active",
        },
        "sharedWith": ["projects", "vault", "organizations"],
      }
    )


class ProviderStatusView(APIView):
  permission_classes = (permissions.IsAuthenticated,)

  def get(self, request):
    providers = []
    for provider in [
      "github",
      "render",
      "railway",
      "fly",
      "kong",
      "terraform",
      "supabase",
      "cloudflare",
      "stripe",
      "orena",
    ]:
      status_payload = provider_live_status(provider)
      providers.append({"provider": provider, **status_payload})
    return Response({"providers": providers, "serverConfig": server_provider_config()})


class AuditView(APIView):
  permission_classes = (permissions.IsAuthenticated,)

  def get(self, request):
    return Response({"entries": list_audit(), "valid": verify_chain()})


class AuditExportView(APIView):
  permission_classes = (permissions.IsAuthenticated,)

  def get(self, request):
    return Response(
      {
        "exportedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "entries": list_audit(),
        "chain": verify_chain(),
        "redaction": "Sensitive fields are recursively redacted before export.",
      }
    )


class DeployDetectView(APIView):
  permission_classes = (permissions.IsAuthenticated,)

  def post(self, request):
    files = request.data.get("files", [])
    package_json = request.data.get("packageJson")
    framework = detect_framework(files, package_json)
    return Response({"framework": framework.to_dict()})


class GitHubImportView(APIView):
  permission_classes = (permissions.IsAuthenticated,)

  def post(self, request):
    serializer = GitHubImportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    token = data.get("accessToken", "")
    if not token.strip():
      from apps.core.access import get_project_for_user
      from apps.vault.services import get_project_secret

      project_slug = request.data.get("projectSlug") or request.data.get("project_slug")
      if project_slug:
        try:
          project = get_project_for_user(request.user, project_slug)
          vault_token = get_project_secret(project, "GITHUB_TOKEN")
          if vault_token:
            token = vault_token
        except Exception:
          pass
    try:
      result = import_repository(
        data["repoUrl"],
        branch=data.get("branch", ""),
        access_token=token,
      )
    except GitHubImportError as exc:
      return Response({"error": str(exc)}, status=400)
    record_audit(
      "discover",
      request.user.email,
      {"source": "github", "repo": result["repository"]["fullName"], "branch": result["repository"]["branch"]},
      result["repository"]["fullName"],
    )
    return Response(redact_sensitive_values(result))


class ProjectGitHubImportView(ProjectOwnedMixin, APIView):
  permission_classes = (permissions.IsAuthenticated,)

  def post(self, request, project_slug: str):
    project = self.get_project(project_slug, min_role="member")
    serializer = GitHubImportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    from apps.vault.services import get_project_secret

    token = data.get("accessToken", "") or get_project_secret(project, "GITHUB_TOKEN") or ""
    try:
      result = import_repository(
        data["repoUrl"] or project.git_url,
        branch=data.get("branch", ""),
        access_token=token,
      )
    except GitHubImportError as exc:
      return Response({"error": str(exc)}, status=400)
    record_audit(
      "discover",
      request.user.email,
      {"source": "github", "repo": result["repository"]["fullName"], "project": project.slug},
      project.slug,
    )
    return Response(redact_sensitive_values(result))


class ProjectDeployDetectView(ProjectOwnedMixin, APIView):
  permission_classes = (permissions.IsAuthenticated,)

  def post(self, request, project_slug: str):
    self.get_project(project_slug)
    files = request.data.get("files", [])
    package_json = request.data.get("packageJson")
    framework = detect_framework(files, package_json)
    return Response({"framework": framework.to_dict()})


class ProjectDeployView(ProjectOwnedMixin, APIView):
  permission_classes = (permissions.IsAuthenticated,)
  project_min_role = "admin"

  def post(self, request, project_slug: str):
    project = self.get_project(project_slug, min_role="admin")
    serializer = DeploymentRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    req = hydrate_deploy_request(project, serializer.normalized())
    req["requestedBy"] = request.user.email
    req["demoMode"] = False
    result = run_pipeline(req)
    result["liveExecution"] = deployment_live_summary(result)
    status_code = status.HTTP_200_OK if result["succeeded"] else status.HTTP_207_MULTI_STATUS
    DeploymentRun.objects.create(
      deployment_id=result["deploymentId"],
      project=project,
      organization=project.organization,
      app_name=req["appName"],
      target_provider=req["targetProvider"],
      requested_by=req["requestedBy"],
      live=result["liveExecution"]["fullyLive"],
      succeeded=result["succeeded"],
      status=initial_deployment_status(result),
      provider_service_id=deploy_stage_data(result).get("serviceId") or "",
      provider_deploy_id=deploy_stage_data(result).get("deployId") or "",
      provider_status={"initial": deploy_stage_data(result)},
      live_url=result.get("liveUrl") or "",
      result=redact_sensitive_values(result),
    )
    record_audit(
      "apply",
      request.user.email,
      {"deploymentId": result["deploymentId"], "succeeded": result["succeeded"], "project": project.slug},
      req["appName"],
    )
    return Response(redact_sensitive_values({"result": result}), status=status_code)


class ProjectDeploymentHistoryView(ProjectOwnedMixin, APIView):
  permission_classes = (permissions.IsAuthenticated,)

  def get(self, request, project_slug: str):
    project = self.get_project(project_slug)
    limit = min(int(request.query_params.get("limit", 20)), 100)
    runs = DeploymentRun.objects.filter(project=project)[:limit]
    return Response({"runs": [r.to_dict() for r in runs]})


class ProjectDeploymentStatusRefreshView(ProjectOwnedMixin, APIView):
  permission_classes = (permissions.IsAuthenticated,)

  def post(self, request, project_slug: str, deployment_id: str):
    project = self.get_project(project_slug)
    run = DeploymentRun.objects.filter(project=project, deployment_id=deployment_id).first()
    if run is None:
      return Response({"error": "Deployment run not found."}, status=404)
    if not run.live:
      payload = {"status": "simulated", "message": "Simulated deploy — no provider status."}
      run.mark_status("simulated", payload)
      return Response({"run": run.to_dict()})
    if run.target_provider == "render":
      if not run.provider_service_id or not run.provider_deploy_id:
        return Response({"error": "Render service/deploy identifiers were not recorded."}, status=409)
      try:
        provider_status = get_render_deploy(run.provider_service_id, run.provider_deploy_id)
      except ProviderApiError as exc:
        return Response({"error": str(exc)}, status=502)
      run.mark_status(normalize_render_status(provider_status["status"]), provider_status)
      return Response({"run": run.to_dict()})
    if run.target_provider == "railway":
      if not run.provider_deploy_id:
        return Response({"error": "Railway deployment identifier was not recorded."}, status=409)
      try:
        provider_status = get_railway_deployment(run.provider_deploy_id)
      except ProviderApiError as exc:
        return Response({"error": str(exc)}, status=502)
      run.mark_status(normalize_railway_status(provider_status["status"]), provider_status)
      return Response({"run": run.to_dict()})
    payload = {"status": "unknown", "message": f"Status polling not implemented for {run.target_provider}."}
    run.mark_status("unknown", payload)
    return Response({"run": run.to_dict()})


class RailwayEnvBackupView(APIView):
  permission_classes = (permissions.IsAuthenticated,)

  def post(self, request):
    service_id = (request.data.get("service_id") or request.data.get("serviceId") or "").strip()
    service_name = (request.data.get("service_name") or request.data.get("serviceName") or "").strip()
    project_id = (request.data.get("project_id") or request.data.get("projectId") or "").strip() or None
    environment_id = (request.data.get("environment_id") or request.data.get("environmentId") or "").strip() or None
    save_to_disk = request.data.get("save_to_disk", request.data.get("saveToDisk", True))
    if isinstance(save_to_disk, str):
      save_to_disk = save_to_disk.lower() not in ("0", "false", "no")

    if not service_id:
      return Response({"error": "service_id is required"}, status=400)
    if not settings.RAILWAY_API_TOKEN:
      return Response({"error": "RAILWAY_API_TOKEN is not configured"}, status=400)

    try:
      snapshot = backup_railway_env_snapshot(
        service_id,
        service_name=service_name,
        project_id=project_id,
        environment_id=environment_id,
        save_to_disk=bool(save_to_disk),
      )
    except ProviderApiError as exc:
      return Response({"error": str(exc)}, status=400)

    record_audit(
      "railway_env_backup",
      request.user.email,
      {
        "serviceId": service_id,
        "serviceName": snapshot.get("serviceName"),
        "keyCount": snapshot.get("keyCount"),
        "secretKeyCount": snapshot.get("secretKeyCount"),
      },
      service_id,
    )
    return Response(
      redact_sensitive_values(
        {
          "message": f"Backed up {snapshot['keyCount']} variable(s) for {snapshot.get('serviceName')}.",
          "serviceName": snapshot.get("serviceName"),
          "serviceId": snapshot.get("serviceId"),
          "keyCount": snapshot.get("keyCount"),
          "secretKeyCount": snapshot.get("secretKeyCount"),
          "variableKeys": snapshot.get("variableKeys"),
          "secretKeys": snapshot.get("secretKeys"),
          "backupPath": snapshot.get("backupPath"),
        }
      )
    )
