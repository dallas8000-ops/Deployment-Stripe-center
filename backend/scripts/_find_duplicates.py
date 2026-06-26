"""Detect duplicate / stale Railway services in hearty-enjoyment."""
import re
from apps.projects.models import Project
from apps.vault.models import get_secret
from apps.deploy.railway_deploy import railway_service_repo
from apps.deploy.railway_resolve import _list_railway_projects_with_domains
from apps.stripe_core.portfolio_catalog import PORTFOLIO_CATALOG

HOME_ID = "e5dce2f2-ffc6-4677-8f16-d3912934cebd"

# Canonical production host per app (from hub catalog).
CATALOG_HOSTS: dict[str, str] = {}
for entry in PORTFOLIO_CATALOG:
    host = (entry.get("productionUrl") or "").split("//", 1)[-1].split("/")[0].lower()
    slug = entry.get("projectSlug") or entry.get("id") or ""
    if host and slug:
        CATALOG_HOSTS[slug.lower()] = host

# Known pairs: api + web are NOT duplicates.
INTENTIONAL_PAIRS = {
    "dbops": {"dbops-api", "dbops-web"},
    "specwright": {"specwright-api", "specwright-web"},
    "elite-fintech": {"elite-fintech-systems-api", "elite-fintech-systems-web", "elite-fintech-systems-db"},
    "righand": {"righand", "righand-frontend"},
    "enpower": {"enpowercommand", "enpower-command-web"},
}

def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

p = Project.objects.get(slug="agripay-logistics-ai")
token = get_secret(p, "RAILWAY_API_TOKEN")
projects = _list_railway_projects_with_domains(token)
home = next(x for x in projects if x["id"] == HOME_ID)
services = home.get("services") or []

print("=== LIKELY DUPLICATES (same app, two services) ===")
dup_groups = [
    ("React Store Catalog", ["react-store-catalog", "react-store-catalog-1"], "react-store-catalog"),
    ("FrontLine Digital", ["frontlinedigital", "frontlinedigital-1"], None),
    ("EnPower", ["enpowercommand", "enpower-command-web"], "enpowercommand"),
]

for label, names, catalog_slug in dup_groups:
    print(f"\n{label}:")
    canonical_host = CATALOG_HOSTS.get((catalog_slug or "").lower(), "")
    for svc in services:
        n = norm(svc.get("name"))
        if any(norm(x) == n or norm(x) in n for x in names):
            doms = svc.get("domains") or []
            primary = doms[0] if doms else "(no domain)"
            repo = railway_service_repo(token, svc["id"])
            has_catalog = any(canonical_host and canonical_host in d.lower() for d in doms) if canonical_host else False
            tag = "KEEP (catalog)" if has_catalog else ("STALE?" if doms else "NO DOMAIN")
            print(f"  {tag}: {svc.get('name')} | repo={repo.get('repo') or 'none'} | {primary}")

print("\n=== ORPHAN / JUNK ===")
for svc in services:
    n = (svc.get("name") or "").lower()
    doms = svc.get("domains") or []
    if n in ("token-probe-temp", "alert-perception", "postgres") and not doms:
        print(f"  {svc.get('name')} | {svc.get('id')} | no domain")

print("\n=== CATALOG HOST MATCH ===")
for svc in services:
    doms = [d.lower() for d in (svc.get("domains") or [])]
    if not doms:
        continue
    matched = [slug for slug, host in CATALOG_HOSTS.items() if any(host in d or d.startswith(host.split('.')[0]) for d in doms)]
    if matched:
        print(f"  {svc.get('name')} -> {matched}")
