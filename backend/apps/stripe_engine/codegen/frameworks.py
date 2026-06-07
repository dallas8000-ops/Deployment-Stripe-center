"""Framework capabilities for codegen."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameworkProfile:
    framework: str
    codegen: str  # full | minimal | none
    webhook_path: str
    display_name: str


CAPABILITIES: dict[str, FrameworkProfile] = {
    "nextjs": FrameworkProfile("nextjs", "full", "/api/stripe/webhook", "Next.js"),
    "express": FrameworkProfile("express", "full", "/stripe/webhook", "Express"),
    "fastify": FrameworkProfile("fastify", "full", "/stripe/webhook", "Fastify"),
    "remix": FrameworkProfile("remix", "full", "/api/stripe/webhook", "Remix"),
    "react": FrameworkProfile("react", "none", "/stripe/webhook", "React (SPA)"),
    "nuxt": FrameworkProfile("nuxt", "full", "/api/stripe/webhook", "Nuxt"),
    "sveltekit": FrameworkProfile("sveltekit", "full", "/api/stripe/webhook", "SvelteKit"),
    "django": FrameworkProfile("django", "full", "/stripe/webhook", "Django"),
    "flask": FrameworkProfile("flask", "full", "/stripe/webhook", "Flask"),
    "rails": FrameworkProfile("rails", "full", "/stripe/webhook", "Rails"),
    "laravel": FrameworkProfile("laravel", "full", "/stripe/webhook", "Laravel"),
    "unknown": FrameworkProfile("unknown", "minimal", "/stripe/webhook", "Unknown"),
}


def get_profile(framework: str) -> FrameworkProfile:
    return CAPABILITIES.get(framework, CAPABILITIES["unknown"])
