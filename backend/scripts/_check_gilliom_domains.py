"""Check custom domains on FrontLineDigital-1 Railway service."""
from apps.projects.models import Project
from apps.vault.models import get_secret
from apps.deploy.env_push import _railway_gql, _railway_environment_id
from apps.deploy.railway_resolve import _list_railway_projects_with_domains

HOME_ID = "e5dce2f2-ffc6-4677-8f16-d3912934cebd"
FLD1 = "6592cd9b-10b8-4b0b-9d7f-9d56d4e64365"

p = Project.objects.get(slug="agripay-logistics-ai")
token = get_secret(p, "RAILWAY_API_TOKEN")
env_id = _railway_environment_id(token, HOME_ID)

data = _railway_gql(token, """
query($id: String!) {
  service(id: $id) {
    id name
    serviceInstances { edges { node {
      domains {
        serviceDomains { domain id }
        customDomains { id hostname status { dnsRecords { status } } }
      }
    } } }
  }
}
""", {"id": FLD1})

import json
print(json.dumps(data, indent=2))

print("\n=== ALL DOMAINS IN HEARTY-ENJOYMENT ===")
projects = _list_railway_projects_with_domains(token)
home = next(x for x in projects if x["id"] == HOME_ID)
for s in home.get("services") or []:
    doms = s.get("domains") or []
    if any("gilliom" in d.lower() for d in doms) or "frontline" in (s.get("name") or "").lower():
        print(s.get("name"), "->", doms)
