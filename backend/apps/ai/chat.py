"""Unified AI chat — vault keys only, sanitized prompts."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from apps.projects.models import Project
from apps.vault.models import get_secret

from .services import _assert_safe


def chat_with_ai(project: Project, prompt: str, *, max_tokens: int = 2000) -> tuple[str, str]:
    _assert_safe(prompt)

    anthropic_key = get_secret(project, "ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            return _chat_anthropic(anthropic_key, prompt, max_tokens), "anthropic"
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, RuntimeError, ValueError):
            pass

    openai_key = get_secret(project, "OPENAI_API_KEY")
    if openai_key:
        try:
            return _chat_openai(openai_key, prompt, max_tokens), "openai"
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, RuntimeError, ValueError):
            pass

    raise RuntimeError("No AI provider — store ANTHROPIC_API_KEY or OPENAI_API_KEY in vault")


def _chat_openai(api_key: str, prompt: str, max_tokens: int) -> str:
    body = json.dumps(
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    text = data["choices"][0]["message"]["content"]
    _assert_safe(text)
    return text


def _chat_anthropic(api_key: str, prompt: str, max_tokens: int) -> str:
    body = json.dumps(
        {
            "model": "claude-3-5-haiku-20241022",
            "max_tokens": max_tokens,
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
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    text = data["content"][0]["text"]
    _assert_safe(text)
    return text


def extract_json_block(text: str) -> dict:
    """Parse JSON from AI response (raw object or ```json fence)."""
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
    if fence:
        stripped = fence.group(1).strip()
    return json.loads(stripped)
