"""Resolve dedicated Railway Postgres per portfolio preset (keeps storefront DBs off the hub DB)."""

from __future__ import annotations

from .env_push import is_placeholder_database_url, is_railway_reference

# Railway Postgres plugin name per hub env preset — automation picks this, not manual dashboard edits.
RAILWAY_POSTGRES_SERVICE_BY_PRESET: dict[str, str] = {
    "kistie-store": "Postgres",
    "silverfox": "PostgreSQL-silverfox",
    "stripe-installer": "Postgres-rDf6",
    "righand": "Postgres",
}

# Projects that use the shared Postgres plugin but have no preset — looked up by slug.
RAILWAY_POSTGRES_SERVICE_BY_SLUG: dict[str, str] = {
    "righand": "Postgres",
}

# Literal DATABASE_URL hosts a preset must never keep (wrong shared database).
BLOCKED_DATABASE_HOSTS_BY_PRESET: dict[str, tuple[str, ...]] = {
    "kistie-store": ("postgres-rdf6.railway.internal",),
}


def postgres_service_for_preset(preset: str | None) -> str | None:
    key = (preset or "").strip().lower()
    return RAILWAY_POSTGRES_SERVICE_BY_PRESET.get(key)


def postgres_service_for_slug(slug: str | None) -> str | None:
    key = (slug or "").strip().lower()
    return RAILWAY_POSTGRES_SERVICE_BY_SLUG.get(key)


def postgres_reference_for_service(service_name: str) -> str:
    return "${{" + service_name.strip() + ".DATABASE_URL}}"


def postgres_reference_for_preset(preset: str | None, *, slug: str | None = None) -> str | None:
    service_name = postgres_service_for_preset(preset) or postgres_service_for_slug(slug)
    if not service_name:
        return None
    return postgres_reference_for_service(service_name)


def database_url_should_be_replaced(
    existing_db: str,
    incoming_value: str,
    *,
    preset: str | None = None,
    slug: str | None = None,
) -> bool:
    """True when Railway should accept incoming DATABASE_URL over the stored literal URL."""
    existing = (existing_db or "").strip()
    incoming = (incoming_value or "").strip()
    if not incoming:
        return False
    if is_placeholder_database_url(existing):
        return True
    if not existing:
        return True
    if "@:5432" in existing or "@localhost" in existing:
        return True
    # Always allow a reference variable to replace a literal URL for slugs that own
    # their Postgres via RAILWAY_POSTGRES_SERVICE_BY_SLUG (e.g. righand).
    if is_railway_reference(incoming) and existing.lower().startswith(("postgres://", "postgresql://")):
        slug_key = (slug or "").strip().lower()
        if slug_key and slug_key in RAILWAY_POSTGRES_SERVICE_BY_SLUG:
            return True
    preset_key = (preset or "").strip().lower()
    blocked = BLOCKED_DATABASE_HOSTS_BY_PRESET.get(preset_key, ())
    if blocked and existing.lower().startswith(("postgres://", "postgresql://")):
        lower = existing.lower()
        if any(host in lower for host in blocked) and is_railway_reference(incoming):
            return True
    return False
