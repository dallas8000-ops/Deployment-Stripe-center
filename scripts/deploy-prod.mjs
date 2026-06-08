#!/usr/bin/env node
/**
 * Production deploy helper — build frontend, validate env, start Docker prod stack.
 */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const isWin = process.platform === "win32";
const python = path.join(root, "backend", ".venv", isWin ? "Scripts/python.exe" : "bin/python");
const npm = isWin ? "npm.cmd" : "npm";

function run(cmd, args, opts = {}) {
  const res = spawnSync(cmd, args, { cwd: root, stdio: "inherit", shell: isWin, ...opts });
  if (res.status !== 0) {
    process.exit(res.status ?? 1);
  }
}

if (!existsSync(python)) {
  console.error("Backend venv missing. Run: npm run setup");
  process.exit(1);
}

console.log("→ Building frontend…");
run(npm, ["run", "build:frontend"]);

console.log("→ Production env check…");
run(python, ["manage.py", "check_production"], { cwd: path.join(root, "backend") });

console.log("→ Docker prod up…");
run(npm, ["run", "docker:prod"]);

console.log("\nDeployed. Open http://127.0.0.1:8000");
console.log("Health: http://127.0.0.1:8000/health/");
