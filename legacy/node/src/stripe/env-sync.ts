import { readFile, writeFile, access } from "node:fs/promises";
import { join } from "node:path";
import { SecretVault } from "../security/vault.js";

const STRIPE_ENV_KEYS = [
  "STRIPE_SECRET_KEY",
  "STRIPE_PUBLISHABLE_KEY",
  "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
  "STRIPE_WEBHOOK_SECRET",
  "OPENAI_API_KEY",
] as const;

export async function importEnvToVault(
  projectRoot: string,
  vault: SecretVault,
  envFile = ".env.local"
): Promise<string[]> {
  const path = join(projectRoot, envFile);
  let content: string;
  try {
    content = await readFile(path, "utf8");
  } catch {
    throw new Error(`Env file not found: ${envFile}`);
  }

  const imported: string[] = [];
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;

    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, "");
    if (!value || !STRIPE_ENV_KEYS.includes(key as (typeof STRIPE_ENV_KEYS)[number])) continue;

    await vault.set(key, value);
    imported.push(key);
  }

  if (
    imported.includes("STRIPE_PUBLISHABLE_KEY") &&
    !imported.includes("NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY")
  ) {
    const pk = await vault.get("STRIPE_PUBLISHABLE_KEY");
    if (pk) {
      await vault.set("NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY", pk);
      imported.push("NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY");
    }
  }

  return imported;
}

export async function syncVaultToEnv(
  projectRoot: string,
  vault: SecretVault,
  envFile = ".env.local"
): Promise<string[]> {
  const path = join(projectRoot, envFile);
  let existing = "";
  try {
    existing = await readFile(path, "utf8");
  } catch {
    // new file
  }

  const lines = existing.split("\n");
  const keyIndex = new Map<string, number>();
  lines.forEach((line, i) => {
    const key = line.split("=")[0]?.trim();
    if (key) keyIndex.set(key, i);
  });

  const synced: string[] = [];
  const keys = await vault.listKeys();

  for (const key of keys) {
    if (!key.startsWith("STRIPE_") && key !== "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY") continue;
    const value = await vault.get(key);
    if (!value) continue;

    const entry = `${key}=${value}`;
    const idx = keyIndex.get(key);
    if (idx !== undefined) {
      lines[idx] = entry;
    } else {
      lines.push(entry);
    }
    synced.push(key);
  }

  const output = lines.filter((l, i, arr) => !(i === arr.length - 1 && l === "")).join("\n") + "\n";
  await writeFile(path, output, "utf8");
  return synced;
}

export async function findEnvFile(projectRoot: string): Promise<string | null> {
  for (const file of [".env.local", ".env"]) {
    try {
      await access(join(projectRoot, file));
      return file;
    } catch {
      // try next
    }
  }
  return null;
}
