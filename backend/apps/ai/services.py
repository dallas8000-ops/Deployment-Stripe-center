"""Sanitized setup recommendations — no secrets cross this boundary."""

from __future__ import annotations

from apps.projects.models import Project

SECRET_PATTERNS = ("sk_", "pk_", "whsec_", "postgresql://", "postgres://", "napi_", "sbp_")


def _assert_safe(text: str) -> None:
    lower = text.lower()
    for pat in SECRET_PATTERNS:
        if pat in lower:
            raise ValueError(f"Unsafe content detected ({pat}) — secrets must not reach AI layer")



def local_recommendations(project: Project) -> str:
    scan = project.scan_data or {}
    framework = project.framework or scan.get("framework") or "unknown"
    language = project.language or scan.get("language") or "unknown"
    features = scan.get("suggestedFeatures") or scan.get("recommendations") or []

    lines = [
        f"# Stripe setup — {project.name}",
        "",
        "## Stack",
        f"- Framework: {framework}",
        f"- Language: {language}",
        "",
        "## Priority steps",
        "1. Store STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY in the vault (write-only)",
        "2. Run verify — confirm live mode matches your environment",
        "3. Run pipeline — provision products, webhook, and generate integration code",
        "4. Set STRIPE_WEBHOOK_SECRET after first webhook registration",
        "5. Run readiness before production deploy",
        "",
    ]
    if features:
        lines.extend(["## Detected recommendations", *[f"- {f}" for f in features[:10]], ""])
    text = "\n".join(lines)
    _assert_safe(text)
    return text
