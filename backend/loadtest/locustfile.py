"""
Load test harness for N-replica web behavior.

Install:
  pip install -r backend/loadtest/requirements.txt

Run (against local or staging):
  cd backend
  locust -f loadtest/locustfile.py --host http://127.0.0.1:8000

Headless smoke (100 users, 30s):
  locust -f loadtest/locustfile.py --host https://your-domain --headless -u 100 -r 10 -t 30s

Optional auth (projects list):
  set LOADTEST_JWT=<access token>
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task


class AutomationCenterUser(HttpUser):
    wait_time = between(0.2, 1.0)

    def on_start(self):
        token = os.environ.get("LOADTEST_JWT", "").strip()
        if token:
            self.client.headers["Authorization"] = f"Bearer {token}"

    @task(5)
    def health(self):
        self.client.get("/health/", name="/health/")

    @task(3)
    def readiness(self):
        self.client.get("/health/ready/", name="/health/ready/")

    @task(2)
    def root(self):
        self.client.get("/", name="/")

    @task(1)
    def projects_list(self):
        if not os.environ.get("LOADTEST_JWT"):
            return
        self.client.get("/api/v1/projects/", name="/api/v1/projects/")
