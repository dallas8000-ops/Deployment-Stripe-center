import { access, readFile } from "node:fs/promises";
import { join } from "node:path";
import type { DeployPlatform, ProjectProfile } from "../types.js";

export async function detectDeployPlatform(root: string, profile: ProjectProfile): Promise<DeployPlatform> {
  if (await exists(join(root, "vercel.json")) || await exists(join(root, ".vercel"))) return "vercel";
  if (await exists(join(root, "railway.json")) || await exists(join(root, "railway.toml"))) return "railway";
  if (await exists(join(root, "render.yaml"))) return "render";
  if (await exists(join(root, "fly.toml"))) return "fly";
  if (await exists(join(root, "Dockerfile"))) return "docker";

  if (profile.framework === "nextjs") return "vercel";
  if (profile.dependencies.includes("@railway/cli")) return "railway";

  try {
    const pkg = JSON.parse(await readFile(join(root, "package.json"), "utf8")) as Record<string, unknown>;
    const scripts = pkg.scripts as Record<string, string> | undefined;
    if (scripts?.deploy?.includes("vercel")) return "vercel";
    if (scripts?.deploy?.includes("railway")) return "railway";
  } catch {
    // ignore
  }

  return "unknown";
}

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

export function platformDeployCommand(platform: DeployPlatform): string {
  switch (platform) {
    case "vercel": return "vercel --prod";
    case "railway": return "railway up";
    case "render": return "render deploy";
    case "fly": return "fly deploy";
    case "docker": return "docker build -t app . && docker run -p 3000:3000 app";
    default: return "npm run build && npm start";
  }
}
