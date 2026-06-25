"""PostgreSQL schema and status — ported from legacy Node deploy/postgres.ts."""

from __future__ import annotations

import re
from pathlib import Path

from apps.projects.models import Project
from apps.vault.models import get_secret

DATABASE_URL_PATTERN = re.compile(r"^postgres(ql)?://", re.I)


def get_database_url(project: Project) -> str | None:
    return get_secret(project, "DATABASE_URL")


def is_testable_database_url(database_url: str | None) -> bool:
    """True only for literal postgres URLs we can connect to from the hub machine."""
    if not database_url or not str(database_url).strip():
        return False
    from apps.deploy.env_push import is_placeholder_database_url, is_railway_reference

    url = str(database_url).strip()
    if is_railway_reference(url) or is_placeholder_database_url(url):
        return False
    return bool(DATABASE_URL_PATTERN.match(url))


def _needs_ssl(url: str) -> bool:
    return any(
        token in url
        for token in ("sslmode=require", "neon.tech", "supabase.co", "railway.app")
    )


def test_postgres_connection(database_url: str) -> dict:
    try:
        import psycopg
    except ImportError:
        return {"ok": False, "message": "psycopg not installed — run pip install -r requirements.txt"}

    try:
        kwargs: dict = {"connect_timeout": 8}
        if _needs_ssl(database_url):
            kwargs["sslmode"] = "require"
        with psycopg.connect(database_url, **kwargs) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                row = cur.fetchone()
        version = (row[0] if row else "PostgreSQL").split()[0]
        return {"ok": True, "message": f"Connected ({version})"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def apply_postgres_schema(project: Project) -> dict:
    database_url = get_database_url(project)
    if not database_url:
        return {"ok": False, "message": "DATABASE_URL not configured in vault"}
    if not DATABASE_URL_PATTERN.match(database_url):
        return {"ok": False, "message": "DATABASE_URL format invalid"}

    try:
        import psycopg
    except ImportError:
        return {"ok": False, "message": "psycopg not installed — run pip install -r requirements.txt"}

    sql = schema_sql()
    try:
        kwargs: dict = {"connect_timeout": 15}
        if _needs_ssl(database_url):
            kwargs["sslmode"] = "require"
        with psycopg.connect(database_url, **kwargs) as conn:
            conn.execute(sql)
            conn.commit()
    except Exception as exc:
        return {"ok": False, "message": str(exc)}

    scan = dict(project.scan_data or {})
    postgres = dict(scan.get("postgres") or {})
    postgres["schemaApplied"] = True
    scan["postgres"] = postgres
    project.scan_data = scan
    project.save(update_fields=["scan_data", "updated_at"])
    return {"ok": True, "message": "Schema applied to DATABASE_URL"}


def postgres_status(project: Project, *, test_connection: bool = False) -> dict:
    url = get_database_url(project)
    valid = bool(url and DATABASE_URL_PATTERN.match(url))
    scan = project.scan_data or {}
    postgres_meta = scan.get("postgres") or {}

    data = {
        "configured": valid,
        "message": "DATABASE_URL set in vault" if valid else "Store DATABASE_URL in vault (postgresql://…)",
        "schemaApplied": bool(postgres_meta.get("schemaApplied")),
    }

    if test_connection and valid and url:
        conn = test_postgres_connection(url)
        data["connected"] = conn["ok"]
        data["connectionMessage"] = conn["message"]
    return data


def schema_sql() -> str:
    candidates = [
        Path(__file__).resolve().parents[1]
        / "stripe_core"
        / "codegen"
        / "templates"
        / "shared"
        / "schema.sql.j2",
        Path(__file__).resolve().parents[3] / "db" / "schema.sql",
    ]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Postgres schema template not found (tried: {candidates})")


def get_production_url(project: Project, fallback: str = "") -> str:
    from pathlib import Path

    from apps.deploy.config import resolve_production_url

    root = Path(project.local_path).resolve() if project.local_path else None
    if root and not root.is_dir():
        root = None
    return resolve_production_url(project, root, fallback)
