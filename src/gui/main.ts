import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { InstallerService } from "./installer-service.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const service = new InstallerService();

let mainWindow: BrowserWindow | null = null;

function desktopPath(...segments: string[]): string {
  return join(app.isPackaged ? process.resourcesPath : join(__dirname, "..", ".."), "desktop", ...segments);
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 900,
    minHeight: 600,
    title: "Stripe Installer",
    backgroundColor: "#0a0a0f",
    webPreferences: {
      preload: join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.loadFile(desktopPath("index.html"));

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function ipc<T>(channel: string, handler: () => Promise<T> | T): void {
  ipcMain.handle(channel, async () => {
    try {
      return { ok: true as const, data: await handler() };
    } catch (err) {
      return {
        ok: false as const,
        error: err instanceof Error ? err.message : "Unknown error",
      };
    }
  });
}

function ipcArg<T, A>(channel: string, handler: (arg: A) => Promise<T> | T): void {
  ipcMain.handle(channel, async (_event, arg: A) => {
    try {
      return { ok: true as const, data: await handler(arg) };
    } catch (err) {
      return {
        ok: false as const,
        error: err instanceof Error ? err.message : "Unknown error",
      };
    }
  });
}

function registerIpc(): void {
  ipc("select-project", async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ["openDirectory"],
      title: "Select project folder",
    });
    if (result.canceled || !result.filePaths[0]) return null;
    service.setProject(result.filePaths[0]);
    return result.filePaths[0];
  });

  ipc("get-state", () => service.getState());

  ipcArg("set-project", (path: string) => {
    service.setProject(path);
    return service.getState();
  });

  ipcArg("init-vault", (passphrase: string) => service.initVault(passphrase));
  ipcArg("unlock-vault", (passphrase: string) => service.unlockVault(passphrase));
  ipc("lock-vault", () => {
    service.lockVault();
    return service.getState();
  });

  ipc("vault-list-keys", () => service.listVaultKeys());

  ipcMain.handle("vault-set", async (_event, key: string, value: string) => {
    try {
      await service.setVaultSecret(key, value);
      return { ok: true as const, data: { stored: key } };
    } catch (err) {
      return {
        ok: false as const,
        error: err instanceof Error ? err.message : "Unknown error",
      };
    }
  });

  ipc("scan", () => service.scan());
  ipc("verify", () => service.verify());
  ipc("get-status", () => service.getStatus());
  ipcArg("run-pipeline", (opts: {
    provision?: boolean;
    generate?: boolean;
    syncEnv?: boolean;
    force?: boolean;
    appUrl?: string;
  }) => service.runStripePipeline(opts));
  ipcArg("deploy", (opts: {
    provisionStripe?: boolean;
    generateCode?: boolean;
    generateInfra?: boolean;
    provisionPostgres?: boolean;
    force?: boolean;
  }) => service.deploy(opts));
  ipc("readiness", () => service.readiness());
  ipcArg("postgres-provision", (opts) => service.postgresProvision(opts as {
    provider: "neon" | "supabase";
    region?: string;
    name?: string;
    applySchema?: boolean;
  }));
  ipc("postgres-status", () => service.postgresStatus());
  ipc("diagnose", () => service.diagnose());
  ipcArg("fix", (opts: { issueIds?: string[]; action?: string; force?: boolean }) =>
    service.fix({
      issueIds: opts.issueIds,
      action: opts.action as import("../types.js").StripeFixAction | undefined,
      force: opts.force,
    })
  );
}

app.whenReady().then(() => {
  registerIpc();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  service.lockVault();
  if (process.platform !== "darwin") app.quit();
});
