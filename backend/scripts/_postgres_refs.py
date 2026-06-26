"""Find which hearty-enjoyment services reference each Postgres plugin."""
from apps.projects.models import Project
from apps.vault.models import get_secret
from apps.deploy.env_push import _railway_environment_id, get_railway_env_vars
from apps.deploy.railway_resolve import _list_railway_projects_with_domains

HOME_ID = "e5dce2f2-ffc6-4677-8f16-d3912934cebd"

p = Project.objects.get(slug="agripay-logistics-ai")
token = get_secret(p, "RAILWAY_API_TOKEN")
projects = _list_railway_projects_with_domains(token)
home = next(x for x in projects if x["id"] == HOME_ID)
env_id = _railway_environment_id(token, HOME_ID)

print("DATABASE_URL references in hearty-enjoyment:")
for svc in sorted(home.get("services") or [], key=lambda x: (x.get("name") or "").lower()):
    name = svc.get("name") or ""
    if "postgres" in name.lower() and "redis" not in name.lower():
        continue
    vars_map = get_railway_env_vars(token, HOME_ID, svc["id"], env_id)
    db = (vars_map.get("DATABASE_URL") or "").strip()
    if not db:
        continue
    if db.startswith("${{"):
        print(f"  {name} -> {db}")
    else:
        print(f"  {name} -> (literal url, len={len(db)})")
