from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.projects.models import Project
from apps.runs.broadcast import make_run_emitter
from apps.runs.models import PipelineRun
from apps.stripe_engine.events import PipelineEvent
from apps.stripe_engine.pipeline import PipelineOptions, run_pipeline


def _serialize_pipeline_result(result) -> dict:
    return {
        "verification": result.verification,
        "provision": result.provision,
        "filesWritten": result.files_written,
        "generatedFiles": result.generated_files,
        "downloadAvailable": bool(result.files_written),
        "readiness": {
            "score": result.readiness_score,
            "checks": result.readiness_checks,
        },
    }


@shared_task(bind=True, name="runs.execute_pipeline")
def execute_pipeline(self, run_id: str) -> None:
    run = PipelineRun.objects.select_related("project").get(id=run_id)
    run.status = PipelineRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])

    project: Project = run.project
    opts_data = run.options or {}
    emitter = make_run_emitter(run)

    try:
        if opts_data.get("mode") == "deploy":
            from apps.deploy.pipeline import DeployOptions, run_deploy_pipeline

            deploy_result = run_deploy_pipeline(
                project,
                on_event=emitter,
                opts=DeployOptions(
                    provision_stripe=opts_data.get("provision", True),
                    generate_code=opts_data.get("generate", True),
                    sync_env=opts_data.get("sync_env", False),
                    force=opts_data.get("force", False),
                    include_infra=opts_data.get("include_infra", True),
                    provision_postgres=opts_data.get("provision_postgres", True),
                    include_readiness=opts_data.get("include_readiness", True),
                    push_platform=opts_data.get("push", False),
                    app_url=opts_data.get("app_url", "http://localhost:8000"),
                    postgres_provider=opts_data.get("postgres_provider", "neon"),
                ),
            )
            result = deploy_result.pipeline
            run.status = PipelineRun.Status.COMPLETED
            run.result = {
                **_serialize_pipeline_result(result),
                "deploy": {
                    "platform": deploy_result.platform,
                    "productionUrl": deploy_result.production_url,
                    "postgresConnected": deploy_result.postgres_connected,
                    "nextSteps": deploy_result.next_steps,
                    "manifest": deploy_result.manifest,
                    "push": deploy_result.push_result,
                },
            }
        else:
            options = PipelineOptions(
                provision=opts_data.get("provision", True),
                generate=opts_data.get("generate", True),
                sync_env=opts_data.get("sync_env", False),
                force=opts_data.get("force", False),
                include_readiness=opts_data.get("include_readiness", True),
                app_url=opts_data.get("app_url", "http://localhost:8000"),
            )
            result = run_pipeline(project, on_event=emitter, opts=options)
            run.status = PipelineRun.Status.COMPLETED
            run.result = _serialize_pipeline_result(result)
        run.readiness_score = result.readiness_score
        run.error_message = ""
    except Exception as exc:
        run.status = PipelineRun.Status.FAILED
        run.error_message = str(exc)
        emitter(PipelineEvent("run.failed", "failed", str(exc)))
    finally:
        run.completed_at = timezone.now()
        run.save(
            update_fields=["status", "result", "readiness_score", "error_message", "completed_at"]
        )
