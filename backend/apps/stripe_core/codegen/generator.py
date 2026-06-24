"""Jinja2 code generator — port of code-generator.ts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .context import build_context, lib_dir
from .frameworks import get_profile

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(enabled_extensions=("html", "j2")),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)
# TSX/Vue/Svelte use {{ }} — alternate delimiters avoid clashes with Jinja2
_ts_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    variable_start_string="[[",
    variable_end_string="]]",
    block_start_string="[%",
    block_end_string="%)",
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def _render(name: str, ctx: dict[str, Any]) -> str:
    return _env.get_template(name).render(**ctx)


def _render_ts(name: str, ctx: dict[str, Any]) -> str:
    return _ts_env.get_template(name).render(**ctx)


def generate_all(
    framework: str,
    manifest: dict | None = None,
    *,
    app_url: str = "http://localhost:8000",
    next_router: str | None = None,
) -> dict[str, str]:
    profile = get_profile(framework)
    ctx = build_context(
        framework=framework,
        manifest=manifest,
        app_url=app_url,
        next_router=next_router,
    )
    ctx["lib"] = lib_dir(framework)
    ctx["profile"] = profile

    if profile.codegen == "none":
        return {
            "docs/STRIPE-SETUP.md": _render("docs/setup_manual.md.j2", ctx),
            ".env.example": _render("shared/env.example.md.j2", ctx),
        }

    generators = {
        "django": _generate_django,
        "flask": _generate_flask,
        "express": _generate_express,
        "fastify": _generate_fastify,
        "nextjs": _generate_nextjs,
        "remix": _generate_remix,
        "nuxt": _generate_nuxt,
        "sveltekit": _generate_sveltekit,
        "rails": _generate_rails,
        "laravel": _generate_laravel,
    }

    gen = generators.get(framework, _generate_minimal)
    return gen(ctx)


def _generate_django(ctx: dict[str, Any]) -> dict[str, str]:
    return {
        "stripe/__init__.py": "",
        "stripe/client.py": _render("django/client.py.j2", ctx),
        "stripe/db.py": _render("django/db.py.j2", ctx),
        "stripe/webhook_handlers.py": _render("django/webhook_handlers.py.j2", ctx),
        "stripe/views.py": _render("django/views.py.j2", ctx),
        "stripe/urls.py": _render("django/urls.py.j2", ctx),
        "stripe/templates/stripe/pricing.html": _render("django/pricing.html.j2", ctx),
        "stripe/templates/stripe/success.html": _render("django/success.html.j2", ctx),
        "stripe/templates/stripe/account.html": _render("django/account.html.j2", ctx),
        "db/schema.sql": _render("shared/schema.sql.j2", ctx),
        "docs/STRIPE-DJANGO.md": _render("docs/django_setup.md.j2", ctx),
        "docs/STRIPE-AUTH.md": _render("docs/django_auth.md.j2", ctx),
        ".env.example": _render("shared/env.python.md.j2", ctx),
    }


def _generate_flask(ctx: dict[str, Any]) -> dict[str, str]:
    files = {
        "stripe_routes.py": _render("flask/routes.py.j2", ctx),
        "templates/stripe/pricing.html": _render("flask/pricing.html.j2", ctx),
        "templates/stripe/success.html": _render("flask/success.html.j2", ctx),
        "templates/stripe/account.html": _render("flask/account.html.j2", ctx),
        "docs/STRIPE-FLASK.md": _render("docs/flask_setup.md.j2", ctx),
        ".env.example": _render("shared/env.python.md.j2", ctx),
    }
    return files


def _generate_express(ctx: dict[str, Any]) -> dict[str, str]:
    lib = ctx["lib"]
    return {
        f"{lib}/stripe.ts": _render_ts("node/stripe_client.ts.j2", ctx),
        f"{lib}/stripe-config.ts": _render_ts("node/stripe_config.ts.j2", ctx),
        f"{lib}/stripe-webhooks.ts": _render_ts("node/stripe_webhooks.ts.j2", ctx),
        "src/routes/stripe.ts": _render_ts("express/routes.ts.j2", ctx),
        "public/pricing.html": _render_ts("static/pricing.html.j2", ctx),
        "public/success.html": _render("static/success.html.j2", ctx),
        "public/account.html": _render_ts("static/account.html.j2", ctx),
        "docs/STRIPE-EXPRESS.md": _render("docs/express_setup.md.j2", ctx),
        ".env.example": _render("shared/env.example.md.j2", ctx),
    }


def _generate_fastify(ctx: dict[str, Any]) -> dict[str, str]:
    lib = ctx["lib"]
    return {
        f"{lib}/stripe.ts": _render_ts("node/stripe_client.ts.j2", ctx),
        f"{lib}/stripe-config.ts": _render_ts("node/stripe_config.ts.j2", ctx),
        f"{lib}/stripe-webhooks.ts": _render_ts("node/stripe_webhooks.ts.j2", ctx),
        "src/plugins/stripe.ts": _render_ts("fastify/plugin.ts.j2", ctx),
        "public/pricing.html": _render_ts("static/pricing.html.j2", ctx),
        "public/success.html": _render("static/success.html.j2", ctx),
        "public/account.html": _render_ts("static/account.html.j2", ctx),
        "docs/STRIPE-FASTIFY.md": _render("docs/fastify_setup.md.j2", ctx),
        ".env.example": _render("shared/env.example.md.j2", ctx),
    }


def _generate_nextjs(ctx: dict[str, Any]) -> dict[str, str]:
    lib = ctx["lib"]
    files = {
        f"{lib}/stripe.ts": _render_ts("node/stripe_client.ts.j2", ctx),
        f"{lib}/stripe-config.ts": _render_ts("node/stripe_config.ts.j2", ctx),
        f"{lib}/stripe-webhooks.ts": _render_ts("node/stripe_webhooks.ts.j2", ctx),
        "docs/STRIPE-NEXTJS.md": _render("docs/nextjs_setup.md.j2", ctx),
        ".env.example": _render("shared/env.example.md.j2", ctx),
    }
    if ctx["use_app_router"]:
        files.update(
            {
                "app/api/stripe/webhook/route.ts": _render_ts("nextjs/webhook_app.ts.j2", ctx),
                "app/api/stripe/checkout/route.ts": _render_ts("nextjs/checkout_app.ts.j2", ctx),
                "app/api/stripe/portal/route.ts": _render_ts("nextjs/portal_app.ts.j2", ctx),
                "app/pricing/page.tsx": _render_ts("nextjs/pricing_page.tsx.j2", ctx),
                "app/success/page.tsx": _render_ts("nextjs/success_page.tsx.j2", ctx),
                "app/account/page.tsx": _render_ts("nextjs/account_page.tsx.j2", ctx),
            }
        )
    else:
        files.update(
            {
                "pages/api/stripe/webhook.ts": _render_ts("nextjs/webhook_pages.ts.j2", ctx),
                "pages/api/stripe/checkout.ts": _render_ts("nextjs/checkout_pages.ts.j2", ctx),
                "pages/api/stripe/portal.ts": _render_ts("nextjs/portal_pages.ts.j2", ctx),
                "pages/pricing.tsx": _render_ts("nextjs/pricing_page.tsx.j2", ctx),
                "pages/success.tsx": _render_ts("nextjs/success_page.tsx.j2", ctx),
                "pages/account.tsx": _render_ts("nextjs/account_page.tsx.j2", ctx),
            }
        )
    return files


def _generate_remix(ctx: dict[str, Any]) -> dict[str, str]:
    lib = ctx["lib"]
    return {
        f"{lib}/stripe.ts": _render_ts("node/stripe_client.ts.j2", ctx),
        f"{lib}/stripe-config.ts": _render_ts("node/stripe_config.ts.j2", ctx),
        f"{lib}/stripe-webhooks.ts": _render_ts("node/stripe_webhooks.ts.j2", ctx),
        "app/routes/api.stripe.webhook.ts": _render_ts("remix/webhook.ts.j2", ctx),
        "app/routes/api.stripe.checkout.ts": _render_ts("remix/checkout.ts.j2", ctx),
        "app/routes/api.stripe.portal.ts": _render_ts("remix/portal.ts.j2", ctx),
        "app/routes/stripe.pricing.tsx": _render_ts("remix/pricing.tsx.j2", ctx),
        "docs/STRIPE-REMIX.md": _render("docs/remix_setup.md.j2", ctx),
        ".env.example": _render("shared/env.example.md.j2", ctx),
    }


def _generate_nuxt(ctx: dict[str, Any]) -> dict[str, str]:
    lib = ctx["lib"]
    return {
        f"{lib}/stripe.ts": _render_ts("node/stripe_client.ts.j2", ctx),
        f"{lib}/stripe-config.ts": _render_ts("node/stripe_config.ts.j2", ctx),
        f"{lib}/stripe-webhooks.ts": _render_ts("node/stripe_webhooks.ts.j2", ctx),
        "server/api/stripe/webhook.post.ts": _render_ts("nuxt/webhook.ts.j2", ctx),
        "server/api/stripe/checkout.post.ts": _render_ts("nuxt/checkout.ts.j2", ctx),
        "server/api/stripe/portal.post.ts": _render_ts("nuxt/portal.ts.j2", ctx),
        "pages/pricing.vue": _render_ts("nuxt/pricing.vue.j2", ctx),
        "docs/STRIPE-NUXT.md": _render("docs/nuxt_setup.md.j2", ctx),
        ".env.example": _render("shared/env.example.md.j2", ctx),
    }


def _generate_sveltekit(ctx: dict[str, Any]) -> dict[str, str]:
    lib = ctx["lib"]
    return {
        f"{lib}/stripe.ts": _render_ts("node/stripe_client.ts.j2", ctx),
        f"{lib}/stripe-config.ts": _render_ts("node/stripe_config.ts.j2", ctx),
        f"{lib}/stripe-webhooks.ts": _render_ts("node/stripe_webhooks.ts.j2", ctx),
        "src/routes/api/stripe/webhook/+server.ts": _render_ts("sveltekit/webhook.ts.j2", ctx),
        "src/routes/api/stripe/checkout/+server.ts": _render_ts("sveltekit/checkout.ts.j2", ctx),
        "src/routes/api/stripe/portal/+server.ts": _render_ts("sveltekit/portal.ts.j2", ctx),
        "src/routes/pricing/+page.svelte": _render_ts("sveltekit/pricing.svelte.j2", ctx),
        "docs/STRIPE-SVELTEKIT.md": _render("docs/sveltekit_setup.md.j2", ctx),
        ".env.example": _render("shared/env.example.md.j2", ctx),
    }


def _generate_rails(ctx: dict[str, Any]) -> dict[str, str]:
    return {
        "app/controllers/stripe_controller.rb": _render("rails/controller.rb.j2", ctx),
        "app/views/stripe/pricing.html.erb": _render("rails/pricing.html.erb.j2", ctx),
        "app/views/stripe/success.html.erb": _render("rails/success.html.erb.j2", ctx),
        "app/views/stripe/account.html.erb": _render("rails/account.html.erb.j2", ctx),
        "docs/STRIPE-RAILS.md": _render("docs/rails_setup.md.j2", ctx),
        ".env.example": _render("shared/env.ruby.md.j2", ctx),
    }


def _generate_laravel(ctx: dict[str, Any]) -> dict[str, str]:
    return {
        "app/Http/Controllers/StripeController.php": _render("laravel/controller.php.j2", ctx),
        "routes/stripe.php": _render("laravel/routes.php.j2", ctx),
        "resources/views/stripe/pricing.blade.php": _render_ts("laravel/pricing.blade.php.j2", ctx),
        "docs/STRIPE-LARAVEL.md": _render("docs/laravel_setup.md.j2", ctx),
        ".env.example": _render("shared/env.php.md.j2", ctx),
    }


def _generate_minimal(ctx: dict[str, Any]) -> dict[str, str]:
    lib = ctx["lib"]
    return {
        f"{lib}/stripe.ts": _render_ts("node/stripe_client.ts.j2", ctx),
        f"{lib}/stripe-config.ts": _render_ts("node/stripe_config.ts.j2", ctx),
        f"{lib}/stripe-webhooks.ts": _render_ts("node/stripe_webhooks.ts.j2", ctx),
        "docs/STRIPE-WIRING.md": _render("docs/wiring.md.j2", ctx),
        ".env.example": _render("shared/env.example.md.j2", ctx),
    }
