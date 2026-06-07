import type { Framework, ProjectProfile } from "../types.js";
import { libDir, resolveWebhookPath } from "../stripe/framework-profiles.js";

export interface DeployPaths {
  libDir: string;
  dbImport: string;
  stripeDbImport: string;
  healthPath: string;
  webhookPath: string;
  healthUrl: string;
  webhookUrl: string;
}

export function getDeployPaths(profile: ProjectProfile, productionUrl: string): DeployPaths {
  const lib = libDir(profile);
  const webhookPath = resolveWebhookPath(profile);
  const healthPath = healthCheckPath(profile.framework);

  let dbImport = "./db.js";
  let stripeDbImport = "./stripe-db.js";

  switch (profile.framework) {
    case "nextjs":
      dbImport = "@/lib/db";
      stripeDbImport = "@/lib/stripe-db";
      break;
    case "remix":
      dbImport = "~/lib/db";
      stripeDbImport = "~/lib/stripe-db";
      break;
    case "nuxt":
      dbImport = "../../utils/db";
      stripeDbImport = "../../utils/stripe-db";
      break;
    case "sveltekit":
      dbImport = "$lib/db";
      stripeDbImport = "$lib/stripe-db";
      break;
    case "express":
    case "fastify":
    case "react":
      dbImport = "../lib/db.js";
      stripeDbImport = "../lib/stripe-db.js";
      break;
    default:
      break;
  }

  return {
    libDir: lib,
    dbImport,
    stripeDbImport,
    healthPath,
    webhookPath,
    healthUrl: `${productionUrl}${healthPath}`,
    webhookUrl: `${productionUrl}${webhookPath}`,
  };
}

export function healthCheckPath(framework: Framework): string {
  switch (framework) {
    case "nextjs":
    case "remix":
    case "nuxt":
    case "sveltekit":
    case "react":
      return "/api/health";
    default:
      return "/stripe/health";
  }
}

export function frameworkStartCommand(profile: ProjectProfile): string {
  switch (profile.framework) {
    case "nextjs":
      return "npm run start";
    case "nuxt":
      return "node .output/server/index.mjs";
    case "express":
    case "fastify":
    case "react":
      return "node dist/server.js";
    case "django":
      return "gunicorn myproject.wsgi:application --bind 0.0.0.0:$PORT";
    case "flask":
      return "gunicorn app:app --bind 0.0.0.0:$PORT";
    case "rails":
      return "bundle exec rails server -p $PORT -e production";
    case "laravel":
      return "php artisan serve --host=0.0.0.0 --port=$PORT";
    default:
      return "npm start";
  }
}

export function frameworkBuildCommand(profile: ProjectProfile): string {
  switch (profile.framework) {
    case "django":
    case "flask":
      return "pip install -r requirements.txt";
    case "rails":
      return "bundle install";
    case "laravel":
      return "composer install --no-dev --optimize-autoloader";
    default:
      return "npm ci && npm run build";
  }
}

function healthHandlerBody(dbImport: string): string {
  return `  const checks: Record<string, string> = { app: "ok" };

  if (process.env.DATABASE_URL) {
    try {
      const { query } = await import("${dbImport}");
      await query("SELECT 1");
      checks.database = "ok";
    } catch (err) {
      checks.database = err instanceof Error ? err.message : "error";
    }
  }

  const payload = {
    status: Object.values(checks).every((v) => v === "ok") ? "healthy" : "degraded",
    checks,
    timestamp: new Date().toISOString(),
  };`;
}

