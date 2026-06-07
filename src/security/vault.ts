import {
  createCipheriv,
  createDecipheriv,
  randomBytes,
  scryptSync,
} from "node:crypto";
import { mkdir, readFile, writeFile, chmod } from "node:fs/promises";
import { join } from "node:path";
import type { VaultEntry } from "../types.js";

const ALGORITHM = "aes-256-gcm";
const VAULT_DIR = ".stripe-installer";
const VAULT_FILE = "vault.enc.json";
const SALT_FILE = "vault.salt";

/**
 * Local encrypted vault. Secrets never leave this boundary.
 * AI and logs must never receive decrypted values from this module.
 */
export class SecretVault {
  private readonly vaultPath: string;
  private readonly saltPath: string;
  private key: Buffer | null = null;

  constructor(private readonly projectRoot: string) {
    const dir = join(projectRoot, VAULT_DIR);
    this.vaultPath = join(dir, VAULT_FILE);
    this.saltPath = join(dir, SALT_FILE);
  }

  async initialize(passphrase: string): Promise<void> {
    await mkdir(join(this.projectRoot, VAULT_DIR), { recursive: true });
    let salt: Buffer;

    try {
      salt = await readFile(this.saltPath);
    } catch {
      salt = randomBytes(32);
      await writeFile(this.saltPath, salt);
      await chmod(this.saltPath, 0o600);
    }

    this.key = scryptSync(passphrase, salt, 32);
  }

  private ensureKey(): Buffer {
    if (!this.key) {
      throw new Error("Vault not initialized. Call initialize() with a passphrase first.");
    }
    return this.key;
  }

  private encrypt(plaintext: string): Omit<VaultEntry, "key" | "createdAt" | "updatedAt"> {
    const key = this.ensureKey();
    const iv = randomBytes(12);
    const cipher = createCipheriv(ALGORITHM, key, iv);
    const encrypted = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
    const authTag = cipher.getAuthTag();

    return {
      encryptedValue: encrypted.toString("base64"),
      iv: iv.toString("base64"),
      authTag: authTag.toString("base64"),
    };
  }

  private decrypt(entry: VaultEntry): string {
    const key = this.ensureKey();
    const decipher = createDecipheriv(
      ALGORITHM,
      key,
      Buffer.from(entry.iv, "base64")
    );
    decipher.setAuthTag(Buffer.from(entry.authTag, "base64"));
    const decrypted = Buffer.concat([
      decipher.update(Buffer.from(entry.encryptedValue, "base64")),
      decipher.final(),
    ]);
    return decrypted.toString("utf8");
  }

  async load(): Promise<Record<string, VaultEntry>> {
    try {
      const raw = await readFile(this.vaultPath, "utf8");
      return JSON.parse(raw) as Record<string, VaultEntry>;
    } catch {
      return {};
    }
  }

  async save(entries: Record<string, VaultEntry>): Promise<void> {
    await writeFile(this.vaultPath, JSON.stringify(entries, null, 2), "utf8");
    await chmod(this.vaultPath, 0o600);
  }

  async set(key: string, value: string): Promise<void> {
    const entries = await this.load();
    const now = new Date().toISOString();
    const encrypted = this.encrypt(value);

    entries[key] = {
      key,
      ...encrypted,
      createdAt: entries[key]?.createdAt ?? now,
      updatedAt: now,
    };

    await this.save(entries);
  }

  async get(key: string): Promise<string | null> {
    const entries = await this.load();
    const entry = entries[key];
    if (!entry) return null;
    return this.decrypt(entry);
  }

  async has(key: string): Promise<boolean> {
    const entries = await this.load();
    return key in entries;
  }

  async listKeys(): Promise<string[]> {
    const entries = await this.load();
    return Object.keys(entries);
  }

  /** Returns only key names — safe for AI and logging */
  async getKeyManifest(): Promise<string[]> {
    return this.listKeys();
  }
}
