#!/usr/bin/env node
/**
 * Burn test — exercises CLI commands against a temp Next.js-style fixture.
 * Run: node scripts/burn-test.mjs
 */
import { execSync } from "node:child_process";
import { mkdir, writeFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

const root = join(tmpdir(), `stripe-installer-burn-${Date.now()}`);
const cli = "npx tsx src/cli.ts";
const env = { ...process.env, STRIPE_INSTALLER_PASSPHRASE: "burn-test-pass" };

const results = [];

function run(label, cmd, expectFail = false) {
  try {
    const out = execSync(cmd, { cwd: process.cwd(), env, encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] });
    if (expectFail) {
      results.push({ label, ok: false, error: "Expected failure but succeeded" });
      console.log(`✗ ${label} — expected failure`);
      return;
    }
    results.push({ label, ok: true });
    console.log(`✓ ${label}`);
    return out;
  } catch (err) {
    if (expectFail) {
      results.push({ label, ok: true });
      console.log(`✓ ${label} (expected fail)`);
      return err.stdout?.toString() ?? "";
    }
    results.push({ label, ok: false, error: err.stderr?.toString() || err.message });
    console.log(`✗ ${label}`);
    console.log(err.stderr?.toString() || err.message);
    return null;
  }
}

async function setupFixture() {
  await mkdir(root, { recursive: true });
  await writeFile(
    join(root, "package.json"),
    JSON.stringify({
      name: "burn-test-app",
      private: true,
      dependencies: { next: "14.0.0", react: "18.0.0", stripe: "^17.0.0" },
    }, null, 2)
  );
  await mkdir(join(root, "app"), { recursive: true });
  await writeFile(join(root, "app", "layout.tsx"), "export default function L({ children }) { return children; }\n");
  await writeFile(join(root, ".gitignore"), "node_modules/\n");
}

async function setupExpressFixture() {
  const expressRoot = join(tmpdir(), `stripe-installer-burn-express-${Date.now()}`);
  await mkdir(expressRoot, { recursive: true });
  await writeFile(
    join(expressRoot, "package.json"),
    JSON.stringify({
      name: "burn-test-express",
      private: true,
      type: "module",
      dependencies: { express: "^4.18.0", stripe: "^17.0.0" },
    }, null, 2)
  );
  await writeFile(join(expressRoot, ".gitignore"), "node_modules/\n");
  return expressRoot;
}

async function setupNuxtFixture() {
  const dir = join(tmpdir(), `stripe-installer-burn-nuxt-${Date.now()}`);
  await mkdir(dir, { recursive: true });
  await writeFile(
    join(dir, "package.json"),
    JSON.stringify({
      name: "burn-test-nuxt",
      private: true,
      dependencies: { nuxt: "^3.0.0", stripe: "^17.0.0" },
    }, null, 2)
  );
  await writeFile(join(dir, ".gitignore"), "node_modules/\n");
  return dir;
}

async function setupSvelteKitFixture() {
  const dir = join(tmpdir(), `stripe-installer-burn-svelte-${Date.now()}`);
  await mkdir(dir, { recursive: true });
  await writeFile(
    join(dir, "package.json"),
    JSON.stringify({
      name: "burn-test-svelte",
      private: true,
      dependencies: { "@sveltejs/kit": "^2.0.0", stripe: "^17.0.0" },
    }, null, 2)
  );
  await writeFile(join(dir, ".gitignore"), "node_modules/\n");
  return dir;
}

async function setupDjangoFixture() {
  const dir = join(tmpdir(), `stripe-installer-burn-django-${Date.now()}`);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, "manage.py"), "#!/usr/bin/env python\n");
  await writeFile(join(dir, "requirements.txt"), "django\nstripe\n");
  await writeFile(join(dir, ".gitignore"), "__pycache__/\n");
  return dir;
}

async function setupFlaskFixture() {
  const dir = join(tmpdir(), `stripe-installer-burn-flask-${Date.now()}`);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, "app.py"), "from flask import Flask\napp = Flask(__name__)\n");
  await writeFile(join(dir, "requirements.txt"), "flask\nstripe\n");
  return dir;
}

