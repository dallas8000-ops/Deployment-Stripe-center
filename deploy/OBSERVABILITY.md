# Observability (Phase 3)

## Sentry

Set on all Railway services (web, worker, beat):

```
SENTRY_DSN=https://<key>@<org>.ingest.sentry.io/<project>
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
LOG_LEVEL=INFO
```

Sentry captures:

- Django unhandled exceptions (web)
- Celery worker/beat failures
- Redis client errors
- `logging.error` and above as events

`send_default_pii` is **false** — no user emails in Sentry payloads by default.

## Structured logs

Every HTTP request gets an `X-Request-ID` header (client may supply one). Logs use:

```
2026-06-22T12:00:00 INFO [a1b2c3d4-...] apps.billing.webhooks: ...
```

Filter Railway logs by request ID when correlating with a user report.

## Health endpoints

| Path | Purpose |
|------|---------|
| `GET /health/` | Liveness — DB, vault, Redis (prod), license |
| `GET /health/ready/` | Readiness for load balancers (DB + Redis) |
| `GET /health/metrics/` | Ops metrics — latencies, transfer queue depth, webhook volume |

Example:

```bash
curl https://your-domain/health/metrics/
```

## Railway

Point uptime checks at `/health/` (liveness). For scaled web replicas, optional secondary check on `/health/ready/`.
