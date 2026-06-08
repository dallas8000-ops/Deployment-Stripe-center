/**
 * Stop Stripe Installer dev servers (ports 8000, 5173–5175).
 * Pure Node — no PowerShell required in PATH.
 */
import { execSync } from "node:child_process";
import path from "node:path";

const ports = [8000, 5173, 5174, 5175];

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
    // Match :8000 with word boundary (avoid :80000)
    if (!new RegExp(`:${port}\\s`).test(line)) continue;
    const parts = line.trim().split(/\s+/);
    const pid = parts[parts.length - 1];
    if (pid && /^\d+$/.test(pid) && pid !== "0") pids.add(pid);
  }

  for (const pid of pids) {
    console.log(`  :${port} -> PID ${pid}`);
    try {
      execSync(`"${taskkill}" /F /PID ${pid}`, { stdio: "inherit" });
    } catch {
      /* already exited */
    }
  }
}

function killPortUnix(port) {
  try {
    const out = execSync(`lsof -ti :${port}`, { encoding: "utf8" }).trim();
    if (!out) return;
    for (const pid of out.split(/\s+/)) {
      if (!pid) continue;
      console.log(`  :${port} -> PID ${pid}`);
      try {
        process.kill(Number(pid), "SIGTERM");
      } catch {
        /* gone */
      }
    }
  } catch {
    /* port free */
  }
}

console.log(`Stopping dev servers on ports ${ports.join(", ")}...`);

for (const port of ports) {
  if (process.platform === "win32") killPortWindows(port);
  else killPortUnix(port);
}

console.log("Done. Run: npm run dev");
