"""Optional OpenAI / Anthropic providers — secrets from project vault only."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from apps.projects.models import Project
from apps.vault.models import get_secret

from .services import _assert_safe, local_recommendations


def _chat_openai(api_key: str, prompt: str) -> str:
    body = json.dumps(
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1500,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode())
    text = data["choices"][0]["message"]["content"]
    _assert_safe(text)
    return text


def _chat_anthropic(api_key: str, prompt: str) -> str:
    body = json.dumps(
        {
            "model": "claude-3-5-haiku-20241022",
            "max_tokens": 1500,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode())
    text = data["content"][0]["text"]
    _assert_safe(text)
    return text


def _build_prompt(project: Project) -> str:
    base = local_recommendations(project)
    return (
        "You are a Stripe integration expert. Analyze this SANITIZED project profile "
        "and provide actionable setup guidance. Never ask for API keys.\n\n"
        f"{base}\n\n"
        "Provide: priority steps, security notes, recommended Stripe features, testing checklist."
    )


def generate_recommendations(project: Project) -> tuple[str, str]:
    prompt = _build_prompt(project)
    _assert_safe(prompt)

    anthropic_key = get_secret(project, "ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            return _chat_anthropic(anthropic_key, prompt), "anthropic"
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, RuntimeError):
            pass

    openai_key = get_secret(project, "OPENAI_API_KEY")
    if openai_key:
        try:
            return _chat_openai(openai_key, prompt), "openai"
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, RuntimeError):
            pass

    return local_recommendations(project), "local"
