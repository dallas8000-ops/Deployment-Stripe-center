import { readFile, access } from "node:fs/promises";
import { join, basename } from "node:path";
import { glob } from "glob";
import type {
  Framework,
  Language,
  NextRouter,
  ProjectProfile,
  StripeFeature,
  DetectedSecret,
} from "../types.js";
import { redactSecrets } from "../security/sanitizer.js";
import { frameworkRecommendations } from "../stripe/framework-profiles.js";

const FRAMEWORK_SIGNALS: Record<Framework, string[]> = {
  nextjs: ["next.config", "app/layout", "pages/_app"],
  react: ["src/App.tsx", "src/App.jsx", "vite.config"],
  express: ["express", "app.listen"],
  fastify: ["fastify"],
  remix: ["remix.config", "@remix-run"],
  nuxt: ["nuxt.config"],
  sveltekit: ["svelte.config", "@sveltejs/kit"],
  django: ["manage.py", "settings.py"],
  flask: ["flask", "app.py"],
  rails: ["config/routes.rb", "Gemfile"],
  laravel: ["artisan", "composer.json"],
  unknown: [],
};

const STRIPE_FEATURE_SIGNALS: Record<StripeFeature, RegExp[]> = {
  checkout: [/checkout\.sessions/i, /stripe\.checkout/i, /@stripe\/react-stripe-js/i],
  subscriptions: [/subscriptions/i, /recurring/i, /price_/i],
  connect: [/stripe\.connect/i, /ConnectAccount/i],
  "billing-portal": [/billingPortal/i, /billing-portal/i],
  webhooks: [/webhook/i, /constructEvent/i, /stripe-signature/i],
  "payment-intents": [/paymentIntents/i, /payment-intent/i],
  "customer-portal": [/customer-portal/i, /billingPortal/i],
  invoicing: [/invoices/i, /invoice\./i],
};

export class ProjectScanner {
  constructor(private readonly rootPath: string) {}

  async scan(): Promise<ProjectProfile> {
    const [packageJson, envFiles, sourceFiles] = await Promise.all([
      this.readPackageJson(),
      this.findEnvFiles(),
      this.findSourceFiles(),
    ]);

    const framework = await this.detectFramework(packageJson, sourceFiles);
    const language = this.detectLanguage(packageJson, sourceFiles);
    const dependencies = packageJson?.dependencies
      ? Object.keys(packageJson.dependencies)
      : [];
    const devDependencies = packageJson?.devDependencies
      ? Object.keys(packageJson.devDependencies)
      : [];

    const { secrets, existingStripe } = await this.scanForSecretsAndStripe(
      sourceFiles,
      envFiles
    );

    const suggestedFeatures = this.inferStripeFeatures(
      sourceFiles,
      dependencies,
      existingStripe
    );

    const nextRouter = framework === "nextjs" ? await this.detectNextRouter() : undefined;

    const recommendations = [
      ...this.buildRecommendations(
        framework,
        language,
        existingStripe,
        envFiles,
        suggestedFeatures
      ),
      ...frameworkRecommendations({
        rootPath: this.rootPath,
        name: (packageJson?.name as string | undefined) ?? basename(this.rootPath),
        framework,
        language,
        nextRouter,
        hasPackageJson: packageJson !== null,
        hasEnvFile: envFiles.length > 0,
        envFiles,
        dependencies,
        devDependencies,
        detectedSecrets: secrets,
        suggestedFeatures,
        existingStripeCode: existingStripe,
        serverRuntime: this.detectRuntime(framework, packageJson),
        recommendations: [],
      }),
    ];

    return {
      rootPath: this.rootPath,
      name: (packageJson?.name as string | undefined) ?? basename(this.rootPath),
      framework,
      language,
      nextRouter,
      hasPackageJson: packageJson !== null,
      hasEnvFile: envFiles.length > 0,
      envFiles,
      dependencies,
      devDependencies,
      detectedSecrets: secrets,
      suggestedFeatures,
      existingStripeCode: existingStripe,
      serverRuntime: this.detectRuntime(framework, packageJson),
      recommendations,
    };
  }

  private async readPackageJson(): Promise<Record<string, unknown> | null> {
    try {
      const raw = await readFile(join(this.rootPath, "package.json"), "utf8");
      return JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return null;
    }
  }

  private async findEnvFiles(): Promise<string[]> {
    const matches = await glob("**/.env*", {
      cwd: this.rootPath,
      dot: true,
      ignore: ["**/node_modules/**", "**/.stripe-installer/**"],
    });
    return matches;
  }

  private async findSourceFiles(): Promise<string[]> {
    const patterns = [
      "**/*.{ts,tsx,js,jsx,py,rb,php}",
      "**/package.json",
      "**/requirements.txt",
      "**/Gemfile",
      "**/composer.json",
    ];
    const files: string[] = [];
    for (const pattern of patterns) {
      const matches = await glob(pattern, {
        cwd: this.rootPath,
        ignore: ["**/node_modules/**", "**/dist/**", "**/.stripe-installer/**", "**/scripts/**"],
        maxDepth: 6,
      });
      files.push(...matches);
    }
    return [...new Set(files)].slice(0, 200);
  }