export function generateHealthRoute(profile: ProjectProfile, dbImport: string): Record<string, string> {
  const files: Record<string, string> = {};
  const body = healthHandlerBody(dbImport);

  switch (profile.framework) {
    case "nextjs":
      if (profile.nextRouter !== "pages") {
        files["app/api/health/route.ts"] = `import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
${body}
  return NextResponse.json(payload, { status: payload.status === "healthy" ? 200 : 503 });
}
`;
      } else {
        files["pages/api/health.ts"] = `import type { NextApiRequest, NextApiResponse } from "next";

export default async function handler(_req: NextApiRequest, res: NextApiResponse) {
${body}
  res.status(payload.status === "healthy" ? 200 : 503).json(payload);
}
`;
      }
      break;
    case "express":
      files["src/routes/health.ts"] = `import { Router } from "express";
import { query } from "../lib/db.js";

const router = Router();

router.get("/", async (_req, res) => {
${body}
  res.status(payload.status === "healthy" ? 200 : 503).json(payload);
});

export default router;
`;
      break;
    case "nuxt":
      files["server/api/health.get.ts"] = `export default defineEventHandler(async (event) => {
${body}
  setResponseStatus(event, payload.status === "healthy" ? 200 : 503);
  return payload;
});
`;
      break;
    case "sveltekit":
      files["src/routes/api/health/+server.ts"] = `import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";

export const GET: RequestHandler = async () => {
${body}
  return json(payload, { status: payload.status === "healthy" ? 200 : 503 });
};
`;
      break;
    case "remix":
      files["app/routes/api.health.ts"] = `import type { LoaderFunctionArgs } from "@remix-run/node";

export async function loader(_args: LoaderFunctionArgs) {
${body}
  return Response.json(payload, { status: payload.status === "healthy" ? 200 : 503 });
}
`;
      break;
    case "django":
      files["stripe/health_views.py"] = `from django.http import JsonResponse
from datetime import datetime, timezone


def health(_request):
    return JsonResponse(
        {
            "status": "healthy",
            "checks": {"app": "ok"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        status=200,
    )
`;
      break;
    case "flask":
      files["health_routes.py"] = `from datetime import datetime, timezone
from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/stripe/health")
def health():
    return jsonify(
        status="healthy",
        checks={"app": "ok"},
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
`;
      break;
    default:
      break;
  }

  return files;
}

export function generateDockerfile(profile: ProjectProfile): string {
  switch (profile.framework) {
    case "django":
      return `FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
ENV PORT=8000
CMD gunicorn myproject.wsgi:application --bind 0.0.0.0:\${PORT}
`;
    case "flask":
      return `FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
ENV PORT=5000
CMD gunicorn app:app --bind 0.0.0.0:\${PORT}
`;
    case "rails":
      return `FROM ruby:3.3-slim
WORKDIR /app
COPY Gemfile Gemfile.lock ./
RUN bundle install
COPY . .
ENV PORT=3000
CMD bundle exec rails server -b 0.0.0.0 -p \${PORT} -e production
`;
    case "laravel":
      return `FROM php:8.3-cli
WORKDIR /app
COPY . .
RUN apt-get update && apt-get install -y unzip git \\
  && curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer \\
  && composer install --no-dev --optimize-autoloader
ENV PORT=8000
CMD php artisan serve --host=0.0.0.0 --port=\${PORT}
`;
    case "express":
    case "fastify":
      return `FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
ENV PORT=3000
CMD node dist/server.js
`;
    default:
      return `FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
ENV PORT=3000
EXPOSE 3000
CMD ${frameworkStartCommand(profile)}
`;
  }
}

export function productionEnvKeys(profile: ProjectProfile, prodUrl: string): string {
  const isNext = profile.framework === "nextjs";
  const appKey = isNext ? "NEXT_PUBLIC_APP_URL" : "APP_URL";
  const pubKey = isNext ? "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY" : "STRIPE_PUBLISHABLE_KEY";
  return `NODE_ENV=production
${appKey}=${prodUrl}
STRIPE_SECRET_KEY=sk_live_
STRIPE_PUBLISHABLE_KEY=pk_live_
${isNext ? `${pubKey}=pk_live_\n` : ""}STRIPE_WEBHOOK_SECRET=whsec_
DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require
`;
}
