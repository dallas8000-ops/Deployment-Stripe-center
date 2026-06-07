"""Port of Node project-scanner — filesystem framework detection."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

FRAMEWORK_SIGNALS: dict[str, list[str]] = {
    "nextjs": ["next.config", "app/layout", "pages/_app"],
    "react": ["src/App.tsx", "src/App.jsx", "vite.config"],
    "express": ["express", "app.listen"],
    "fastify": ["fastify"],
    "remix": ["remix.config", "@remix-run"],
    "nuxt": ["nuxt.config"],
    "sveltekit": ["svelte.config", "@sveltejs/kit"],
    "django": ["manage.py", "settings.py"],
    "flask": ["flask", "app.py"],
    "rails": ["config/routes.rb", "Gemfile"],
    "laravel": ["artisan", "composer.json"],
}

SECRET_PATTERNS = [
    (re.compile(r"sk_(test|live)_[a-zA-Z0-9]+"), "STRIPE_SECRET_KEY"),
    (re.compile(r"pk_(test|live)_[a-zA-Z0-9]+"), "STRIPE_PUBLISHABLE_KEY"),
    (re.compile(r"whsec_[a-zA-Z0-9]+"), "STRIPE_WEBHOOK_SECRET"),
]


@dataclass
class ScanResult:
    framework: str = "unknown"
    language: str = "unknown"
    next_router: str | None = None
    has_package_json: bool = False
    has_env_file: bool = False
    env_files: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)
    existing_stripe_code: bool = False
    suggested_features: list[str] = field(default_factory=list)
    detected_secrets: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    source_file_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class ProjectScanner:
    def __init__(self, root_path: str | Path) -> None:
        self.root = Path(root_path).resolve()

    def scan(self) -> ScanResult:
        if not self.root.is_dir():
            raise FileNotFoundError(f"Project path not found: {self.root}")

        package_json = self._read_package_json()
        source_files = self._find_source_files()
        env_files = self._find_env_files()

        framework = self._detect_framework(package_json, source_files)
        language = self._detect_language(package_json, source_files)
        next_router = self._detect_next_router() if framework == "nextjs" else None

        deps = list((package_json or {}).get("dependencies", {}).keys())
        dev_deps = list((package_json or {}).get("devDependencies", {}).keys())

        existing_stripe, secrets = self._scan_secrets(source_files[:50] + env_files)
        features = self._infer_features(deps, existing_stripe)
        recommendations = self._recommendations(framework, language, existing_stripe, env_files, features)

        return ScanResult(
            framework=framework,
            language=language,
            next_router=next_router,
            has_package_json=package_json is not None,
            has_env_file=len(env_files) > 0,
            env_files=env_files,
            dependencies=deps,
            dev_dependencies=dev_deps,
            existing_stripe_code=existing_stripe,
            suggested_features=features,
            detected_secrets=secrets,
            recommendations=recommendations,
            source_file_count=len(source_files),
        )

    def _read_package_json(self) -> dict | None:
        path = self.root / "package.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _find_env_files(self) -> list[str]:
        files: list[str] = []
        for p in self.root.rglob(".env*"):
            if "node_modules" in p.parts or ".stripe-installer" in p.parts:
                continue
            files.append(str(p.relative_to(self.root)).replace("\\", "/"))
        return files[:20]

    def _find_source_files(self) -> list[str]:
        patterns = ("*.ts", "*.tsx", "*.js", "*.jsx", "*.py", "*.rb", "*.php")
        found: set[str] = set()
        for pattern in patterns:
            for p in self.root.rglob(pattern):
                if any(x in p.parts for x in ("node_modules", "dist", ".stripe-installer", "venv")):
                    continue
                if len(p.relative_to(self.root).parts) > 8:
                    continue
                found.add(str(p.relative_to(self.root)).replace("\\", "/"))
        for name in ("package.json", "requirements.txt", "Gemfile", "composer.json", "manage.py"):
            if (self.root / name).is_file():
                found.add(name)
        return sorted(found)[:200]

    def _file_exists(self, relative: str) -> bool:
        return (self.root / relative).is_file()

    def _detect_framework(self, package_json: dict | None, source_files: list[str]) -> str:
        deps = {}
        if package_json:
            deps.update(package_json.get("dependencies") or {})
            deps.update(package_json.get("devDependencies") or {})

        if deps.get("next"):
            return "nextjs"
        if deps.get("@remix-run/react"):
            return "remix"
        if deps.get("nuxt") or deps.get("nuxt3"):
            return "nuxt"
        if deps.get("@sveltejs/kit"):
            return "sveltekit"
        if deps.get("express"):
            return "express"
        if deps.get("fastify"):
            return "fastify"
        if self._file_exists("manage.py"):
            return "django"
        if self._file_exists("config/routes.rb"):
            return "rails"
        if self._file_exists("artisan"):
            return "laravel"
        if deps.get("react") or deps.get("react-dom"):
            return "react"

        for framework, signals in FRAMEWORK_SIGNALS.items():
            if framework == "unknown":
                continue
            for signal in signals:
                if any(signal in f for f in source_files):
                    return framework
        return "unknown"

    def _detect_language(self, package_json: dict | None, source_files: list[str]) -> str:
        if any(f.endswith((".ts", ".tsx")) for f in source_files):
            return "typescript"
        if package_json or any(f.endswith((".js", ".jsx")) for f in source_files):
            return "javascript"
        if any(f.endswith(".py") for f in source_files):
            return "python"
        if any(f.endswith(".rb") for f in source_files):
            return "ruby"
        if any(f.endswith(".php") for f in source_files):
            return "php"
        return "unknown"

    def _detect_next_router(self) -> str | None:
        if self._file_exists("app/layout.tsx") or self._file_exists("app/layout.js"):
            return "app"
        if self._file_exists("pages/_app.tsx") or self._file_exists("pages/_app.js"):
            return "pages"
        return "unknown"

    def _scan_secrets(self, files: list[str]) -> tuple[bool, list[dict]]:
        secrets: list[dict] = []
        existing_stripe = False
        for rel in files:
            path = self.root / rel
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"stripe", content, re.I) or "from 'stripe'" in content or 'from "stripe"' in content:
                existing_stripe = True
            for pattern, key in SECRET_PATTERNS:
                if pattern.search(content):
                    secrets.append({"key": key, "file": rel, "placeholder": "[REDACTED]"})
        return existing_stripe, secrets

    def _infer_features(self, dependencies: list[str], existing_stripe: bool) -> list[str]:
        features: set[str] = set()
        if "stripe" in dependencies:
            features.add("webhooks")
        if "@stripe/stripe-js" in dependencies:
            features.add("checkout")
        if not existing_stripe:
            features.update(["checkout", "subscriptions", "webhooks", "billing-portal"])
        elif not features:
            features.update(["checkout", "subscriptions", "webhooks", "billing-portal"])
        return sorted(features)

    def _recommendations(
        self,
        framework: str,
        language: str,
        existing_stripe: bool,
        env_files: list[str],
        features: list[str],
    ) -> list[str]:
        recs: list[str] = []
        if not existing_stripe:
            recs.append("No existing Stripe integration detected — greenfield setup recommended.")
        else:
            recs.append("Existing Stripe code found — incremental setup to avoid overwriting.")
        if not env_files:
            recs.append("Create a .env.local file for Stripe keys — never commit secrets.")
        if framework == "django":
            recs.append("Use server-rendered Django templates for SEO-friendly billing pages.")
        elif framework == "nextjs":
            recs.append("Keep STRIPE_SECRET_KEY server-side only.")
        if "subscriptions" in features:
            recs.append("Enable Stripe Billing and Customer Portal for self-service.")
        recs.append("Store all secrets in the encrypted vault — never pass to AI prompts.")
        return recs
