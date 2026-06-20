import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const isWin = process.platform === "win32";

function prefix(name) {
  const colors = { backend: "\x1b[34m", frontend: "\x1b[32m" };
  return `${colors[name] || ""}[${name}]\x1b[0m `;
}

function pipe(name, child) {
  child.stdout?.on("data", (buf) => {
    for (const line of buf.toString().split(/\r?\n/)) {
      if (line) process.stdout.write(prefix(name) + line + "\n");
    }
  });
  child.stderr?.on("data", (buf) => {
    for (const line of buf.toString().split(/\r?\n/)) {
      if (line) process.stderr.write(prefix(name) + line + "\n");
    }
  });
}

/** Spawn without shell so paths containing & or spaces stay intact on Windows. */
function startProcess(name, executable, args, cwd) {
  const child = spawn(executable, args, {
    cwd: path.join(root, cwd),
    stdio: ["ignore", "pipe", "pipe"],
    shell: false,
    windowsHide: true,
    env: process.env,
  });
  pipe(name, child);
  child.on("exit", (code, signal) => {
    if (signal) console.log(`${prefix(name)}stopped (${signal})`);
    else if (code && name !== "backend") {
      console.log(`${prefix(name)}exited with code ${code}`);
      shutdown(code);
    } else if (code) {
      console.error(
        `${prefix(name)}exited with code ${code}\n` +
          "Port may be in use. Run: npm run dev:stop\n"
      );
      shutdown(code);
    }
  });
  return child;
}

const children = [];

function shutdown(code = 0) {
  for (const c of children) {
    if (!c.killed) c.kill();
  }
  process.exit(code);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

const daphne = path.join(root, "backend", ".venv", isWin ? "Scripts" : "bin", isWin ? "daphne.exe" : "daphne");
const viteJs = path.join(root, "frontend", "node_modules", "vite", "bin", "vite.js");

if (!existsSync(daphne)) {
  console.error("Backend not set up. Run first:\n  .\\scripts\\setup.ps1\n");
  process.exit(1);
}

if (!existsSync(viteJs)) {
  console.error("Frontend not set up. Run first:\n  npm run setup:frontend\n");
  process.exit(1);
}

async function portInUse(port) {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/health/`);
    return res.ok;
  } catch {
    return false;
  }
}

async function backendIsCurrent() {
  try {
    const res = await fetch("http://127.0.0.1:8000/api/v1/agency/dashboard/");
    // 404 = old URLconf without organizations app; 401/403 = route exists, needs auth
    return res.status !== 404;
  } catch {
    return false;
  }
}

const busy = await portInUse(8000);
if (busy) {
  const current = await backendIsCurrent();
  if (!current) {
    console.error(
      "Port 8000 is running an OLD backend (missing new API routes).\n" +
        "Stop it, then start fresh:\n" +
        "  npm run dev:stop\n" +
        "  npm run dev\n"
    );
    process.exit(1);
  }
  try {
    const probe = await fetch("http://127.0.0.1:8000/api/v1/auth/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "probe@local", password: "probe" }),
    });
    if (probe.status >= 500) {
      console.error(
        "Port 8000 is in use by a broken backend (login returns 500).\n" +
          "Stop it: npm run dev:stop\n"
      );
      process.exit(1);
    }
    console.log("[backend] Already listening on :8000 — skipping backend start\n");
  } catch {
    console.error("Port 8000 is in use but not responding. Run: npm run dev:stop\n");
    process.exit(1);
  }
} else {
  children.push(
    startProcess(
      "backend",
      daphne,
      ["-b", "127.0.0.1", "-p", "8000", "config.asgi:application"],
      "backend"
    )
  );
}

// Invoke vite via node directly — npm/.cmd shims break when the project path contains &.
children.push(startProcess("frontend", process.execPath, [viteJs], "frontend"));

console.log("Dev servers starting — open http://localhost:5173\n");
