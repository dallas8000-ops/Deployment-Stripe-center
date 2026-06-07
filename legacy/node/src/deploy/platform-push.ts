import { execSync } from "node:child_process";
import type { DeployPlatform } from "../types.js";
import { platformDeployCommand } from "./platform-detector.js";

export interface PlatformPushResult {
  success: boolean;
  platform: DeployPlatform;
  message: string;
}

export function pushToPlatform(root: string, platform: DeployPlatform): PlatformPushResult {
  if (platform === "unknown") {
    return {
      success: false,
      platform,
      message: "Unknown platform — set platform in deploy.config.json or add vercel.json / railway.toml",
    };
  }

  const cmd = platformDeployCommand(platform);
  try {
    execSync(cmd, { cwd: root, stdio: "pipe", encoding: "utf8" });
    return { success: true, platform, message: `Deployed via: ${cmd}` };
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Deploy command failed";
    const stderr =
      err && typeof err === "object" && "stderr" in err
        ? String((err as { stderr?: Buffer }).stderr ?? "")
        : "";
    return {
      success: false,
      platform,
      message: `${msg}${stderr ? `\n${stderr.slice(0, 500)}` : ""}`,
    };
  }
}
