"""Deploy platform detection — port of legacy deploy/platform-detector.ts."""

from __future__ import annotations

import json
import re
from pathlib import Path

from apps.projects.models import Project

PLATFORMS = ("vercel", "railway", "fly", "docker", "unknown")


def detect_deploy_platform(
    project_root: Path,
    framework: str = "unknown",
    *,
    production_url: str = "",
) -> str:
    root = project_root.resolve()
    prod = (production_url or "").lower()
    if ".railway.app" in prod or "railway.app" in prod:
        return "railway"

    for candidate in (root, *root.parents):
        if candidate == candidate.parent:
            break
        if (candidate / "railway.json").is_file() or (candidate / "railway.toml").is_file():
            return "railway"
        if (candidate / "vercel.json").is_file() or (candidate / ".vercel").is_dir():
            return "vercel"
        if (candidate / "fly.toml").is_file():
            return "fly"

    if (root / "Dockerfile").is_file():
        return "docker"

    if framework == "nextjs":
        return "vercel"

    pkg_path = root / "package.json"
    if pkg_path.is_file():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
            deps = pkg.get("dependencies") or {}
            scripts = pkg.get("scripts") or {}
            if "@railway/cli" in deps or "railway" in str(scripts.get("deploy", "")):
                return "railway"
            if "vercel" in str(scripts.get("deploy", "")):
                return "vercel"
        except (json.JSONDecodeError, OSError):
            pass

    if framework == "django":
        return "railway"
    return "unknown"


def platform_deploy_command(platform: str) -> str:
    return {
        "vercel": "vercel --prod",
        "railway": "railway up",
        "fly": "fly deploy",
        "docker": "docker build -t app . && docker run -p 3000:3000 --env-file .env.production app",
    }.get(platform, "npm run build && npm start")


def health_check_path(framework: str) -> str:
    if framework in ("nextjs", "remix", "nuxt", "sveltekit", "react"):
        return "/api/health"
    if framework == "django":
        return "/health/"
    return "/stripe/health"


def framework_build_command(framework: str) -> str:
    if framework in ("django", "flask"):
        return "pip install -r requirements.txt"
    if framework == "rails":
        return "bundle install"
    if framework == "laravel":
        return "composer install --no-dev --optimize-autoloader"
    return "npm ci && npm run build"


_DJANGO_SETTINGS_RX = re.compile(r"""DJANGO_SETTINGS_MODULE["']\s*,\s*["']([\w.]+)["']""")


def resolve_django_wsgi_module(app_root: Path) -> str | None:
    """Dotted WSGI module (e.g. ``config.wsgi``) for the Django project rooted at ``app_root``.

    Reads DJANGO_SETTINGS_MODULE from manage.py and walks up the dotted path until a
    ``wsgi.py`` exists (handles ``config.settings`` and ``config.settings.production``).
    Falls back to a single unambiguous ``*/wsgi.py``. Returns None when it cannot be
    determined -- callers must then skip generating a start command rather than guess.
    """
    manage = app_root / "manage.py"
    if manage.is_file():
        match = _DJANGO_SETTINGS_RX.search(manage.read_text(encoding="utf-8", errors="ignore"))
        if match:
            parts = match.group(1).split(".")[:-1]
            while parts:
                if (app_root.joinpath(*parts) / "wsgi.py").is_file():
                    return ".".join(parts) + ".wsgi"
                parts = parts[:-1]
    candidates = [p for p in app_root.glob("*/wsgi.py") if p.is_file()]
    if len(candidates) == 1:
        return f"{candidates[0].parent.name}.wsgi"
    return None


def framework_start_command(framework: str, *, wsgi_module: str | None = None) -> str | None:
    """Production start command, or None when it cannot be derived safely.

    Django needs the project's real WSGI module; there is no safe default
    (a guessed module name crash-loops the deploy).
    """
    if framework == "django":
        if not wsgi_module:
            return None
        return f"gunicorn {wsgi_module}:application --bind 0.0.0.0:$PORT"
    return {
        "nextjs": "npm run start",
        "nuxt": "node .output/server/index.mjs",
        "express": "node dist/server.js",
        "fastify": "node dist/server.js",
        "react": "node dist/server.js",
        "flask": "gunicorn app:app --bind 0.0.0.0:$PORT",
        "rails": "bundle exec rails server -p $PORT -e production",
        "laravel": "php artisan serve --host=0.0.0.0 --port=$PORT",
    }.get(framework, "npm start")


def webhook_path_for(framework: str, next_router: str | None = None) -> str:
    if framework == "nextjs":
        return "/api/stripe/webhook" if next_router != "pages" else "/api/stripe/webhook"
    if framework == "django":
        return "/webhooks/stripe/"
    if framework == "express":
        return "/stripe/webhook"
    return "/api/stripe/webhook"


def production_env_example(framework: str, prod_url: str) -> str:
    is_next = framework == "nextjs"
    app_key = "NEXT_PUBLIC_APP_URL" if is_next else "APP_URL"
    pub_line = "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_\n" if is_next else ""
    return (
        f"NODE_ENV=production\n"
        f"{app_key}={prod_url}\n"
        f"STRIPE_SECRET_KEY=sk_live_\n"
        f"STRIPE_PUBLISHABLE_KEY=pk_live_\n"
        f"{pub_line}"
        f"STRIPE_WEBHOOK_SECRET=whsec_\n"
        f"DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require\n"
    )


def generate_dockerfile(framework: str, *, wsgi_module: str | None = None) -> str | None:
    """Dockerfile for the app, or None when a correct one cannot be generated."""
    start = framework_start_command(framework, wsgi_module=wsgi_module)
    if start is None:
        return None
    templates = {
        "django": f"""FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
ENV PORT=8000
CMD gunicorn {wsgi_module}:application --bind 0.0.0.0:${{PORT}}
""",
        "flask": """FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
ENV PORT=5000
CMD gunicorn app:app --bind 0.0.0.0:${PORT}
""",
        "express": """FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
ENV PORT=3000
CMD node dist/server.js
""",
    }
    if framework in templates:
        return templates[framework]
    return f"""FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
ENV PORT=3000
EXPOSE 3000
CMD {start}
"""
