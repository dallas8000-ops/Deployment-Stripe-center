"""In-process transfer worker state and helpers (Render → Railway)."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone

from django.conf import settings
from django.db.models import Count, Q

from .models import TransferRun

_TRANSFER_LOCK = threading.Lock()
_TRANSFER_STATE: dict[str, object] = {
    "id": "",
    "process": None,
    "startedAt": "",
    "command": [],
    "logPath": "",
}

_UTC_OFFSET_SUFFIX = "+00:00"
_UTC_Z_SUFFIX = "Z"
_TRANSFER_AGING_WINDOW_DEFAULT = 300
_TRANSFER_MAX_AGING_BOOST_DEFAULT = 10


def build_transfer_command(options: dict) -> list[str]:
    cmd = [sys.executable, "manage.py", "transfer_render_to_railway", "--mode", str(options.get("mode", "queue"))]

    for value in options.get("only", []) or []:
        cmd.extend(["--only", str(value)])

    limit = options.get("limit")
    if limit:
        cmd.extend(["--limit", str(int(limit))])

    if options.get("redeployExisting"):
        cmd.append("--redeploy-existing")
    if not options.get("verify", True):
        cmd.append("--no-verify")

    cmd.extend(["--verify-timeout", str(int(options.get("verifyTimeout", 240)))])
    cmd.extend(["--verify-interval", str(int(options.get("verifyInterval", 10)))])
    cmd.extend(["--service-timeout", str(int(options.get("serviceTimeout", 180)))])

    if options.get("allowOverlap"):
        cmd.append("--allow-overlap")
    if options.get("dryRun"):
        cmd.append("--dry-run")

    return cmd


def transfer_log_path(run_id: str) -> str:
    data_dir = os.path.join(str(settings.BASE_DIR), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, f"transfer-{run_id}.log")


def transfer_status_payload() -> dict:
    process = _TRANSFER_STATE.get("process")
    running = isinstance(process, subprocess.Popen) and process.poll() is None
    exit_code = None if running or not isinstance(process, subprocess.Popen) else process.poll()
    run_id = str(_TRANSFER_STATE.get("id") or "")
    record = _get_transfer_record(run_id)
    if record is None:
        return _transfer_fallback_payload(run_id, running, exit_code)

    _sync_transfer_record(record, running, exit_code)
    return _transfer_record_payload(record, run_id, running)


def start_transfer_run(
    data: dict,
    *,
    requested_by: str,
    organization=None,
    project=None,
    queue_only: bool = False,
) -> dict:
    cmd = build_transfer_command(data)
    run_id = str(uuid.uuid4())
    log_path = transfer_log_path(run_id)
    plain_options = _to_plain(data)

    if queue_only:
        run = TransferRun.objects.create(
            run_id=run_id,
            project=project,
            organization=organization or (project.organization if project else None),
            mode=str(data.get("mode") or "queue"),
            requested_by=requested_by,
            status=TransferRun.STATUS_QUEUED,
            command=cmd,
            options=plain_options,
            step=TransferRun.STEP_QUEUED,
            max_retries=int(data.get("maxRetries") or 3),
            log_path=log_path,
        )
        run.mark_step(TransferRun.STEP_QUEUED, details={"queueOnly": True})
        payload = run.to_dict()
        payload.update({"running": False, "logTail": ""})
        return payload

    with _TRANSFER_LOCK:
        process = _TRANSFER_STATE.get("process")
        if isinstance(process, subprocess.Popen) and process.poll() is None:
            raise RuntimeError("A transfer is already running.")

        with open(log_path, "w", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                cmd,
                cwd=str(settings.BASE_DIR),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )

        _TRANSFER_STATE.update(
            {
                "id": run_id,
                "process": process,
                "startedAt": _iso_utc_z(datetime.now(timezone.utc)),
                "command": cmd,
                "logPath": log_path,
            }
        )
        TransferRun.objects.create(
            run_id=run_id,
            project=project,
            organization=organization or (project.organization if project else None),
            mode=str(data.get("mode") or "queue"),
            requested_by=requested_by,
            status=TransferRun.STATUS_RUNNING,
            command=cmd,
            options=plain_options,
            step=TransferRun.STEP_TRANSFER,
            max_retries=int(data.get("maxRetries") or 3),
            attempt_started_at=datetime.now(timezone.utc),
            log_path=log_path,
        )

    return transfer_status_payload()


def stop_transfer_run() -> tuple[bool, dict, str]:
    with _TRANSFER_LOCK:
        process = _TRANSFER_STATE.get("process")
        if not isinstance(process, subprocess.Popen):
            return False, transfer_status_payload(), "No transfer run is tracked."
        if process.poll() is not None:
            return False, transfer_status_payload(), "Transfer already finished."

        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

        payload = transfer_status_payload()
        run = TransferRun.objects.filter(run_id=payload.get("id") or "").first()
        if run is not None:
            run.status = TransferRun.STATUS_STOPPED
            run.step = TransferRun.STEP_FINALIZE
            run.exit_code = payload.get("exitCode")
            run.finished_at = datetime.now(timezone.utc)
            run.save(update_fields=["status", "step", "exit_code", "finished_at", "updated_at"])

    return True, payload, ""


def transfer_history(limit: int, cursor_id: int | None, organization=None) -> dict:
    process = _TRANSFER_STATE.get("process")
    running = isinstance(process, subprocess.Popen) and process.poll() is None
    active_run_id = str(_TRANSFER_STATE.get("id") or "")

    queryset = TransferRun.objects.order_by("-id")
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    if cursor_id is not None:
        queryset = queryset.filter(id__lt=cursor_id)
    runs = list(queryset[:limit])
    payload = [_transfer_history_item(run, active_run_id, running) for run in runs]
    next_cursor = str(runs[-1].id) if len(runs) == limit else None
    return {"runs": payload, "nextCursor": next_cursor}


def transfer_metrics(organization=None) -> dict:
    now = datetime.now(timezone.utc)
    running_filter = Q(status=TransferRun.STATUS_RUNNING) & Q(lease_expires_at__isnull=False) & Q(lease_expires_at__gt=now)
    queued_filter = Q(status=TransferRun.STATUS_QUEUED)
    retryable_filter = Q(status=TransferRun.STATUS_RETRYABLE)
    dead_letter_filter = Q(status=TransferRun.STATUS_DEAD_LETTER)

    all_runs = TransferRun.objects.all()
    scoped = all_runs.filter(organization=organization) if organization else all_runs

    return {
        "summary": {
            "running": all_runs.filter(running_filter).count(),
            "queued": all_runs.filter(queued_filter).count(),
            "retryable": all_runs.filter(retryable_filter).count(),
            "deadLetter": all_runs.filter(dead_letter_filter).count(),
            "total": all_runs.count(),
        },
        "schedulingPolicy": _transfer_scheduling_policy(),
        "alerts": _transfer_alerts(now=now),
        "organization": {
            "id": str(organization.id) if organization else None,
            "name": organization.name if organization else None,
            "running": scoped.filter(running_filter).count(),
            "queued": scoped.filter(queued_filter).count(),
            "retryable": scoped.filter(retryable_filter).count(),
            "deadLetter": scoped.filter(dead_letter_filter).count(),
            "total": scoped.count(),
        },
        "runningByOrganization": _organization_metric_rows(all_runs.filter(running_filter)),
        "queuedByOrganization": _organization_metric_rows(all_runs.filter(queued_filter | retryable_filter)),
        "deadLetterByOrganization": _organization_metric_rows(all_runs.filter(dead_letter_filter)),
        "generatedAt": _iso_utc_z(now),
    }


def replay_transfer_run(run_id: str, actor: str) -> TransferRun:
    run = TransferRun.objects.filter(run_id=run_id).first()
    if run is None:
        raise ValueError("Transfer run not found.")
    if run.status not in {TransferRun.STATUS_FAILED, TransferRun.STATUS_DEAD_LETTER, TransferRun.STATUS_STOPPED}:
        raise ValueError(f"Run status '{run.status}' cannot be replayed.")

    run.status = TransferRun.STATUS_QUEUED
    run.step = TransferRun.STEP_QUEUED
    run.retry_count = 0
    run.next_retry_at = None
    run.last_error = ""
    run.exit_code = None
    run.finished_at = None
    run.attempt_started_at = None
    run.lease_owner = ""
    run.lease_expires_at = None
    run.heartbeat_at = None
    run.save(
        update_fields=[
            "status",
            "step",
            "retry_count",
            "next_retry_at",
            "last_error",
            "exit_code",
            "finished_at",
            "attempt_started_at",
            "lease_owner",
            "lease_expires_at",
            "heartbeat_at",
            "updated_at",
        ]
    )
    run.mark_step(TransferRun.STEP_QUEUED, details={"replay": True, "requestedBy": actor})
    return run


def _get_transfer_record(run_id: str) -> TransferRun | None:
    if run_id:
        return TransferRun.objects.filter(run_id=run_id).first()
    return TransferRun.objects.order_by("-created_at").first()


def _sync_transfer_record(record: TransferRun, running: bool, exit_code: int | None) -> None:
    if running:
        if record.status != TransferRun.STATUS_RUNNING:
            record.status = TransferRun.STATUS_RUNNING
            record.step = TransferRun.STEP_TRANSFER
            record.exit_code = None
            record.finished_at = None
            record.save(update_fields=["status", "step", "exit_code", "finished_at", "updated_at"])
        return

    if record.status != TransferRun.STATUS_RUNNING:
        return

    record.status = TransferRun.STATUS_SUCCEEDED if exit_code == 0 else TransferRun.STATUS_FAILED
    record.step = TransferRun.STEP_FINALIZE
    record.exit_code = exit_code
    record.finished_at = datetime.now(timezone.utc)
    record.save(update_fields=["status", "step", "exit_code", "finished_at", "updated_at"])


def _transfer_record_payload(record: TransferRun, run_id: str, running: bool) -> dict:
    payload = record.to_dict()
    payload.update(
        {
            "running": running if record.run_id == run_id else False,
            "exitCode": record.exit_code,
            "command": record.command,
            "logTail": _tail_file(record.log_path, 40),
        }
    )
    payload.update(_queue_priority_snapshot(record, datetime.now(timezone.utc)))
    return payload


def _transfer_fallback_payload(run_id: str, running: bool, exit_code: int | None) -> dict:
    return {
        "id": run_id,
        "running": running,
        "exitCode": exit_code,
        "startedAt": _TRANSFER_STATE.get("startedAt") or "",
        "command": _TRANSFER_STATE.get("command") or [],
        "logTail": _tail_file(str(_TRANSFER_STATE.get("logPath") or ""), 40),
        "status": "running" if running else "idle",
    }


def _transfer_history_item(run: TransferRun, active_run_id: str, active_running: bool) -> dict:
    item = run.to_dict()
    item["running"] = bool(active_running and run.run_id == active_run_id)
    item["command"] = run.command
    item["logTail"] = _tail_file(run.log_path, 12)
    item.update(_queue_priority_snapshot(run, datetime.now(timezone.utc)))
    return item


def _queue_priority_snapshot(run: TransferRun, now: datetime) -> dict:
    aging_window, max_aging_boost = _queue_aging_config()
    queue_priority = _queue_priority_value(run)
    queue_age_seconds = max(0, int((now - run.created_at).total_seconds()))
    queue_age_boost = min(max_aging_boost, queue_age_seconds // aging_window)
    return {
        "queuePriority": queue_priority,
        "queueAgeSeconds": queue_age_seconds,
        "queueAgeBoost": queue_age_boost,
        "queueEffectivePriority": queue_priority + queue_age_boost,
        "agingWindowSeconds": aging_window,
        "maxAgingBoost": max_aging_boost,
    }


def _queue_aging_config() -> tuple[int, int]:
    raw_window = getattr(settings, "TRANSFER_QUEUE_AGING_WINDOW_SECONDS", _TRANSFER_AGING_WINDOW_DEFAULT)
    raw_boost = getattr(settings, "TRANSFER_QUEUE_MAX_AGING_BOOST", _TRANSFER_MAX_AGING_BOOST_DEFAULT)
    try:
        aging_window = max(1, int(raw_window))
    except (TypeError, ValueError):
        aging_window = _TRANSFER_AGING_WINDOW_DEFAULT
    try:
        max_aging_boost = max(0, int(raw_boost))
    except (TypeError, ValueError):
        max_aging_boost = _TRANSFER_MAX_AGING_BOOST_DEFAULT
    return aging_window, max_aging_boost


def _transfer_scheduling_policy() -> dict:
    aging_window, max_aging_boost = _queue_aging_config()
    return {
        "workerBatchLimit": int(getattr(settings, "TRANSFER_WORKER_LIMIT", 5)),
        "pollIntervalSeconds": int(getattr(settings, "TRANSFER_WORKER_POLL_INTERVAL_SECONDS", 5)),
        "leaseTtlSeconds": int(getattr(settings, "TRANSFER_WORKER_LEASE_TTL_SECONDS", 120)),
        "heartbeatIntervalSeconds": int(getattr(settings, "TRANSFER_WORKER_HEARTBEAT_INTERVAL_SECONDS", 15)),
        "organizationConcurrencyCap": int(getattr(settings, "TRANSFER_ORG_CONCURRENCY_CAP", 1)),
        "agingWindowSeconds": aging_window,
        "maxAgingBoost": max_aging_boost,
    }


def _transfer_alerts(now: datetime) -> dict:
    dead_letter_count = TransferRun.objects.filter(status=TransferRun.STATUS_DEAD_LETTER).count()
    retryable_count = TransferRun.objects.filter(status=TransferRun.STATUS_RETRYABLE).count()
    stale_lease_count = TransferRun.objects.filter(
        status=TransferRun.STATUS_RUNNING,
        lease_expires_at__isnull=False,
        lease_expires_at__lt=now,
    ).count()

    dead_letter_threshold = int(getattr(settings, "TRANSFER_ALERT_DEAD_LETTER_THRESHOLD", 5))
    retryable_threshold = int(getattr(settings, "TRANSFER_ALERT_RETRYABLE_THRESHOLD", 10))
    stale_lease_threshold = int(getattr(settings, "TRANSFER_ALERT_STALE_LEASE_THRESHOLD", 1))

    return {
        "deadLetter": {
            "active": dead_letter_count >= dead_letter_threshold,
            "count": dead_letter_count,
            "threshold": dead_letter_threshold,
        },
        "retryableBacklog": {
            "active": retryable_count >= retryable_threshold,
            "count": retryable_count,
            "threshold": retryable_threshold,
        },
        "staleLeases": {
            "active": stale_lease_count >= stale_lease_threshold,
            "count": stale_lease_count,
            "threshold": stale_lease_threshold,
        },
    }


def _queue_priority_value(run: TransferRun) -> int:
    value = (run.options or {}).get("queuePriority")
    if isinstance(value, int):
        return value
    return 0


def _organization_metric_rows(queryset):
    rows = queryset.values("organization_id", "organization__name").annotate(count=Count("id")).order_by(
        "organization__name"
    )
    return [
        {
            "organizationId": str(row["organization_id"]) if row["organization_id"] else None,
            "organizationName": row["organization__name"] or "unassigned",
            "count": row["count"],
        }
        for row in rows
    ]


def _iso_utc_z(value: datetime) -> str:
    return value.isoformat().replace(_UTC_OFFSET_SUFFIX, _UTC_Z_SUFFIX)


def _tail_file(path: str, lines: int) -> str:
    if not path or not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        data = handle.readlines()
    return "".join(data[-lines:]).strip()


def _to_plain(value):
    from datetime import date

    if isinstance(value, dict):
        return {k: _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