async function setupRailsFixture() {
  const dir = join(tmpdir(), `stripe-installer-burn-rails-${Date.now()}`);
  await mkdir(join(dir, "config"), { recursive: true });
  await writeFile(join(dir, "Gemfile"), "source 'https://rubygems.org'\ngem 'rails'\ngem 'stripe'\n");
  await writeFile(join(dir, "config", "routes.rb"), "Rails.application.routes.draw do\nend\n");
  return dir;
}

async function setupLaravelFixture() {
  const dir = join(tmpdir(), `stripe-installer-burn-laravel-${Date.now()}`);
  await mkdir(join(dir, "app", "Http", "Controllers"), { recursive: true });
  await writeFile(join(dir, "artisan"), "#!/usr/bin/env php\n");
  await writeFile(
    join(dir, "composer.json"),
    JSON.stringify({ name: "burn/laravel", require: { "stripe/stripe-php": "^13.0" } }, null, 2)
  );
  return dir;
}

async function setupReactFixture() {
  const dir = join(tmpdir(), `stripe-installer-burn-react-${Date.now()}`);
  await mkdir(join(dir, "src"), { recursive: true });
  await writeFile(
    join(dir, "package.json"),
    JSON.stringify({
      name: "burn-test-react",
      private: true,
      dependencies: { react: "^18.0.0", "react-dom": "^18.0.0", stripe: "^17.0.0" },
    }, null, 2)
  );
  await writeFile(join(dir, "src", "App.tsx"), "export default function App() { return null; }\n");
  return dir;
}

async function smokeFramework(name, dir) {
  const quoted = `"${dir}"`;
  run(`${name} scan`, `${cli} scan ${quoted}`);
  run(`${name} diagnose`, `${cli} diagnose ${quoted} --skip-vault`);
  run(`${name} vault init`, `${cli} vault init -p ${dir}`);
  run(`${name} generate`, `${cli} fix ${quoted} --action generate-files`);
  await rm(dir, { recursive: true, force: true });
}

async function main() {
  console.log("\n🔥 Stripe Installer burn test\n");
  const projectDir = process.cwd();

  run("build", "npm run build");

  await setupFixture();
  const p = `"${root}"`;

  run("scan fixture", `${cli} scan ${p}`);
  run("diagnose skip-vault", `${cli} diagnose ${p} --skip-vault`);
  run("vault init", `${cli} vault init -p ${root}`);
  run("vault set keys", `${cli} vault set STRIPE_SECRET_KEY sk_test_burn -p ${root}`);
  run("vault set pk", `${cli} vault set STRIPE_PUBLISHABLE_KEY pk_test_burn -p ${root}`);
  run("vault list", `${cli} vault list -p ${root}`);
  run("diagnose with vault", `${cli} diagnose ${p}`);
  run("fix create config", `${cli} fix ${p} --action create-stripe-config`);
  run("fix gitignore", `${cli} fix ${p} --action fix-gitignore`);
  run("fix sync public key", `${cli} fix ${p} --action sync-public-key`);
  run("fix generate files", `${cli} fix ${p} --action generate-files`);
  run("status", `${cli} status ${p}`);
  run("readiness", `${cli} readiness ${p}`);
  run("postgres status", `${cli} postgres status -p ${root}`);

  const expressRoot = await setupExpressFixture();
  await smokeFramework("express", expressRoot);

  await smokeFramework("nuxt", await setupNuxtFixture());
  await smokeFramework("sveltekit", await setupSvelteKitFixture());
  await smokeFramework("django", await setupDjangoFixture());
  await smokeFramework("flask", await setupFlaskFixture());
  await smokeFramework("rails", await setupRailsFixture());
  await smokeFramework("laravel", await setupLaravelFixture());
  await smokeFramework("react", await setupReactFixture());

  run("self scan", `${cli} scan .`);
  run("self diagnose", `${cli} diagnose . --skip-vault`);
  run("dist cli version", "node dist/cli.js --version");

  run("deploy infra dry", `${cli} deploy ${p} --no-stripe --no-generate --force`, false);

  await rm(root, { recursive: true, force: true });

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${"─".repeat(40)}`);
  console.log(`Passed: ${results.length - failed.length}/${results.length}`);
  if (failed.length) {
    console.log("\nFailures:");
    failed.forEach((f) => console.log(`  • ${f.label}: ${f.error?.slice(0, 120)}`));
    process.exit(1);
  }
  console.log("\nAll burn tests passed.\n");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
