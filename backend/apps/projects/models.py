import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220)
    description = models.TextField(blank=True)
    git_url = models.URLField(blank=True)
    """Server-accessible path for scanning (dev agent or mounted volume)."""
    local_path = models.CharField(max_length=500, blank=True)

    framework = models.CharField(max_length=32, default="unknown")
    language = models.CharField(max_length=32, default="unknown")
    scan_data = models.JSONField(default=dict, blank=True)
    last_scanned_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "slug"], name="unique_project_slug_per_owner"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def active_environment(self) -> str:
        scan = self.scan_data or {}
        env = str(scan.get("activeEnvironment") or "production")
        return env if env in ("test", "staging", "production") else "production"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "project"
            slug = base
            n = 1
            while Project.objects.filter(owner=self.owner, slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=64)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.project.slug}:{self.action}"


from apps.projects.api_keys import ProjectApiKey  # noqa: E402, F401