  private async detectFramework(
    packageJson: Record<string, unknown> | null,
    sourceFiles: string[]
  ): Promise<Framework> {
    const deps = {
      ...(packageJson?.dependencies as Record<string, string> | undefined),
      ...(packageJson?.devDependencies as Record<string, string> | undefined),
    };

    if (deps?.next) return "nextjs";
    if (deps?.["@remix-run/react"]) return "remix";
    if (deps?.nuxt || deps?.["nuxt3"]) return "nuxt";
    if (deps?.["@sveltejs/kit"]) return "sveltekit";
    if (deps?.express) return "express";
    if (deps?.fastify) return "fastify";

    if (await this.fileExists("manage.py")) return "django";
    if (await this.fileExists("config/routes.rb")) return "rails";
    if (await this.fileExists("artisan")) return "laravel";

    if (deps?.react || deps?.["react-dom"]) {
      return "react";
    }

    for (const [framework, signals] of Object.entries(FRAMEWORK_SIGNALS)) {
      if (framework === "unknown") continue;
      for (const signal of signals) {
        if (sourceFiles.some((f) => f.includes(signal))) {
          return framework as Framework;
        }
      }
    }

    return "unknown";
  }

  private detectLanguage(
    packageJson: Record<string, unknown> | null,
    sourceFiles: string[]
  ): Language {
    if (sourceFiles.some((f) => f.endsWith(".ts") || f.endsWith(".tsx"))) {
      return "typescript";
    }
    if (packageJson || sourceFiles.some((f) => f.endsWith(".js") || f.endsWith(".jsx"))) {
      return "javascript";
    }
    if (sourceFiles.some((f) => f.endsWith(".py"))) return "python";
    if (sourceFiles.some((f) => f.endsWith(".rb"))) return "ruby";
    if (sourceFiles.some((f) => f.endsWith(".php"))) return "php";
    return "unknown";
  }

  private detectRuntime(
    framework: Framework,
    packageJson: Record<string, unknown> | null
  ): ProjectProfile["serverRuntime"] {
    if (["django", "flask"].includes(framework)) return "python";
    if (framework === "rails") return "ruby";
    if (framework === "laravel") return "php";

    const deps = packageJson?.dependencies as Record<string, string> | undefined;
    if (deps?.["@vercel/edge"] || framework === "nextjs") {
      return "node";
    }
    if (packageJson) return "node";
    return "unknown";
  }

  private async scanForSecretsAndStripe(
    sourceFiles: string[],
    envFiles: string[]
  ): Promise<{ secrets: DetectedSecret[]; existingStripe: boolean }> {
    const secrets: DetectedSecret[] = [];
    let existingStripe = false;
    const allFiles = [...envFiles, ...sourceFiles.slice(0, 50)];

    for (const file of allFiles) {
      try {
        const content = await readFile(join(this.rootPath, file), "utf8");
        if (/stripe/i.test(content) || /from ['"]stripe['"]/i.test(content)) {
          existingStripe = true;
        }
        const { found } = redactSecrets(content);
        for (const secret of found) {
          secrets.push({ ...secret, file });
        }
      } catch {
        // skip unreadable files
      }
    }

    return { secrets, existingStripe };
  }

  private inferStripeFeatures(
    sourceFiles: string[],
    dependencies: string[],
    existingStripe: boolean
  ): StripeFeature[] {
    const features = new Set<StripeFeature>();

    if (dependencies.includes("stripe")) features.add("webhooks");
    if (dependencies.includes("@stripe/stripe-js")) features.add("checkout");
    if (dependencies.includes("@stripe/react-stripe-js")) features.add("payment-intents");

    if (!existingStripe) {
      features.add("checkout");
      features.add("subscriptions");
      features.add("webhooks");
      features.add("billing-portal");
      return [...features];
    }

    return features.size > 0
      ? [...features]
      : ["checkout", "subscriptions", "webhooks", "billing-portal"];
  }

  private buildRecommendations(
    framework: Framework,
    language: Language,
    existingStripe: boolean,
    envFiles: string[],
    features: StripeFeature[]
  ): string[] {
    const recs: string[] = [];

    if (!existingStripe) {
      recs.push("No existing Stripe integration detected — greenfield setup recommended.");
    } else {
      recs.push("Existing Stripe code found — incremental setup to avoid overwriting.");
    }

    if (envFiles.length === 0) {
      recs.push("Create a .env.local (or .env) file for Stripe keys — never commit secrets.");
    }

    if (framework === "nextjs") {
      recs.push("Keep STRIPE_SECRET_KEY server-side only; expose STRIPE_PUBLISHABLE_KEY to client.");
    } else if (framework === "express" || framework === "fastify") {
      recs.push("Mount webhook handler before global JSON body parsers (raw body required).");
    }

    if (features.includes("subscriptions")) {
      recs.push("Enable Stripe Billing and configure Customer Portal for self-service.");
    }

    if (language === "typescript") {
      recs.push("Use stripe npm package with full TypeScript types.");
    }

    recs.push("Store all secrets in the encrypted vault — never pass to AI prompts.");

    return recs;
  }

  private async detectNextRouter(): Promise<NextRouter> {
    if (await this.fileExists("app/layout.tsx") || await this.fileExists("app/layout.js")) {
      return "app";
    }
    if (await this.fileExists("pages/_app.tsx") || await this.fileExists("pages/_app.js")) {
      return "pages";
    }
    return "unknown";
  }

  private async fileExists(relativePath: string): Promise<boolean> {
    try {
      await access(join(this.rootPath, relativePath));
      return true;
    } catch {
      return false;
    }
  }
}
