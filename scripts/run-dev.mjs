import { existsSync, readFileSync } from "node:fs";
import { execSync, spawn, spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const isWin = process.platform === "win32";
const DEFAULT_BACKEND_PORT = 8000;
const FALLBACK_BACKEND_PORT = 8001;

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
function startProcess(name, executable, args, cwd, extraEnv = {}) {
  const child = spawn(executable, args, {
    cwd: path.join(root, cwd),
    stdio: ["ignore", "pipe", "pipe"],
    shell: false,
    windowsHide: true,
    env: { ...process.env, ...extraEnv },
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

function system32(exe) {
  return path.join(process.env.SystemRoot || "C:\\Windows", "System32", exe);
}

function killPortWindows(port) {
  const netstat = system32("netstat.exe");
  const taskkill = system32("taskkill.exe");
  let out = "";
  try {
    out = execSync(`"${netstat}" -ano`, { encoding: "utf8" });
  } catch {
    return;
  }
  const pids = new Set();
  for (const line of out.split(/\r?\n/)) {
    if (!line.includes("LISTENING")) continue;
    if (!new RegExp(`:${port}\\s`).test(line)) continue;
    const parts = line.trim().split(/\s+/);
    const pid = parts[parts.length - 1];
    if (pid && /^\d+$/.test(pid) && pid !== "0") pids.add(pid);
  }
  for (const pid of pids) {
    console.log(`[dev] Stopping stale listener on :${port} (PID ${pid})`);
    try {
      execSync(`"${taskkill}" /F /PID ${pid}`, { stdio: "inherit" });
    } catch {
      /* zombie PID or already exited */
    }
  }
}

function killPort(port) {
  if (process.platform === "win32") killPortWindows(port);
  else {
    try {
      const out = execSync(`lsof -ti :${port}`, { encoding: "utf8" }).trim();
      for (const pid of out.split(/\s+/)) {
        if (pid) process.kill(Number(pid), "SIGTERM");
      }
    } catch {
      /* port free */
    }
  }
}

const defaultPython = path.join(
  root,
  "backend",
  ".venv",
  isWin ? "Scripts" : "bin",
  isWin ? "python.exe" : "python"
);
// A developer or CI runner may supply a healthy interpreter while repairing a
// moved/stale virtual environment. Running Uvicorn as a module also avoids the
// absolute interpreter path embedded in Windows console-script launchers.
const python = process.env.DEV_PYTHON?.trim() || defaultPython;
const viteJs = path.join(root, "frontend", "node_modules", "vite", "bin", "vite.js");

if (!existsSync(python)) {
  console.error("Backend not set up. Run first:\n  .\\scripts\\setup.ps1\n");
  process.exit(1);
}

if (!existsSync(viteJs)) {
  console.error("Frontend not set up. Run first:\n  npm run setup:frontend\n");
  process.exit(1);
}

const repair = spawnSync(
  python,
  ["manage.py", "fix_project_workspace", "--all-projects", "--skip-vault", "--remove-stale-workspaces"],
  { cwd: path.join(root, "backend"), stdio: "inherit", shell: false }
);
if (repair.status !== 0) {
  console.error("Workspace repair failed — fix_project_workspace exited with code", repair.status);
  process.exit(repair.status || 1);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function portInUse(port) {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/health/`);
    return res.ok;
  } catch {
    return false;
  }
}

function expectedApiRevision() {
  const revPath = path.join(root, "backend", "apps", "core", "api_revision.py");
  const src = readFileSync(revPath, "utf8");
  const match = src.match(/API_REVISION\s*=\s*["']([^"']+)["']/);
  return match?.[1] || "";
}

async function backendIsCurrent(port) {
  try {
    const healthRes = await fetch(`http://127.0.0.1:${port}/health/`);
    if (!healthRes.ok) return false;
    const health = await healthRes.json();
    const expected = expectedApiRevision();
    if (expected && health.apiRevision !== expected) {
      return false;
    }
  } catch {
    return false;
  }
  const probes = [
    `http://127.0.0.1:${port}/api/v1/agency/dashboard/`,
    `http://127.0.0.1:${port}/api/v1/projects/stripe-installer/setup-hub/`,
    `http://127.0.0.1:${port}/api/v1/projects/stripe-installer/vault/pull-from-hub/`,
  ];
  try {
    for (const url of probes) {
      const res = await fetch(url, { method: url.endsWith("pull-from-hub/") ? "POST" : "GET" });
      if (res.status === 404) return false;
    }
    return true;
  } catch {
    return false;
  }
}

async function resolveBackendPort() {
  const preferred = DEFAULT_BACKEND_PORT;
  if (await portInUse(preferred)) {
    if (await backendIsCurrent(preferred)) {
      return { port: preferred, start: false };
    }
    console.warn(
      `[backend] Port ${preferred} has an old API (missing apiRevision) — stopping it…`
    );
    killPort(preferred);
    await sleep(800);
    if ((await portInUse(preferred)) && !(await backendIsCurrent(preferred))) {
      const fallback = FALLBACK_BACKEND_PORT;
      console.warn(
        `[backend] Port ${preferred} still occupied by stale API — starting on :${fallback}`
      );
      if (await portInUse(fallback)) {
        killPort(fallback);
        await sleep(400);
      }
      return { port: fallback, start: true };
    }
    if (await backendIsCurrent(preferred)) {
      return { port: preferred, start: false };
    }
    return { port: preferred, start: true };
  }
  return { port: preferred, start: true };
}

const { port: backendPort, start: startBackend } = await resolveBackendPort();
const devBackendEnv = {
  DJANGO_DEBUG: "true",
  DEV_BACKEND_PORT: String(backendPort),
};

if (startBackend) {
  children.push(
    startProcess(
      "backend",
      python,
      ["-m", "uvicorn", "config.asgi:application", "--host", "127.0.0.1", "--port", String(backendPort), "--reload"],
      "backend",
      devBackendEnv
    )
  );
} else {
  try {
    const probe = await fetch(`http://127.0.0.1:${backendPort}/api/v1/auth/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "probe@local", password: "probe" }),
    });
    if (probe.status >= 500) {
      console.error(
        `Port ${backendPort} is in use by a broken backend (login returns 500).\n` +
          "Stop it: npm run dev:stop\n"
      );
      process.exit(1);
    }
    console.log(`[backend] Already listening on :${backendPort} — skipping backend start\n`);
  } catch {
    console.error(`Port ${backendPort} is in use but not responding. Run: npm run dev:stop\n`);
    process.exit(1);
  }
}

children.push(startProcess("frontend", process.execPath, [viteJs], "frontend", devBackendEnv));

console.log(`Dev servers starting — UI http://localhost:5173  API http://127.0.0.1:${backendPort}\n`);
