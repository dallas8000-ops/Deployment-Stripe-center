"""List all Railway projects and hearty-enjoyment services."""
from apps.projects.models import Project
from apps.vault.models import get_secret
from apps.deploy.railway_resolve import _list_railway_projects_with_domains

HOME_ID = "e5dce2f2-ffc6-4677-8f16-d3912934cebd"

p = Project.objects.get(slug="agripay-logistics-ai")
token = get_secret(p, "RAILWAY_API_TOKEN")
projects = _list_railway_projects_with_domains(token)

print("=== ALL RAILWAY PROJECTS ===")
for proj in sorted(projects, key=lambda x: (x.get("name") or "").lower()):
    svcs = proj.get("services") or []
    print(proj.get("name"), "|", proj.get("id"), "|", len(svcs), "services")

print()
print("=== HEARTY-ENJOYMENT ALL SERVICES ===")
home = next(x for x in projects if x["id"] == HOME_ID)
for s in sorted(home.get("services") or [], key=lambda x: (x.get("name") or "").lower()):
    doms = ", ".join(s.get("domains") or []) or "(no domain)"
    print(s.get("name"), "|", s.get("id"), "|", doms)
