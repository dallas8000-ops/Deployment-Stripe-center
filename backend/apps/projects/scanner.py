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
    (re.compile(r"sk_(test|live)_[a-zA-Z0-9]{24,}"), "STRIPE_SECRET_KEY"),
    (re.compile(r"pk_(test|live)_[a-zA-Z0-9]{24,}"), "STRIPE_PUBLISHABLE_KEY"),
    (re.compile(r"whsec_[a-zA-Z0-9]{24,}"), "STRIPE_WEBHOOK_SECRET"),
]

_TEST_FILE_PATTERNS = re.compile(r"(^|[\\/])(test_|tests[\\/]|__tests__[\\/]|spec[\\/])", re.I)

# Detects the Stripe webhook route path registered in the codebase.
# Only matches actual view/handler registrations — not include() mounts.
_WEBHOOK_ROUTE_PATTERNS = [
    # Django: path("webhook", SomeView) — must NOT be followed by include(
    re.compile(r'path\(["\']([^"\']*(?:stripe|billing|webhook)[^"\']*)["\'](?!.*include\()', re.I),
    # Express / Fastify: app.post("/stripe/webhook", handler)
    re.compile(r'\.post\(["\']([^"\']*(?:stripe|billing|webhook)[^"\']*)["\']', re.I),
    # Generic route registration
    re.compile(r'route\(["\']([^"\']*(?:stripe|billing|webhook)[^"\']*)["\']', re.I),
]
_WEBHOOK_NEXTJS_DIRS = [
    "app/api/stripe/webhook",
    "app/api/billing/webhook",
    "app/api/webhooks/stripe",
    "pages/api/stripe/webhook",
    "pages/api/billing/webhook",
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
    webhook_path: str | None = None

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
        webhook_path = self._detect_webhook_path(source_files)

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
            webhook_path=webhook_path,
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
                if any(x in p.parts for x in ("node_modules", "dist", ".stripe-installer", "venv", ".venv", "__pycache__", ".tox", "site-packages")):
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

    def _detect_webhook_path(self, source_files: list[str]) -> str | None:
        # Next.js: route file at a known webhook directory
        for dir_path in _WEBHOOK_NEXTJS_DIRS:
            for ext in ("route.ts", "route.js"):
                if self._file_exists(f"{dir_path}/{ext}"):
                    stem = dir_path.split("app/", 1)[-1].split("pages/", 1)[-1]
                    return f"/{stem}"

        # Find view names that actually verify Stripe signatures — most reliable signal
        webhook_views = self._find_webhook_view_names(source_files)
        prefix_map = self._build_url_prefix_map(source_files)
        url_files = [
            f for f in source_files
            if any(n in f.lower() for n in ("urls.py", "routes.py", "router"))
        ]

        # First pass: url files that reference a known Stripe webhook view
        for rel in url_files[:20]:
            result = self._extract_webhook_segment(rel, prefix_map, webhook_views)
            if result:
                return result
        # Second pass: any webhook-named path (no view filter)
        for rel in url_files[:20]:
            result = self._extract_webhook_segment(rel, prefix_map, None)
            if result:
                return result
        return None

    _SIG_RE = re.compile(r"construct_event|STRIPE_WEBHOOK_SECRET", re.I)
    _NAME_RE = re.compile(r"class\s+(\w+)|def\s+(\w+)")

    def _find_webhook_view_names(self, source_files: list[str]) -> set[str]:
        """Return class/function names from files that verify Stripe webhook signatures."""
        views: set[str] = set()
        for rel in source_files[:100]:
            if _TEST_FILE_PATTERNS.search(rel):
                continue
            content = self._read_file(rel)
            if content is None or not self._SIG_RE.search(content):
                continue
            for m in self._NAME_RE.finditer(content):
                name = m.group(1) or m.group(2)
                if name:
                    views.add(name)
        return views

    _DJANGO_INCLUDE_PAT = re.compile(
        r'path\(["\']([^"\']+)["\'].*include\(["\']([^"\']+)["\']', re.I
    )
    _FASTAPI_ROUTER_PAT = re.compile(
        r'include_router\((\w+)\.router.*prefix=["\']([^"\']+)["\']', re.I
    )

    def _read_file(self, rel: str) -> str | None:
        path = self.root / rel
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

    def _django_prefixes(self, content: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for m in self._DJANGO_INCLUDE_PAT.finditer(content):
            prefix, module = m.group(1).strip("/"), m.group(2)
            module_name = module.split(".")[-2] if "." in module else module
            result[module_name] = prefix
        return result

    def _fastapi_prefixes(self, content: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for m in self._FASTAPI_ROUTER_PAT.finditer(content):
            result[m.group(1)] = m.group(2).strip("/")
        return result

    def _build_url_prefix_map(self, source_files: list[str]) -> dict[str, str]:
        """Map module names to their URL prefixes from include()/include_router() declarations."""
        prefix_map: dict[str, str] = {}
        for rel in source_files:
            rel_lower = rel.lower()
            is_url_file = "urls" in rel_lower
            is_main_file = rel_lower.endswith(("main.py", "app.py"))
            if not (is_url_file or is_main_file):
                continue
            content = self._read_file(rel)
            if content is None:
                continue
            if is_url_file:
                prefix_map.update(self._django_prefixes(content))
            if is_main_file:
                prefix_map.update(self._fastapi_prefixes(content))
        return prefix_map

    _APIROUTER_PREFIX_PAT = re.compile(r'APIRouter\(.*prefix=["\']([^"\']+)["\']', re.I)

    def _url_prefix(self, rel: str, prefix_map: dict[str, str], content: str = "") -> str:
        normalized = rel.replace("\\", "/")
        module_name = normalized.split("/")[-1].removesuffix(".py").removesuffix("/urls")
        parent_dir = normalized.split("/")[-2] if "/" in normalized else ""
        _known = ("stripe", "billing", "payments")
        outer = (
            prefix_map.get(module_name)
            or prefix_map.get(parent_dir)
            or (module_name if module_name in _known else "")
            or (parent_dir if parent_dir in _known else "")
        )
        # For FastAPI router files, combine outer mount prefix with router's own prefix
        if content and outer:
            m = self._APIROUTER_PREFIX_PAT.search(content)
            if m:
                own = m.group(1).strip("/")
                if own and own not in outer:
                    return f"{outer}/{own}"
        return outer

    def _view_matches(self, match: re.Match, webhook_views: set[str]) -> bool:
        context = match.string[match.start(): match.end() + 200]
        return any(v in context for v in webhook_views)

    def _extract_webhook_segment(
        self,
        rel: str,
        prefix_map: dict[str, str],
        webhook_views: set[str] | None = None,
    ) -> str | None:
        content = self._read_file(rel)
        if content is None:
            return None
        prefix = self._url_prefix(rel, prefix_map, content)
        for pattern in _WEBHOOK_ROUTE_PATTERNS:
            for match in pattern.finditer(content):
                segment = match.group(1).strip("/")
                if "webhook" not in segment.lower():
                    continue
                if webhook_views and not self._view_matches(match, webhook_views):
                    continue
                full = f"{prefix}/{segment}".strip("/") if prefix else segment
                return f"/{full}"
        return None

    def _scan_secrets(self, files: list[str]) -> tuple[bool, list[dict]]:
        secrets: list[dict] = []
        existing_stripe = False
        for rel in files:
            if _TEST_FILE_PATTERNS.search(rel):
                continue
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
        if not existing_stripe or not features:
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
