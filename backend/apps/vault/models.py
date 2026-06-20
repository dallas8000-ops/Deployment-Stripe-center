import logging
from pathlib import Path

from cryptography.exceptions import InvalidTag
from django.db import models
from django.utils import timezone

from apps.projects.models import Project

from .crypto import EncryptedPayload, decrypt_secret, encrypt_secret, generate_salt
from .local_store import (
    delete_secret_from_local,
    load_secret_from_local,
    save_secret_to_local,
    sync_project_from_local_store,
)
from .masking import detect_key_mode, mask_secret_value
from .verification import verify_vault_key

logger = logging.getLogger(__name__)

class ProjectVault(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="vault")
    salt = models.BinaryField()
    initialized_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Vault<{self.project.name}>"


class VaultSecret(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="vault_secrets")
    key_name = models.CharField(max_length=128)
    encrypted_value = models.TextField()
    iv = models.CharField(max_length=64)
    auth_tag = models.CharField(max_length=64)
    display_mask = models.CharField(max_length=64, blank=True)
    key_mode = models.CharField(max_length=16, blank=True, default="unknown")
    verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "key_name"], name="unique_vault_key_per_project"),
        ]
        ordering = ["key_name"]

    def __str__(self) -> str:
        return f"{self.project.slug}:{self.key_name}"

    def to_entry_dict(self, *, readable: bool | None = None) -> dict:
        if readable is None:
            readable = is_secret_readable(self.project, self)
        return {
            "key": self.key_name,
            "display": self.display_mask or "••••••••••••",
            "verified": self.verified,
            "verifiedAt": self.verified_at.isoformat() if self.verified_at else None,
            "verificationMessage": self.verification_message or None,
            "mode": self.key_mode or "unknown",
            "readable": readable,
        }


def get_or_create_vault(project: Project) -> ProjectVault:
    vault, created = ProjectVault.objects.get_or_create(
        project=project,
        defaults={"salt": generate_salt()},
    )
    if created:
        return vault
    return vault


def _apply_verification(secret: VaultSecret, project: Project) -> None:
    verified, message, mode = verify_vault_key(project, secret.key_name)
    secret.verified = verified
    secret.verification_message = message
    secret.key_mode = mode if mode != "unknown" else secret.key_mode
    secret.verified_at = timezone.now() if verified else None


def set_secret(project: Project, key_name: str, plaintext: str) -> VaultSecret:
    secret = _persist_secret(project, key_name, plaintext)
    _apply_verification(secret, project)
    secret.save(update_fields=["verified", "verification_message", "key_mode", "verified_at"])
    return secret


def _persist_secret(project: Project, key_name: str, plaintext: str) -> VaultSecret:
    vault = get_or_create_vault(project)
    payload = encrypt_secret(plaintext, bytes(vault.salt))
    secret, created = VaultSecret.objects.get_or_create(
        project=project,
        key_name=key_name,
        defaults={
            "encrypted_value": payload.encrypted_value,
            "iv": payload.iv,
            "auth_tag": payload.auth_tag,
            "display_mask": mask_secret_value(plaintext),
            "key_mode": detect_key_mode(plaintext),
        },
    )
    if not created:
        secret.encrypted_value = payload.encrypted_value
        secret.iv = payload.iv
        secret.auth_tag = payload.auth_tag
        secret.display_mask = mask_secret_value(plaintext)
        secret.key_mode = detect_key_mode(plaintext)
    secret.save()
    save_secret_to_local(project, secret, bytes(vault.salt))
    return secret


def delete_secret(project: Project, key_name: str) -> bool:
    deleted, _ = VaultSecret.objects.filter(project=project, key_name=key_name).delete()
    if deleted:
        delete_secret_from_local(project, key_name)
    return deleted > 0

def is_secret_readable(project: Project, secret: VaultSecret) -> bool:
    if _decrypt_db_secret(project, secret) is not None:
        return True
    return load_secret_from_local(project, secret.key_name) is not None


def _decrypt_db_secret(project: Project, secret: VaultSecret) -> str | None:
    try:
        vault = project.vault
    except ProjectVault.DoesNotExist:
        return None
    payload = EncryptedPayload(
        encrypted_value=secret.encrypted_value,
        iv=secret.iv,
        auth_tag=secret.auth_tag,
    )
    try:
        return decrypt_secret(payload, bytes(vault.salt))
    except (InvalidTag, ValueError):
        return None

def vault_health(project: Project) -> dict:
    secrets = list(VaultSecret.objects.filter(project=project))
    if not secrets:
        return {"masterKeyValid": True, "unreadableCount": 0, "totalCount": 0}
    unreadable = sum(1 for s in secrets if not is_secret_readable(project, s))
    return {
        "masterKeyValid": unreadable == 0,
        "unreadableCount": unreadable,
        "totalCount": len(secrets),
    }


def get_secret(project: Project, key_name: str) -> str | None:
    try:
        secret = VaultSecret.objects.get(project=project, key_name=key_name)
    except VaultSecret.DoesNotExist:
        secret = None

    if secret is not None:
        value = _decrypt_db_secret(project, secret)
        if value is not None:
            return value

    local_value = load_secret_from_local(project, key_name)
    if local_value is not None:
        _persist_secret(project, key_name, local_value)
        return local_value

    if secret is not None:
        logger.warning(
            "Vault secret %s:%s cannot be decrypted — restore ~/.stripe-installer/projects/%s/vault.json "
            "or re-enter the key",
            project.slug,
            key_name,
            project.slug,
        )
    return None


def hydrate_project_vault(project: Project) -> list[str]:
    """Pull secrets from ~/.stripe-installer, legacy CLI vault, and project env files."""
    from .secret_sources import import_all_discovered_secrets, resolve_project_root

    if not resolve_project_root(project) and not list_local_secret_keys(project.slug):
        return sync_project_from_local_store(project)

    result = import_all_discovered_secrets(
        project,
        include_legacy=False,
        include_env=True,
        only_if_needed=True,
    )
    return result.get("imported", [])

def list_secret_keys(project: Project) -> list[str]:
    return list(
        VaultSecret.objects.filter(project=project).values_list("key_name", flat=True)
    )


def list_vault_entries(project: Project) -> list[dict]:
    return [s.to_entry_dict() for s in VaultSecret.objects.filter(project=project)]