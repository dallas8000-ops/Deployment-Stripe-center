import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("stripeInstaller", {
  selectProject: () => ipcRenderer.invoke("select-project") as Promise<string | null>,
  getState: () => ipcRenderer.invoke("get-state"),
  setProject: (path: string) => ipcRenderer.invoke("set-project", path),
  initVault: (passphrase: string) => ipcRenderer.invoke("init-vault", passphrase),
  unlockVault: (passphrase: string) => ipcRenderer.invoke("unlock-vault", passphrase),
  lockVault: () => ipcRenderer.invoke("lock-vault"),
  vaultListKeys: () => ipcRenderer.invoke("vault-list-keys") as Promise<string[]>,
  vaultSet: (key: string, value: string) => ipcRenderer.invoke("vault-set", key, value),
  scan: () => ipcRenderer.invoke("scan"),
  verify: () => ipcRenderer.invoke("verify"),
  getStatus: () => ipcRenderer.invoke("get-status"),
  runPipeline: (opts: Record<string, unknown>) => ipcRenderer.invoke("run-pipeline", opts),
  deploy: (opts: Record<string, unknown>) => ipcRenderer.invoke("deploy", opts),
  readiness: () => ipcRenderer.invoke("readiness"),
  postgresProvision: (opts: Record<string, unknown>) => ipcRenderer.invoke("postgres-provision", opts),
  postgresStatus: () => ipcRenderer.invoke("postgres-status"),
  diagnose: () => ipcRenderer.invoke("diagnose"),
  fix: (opts: Record<string, unknown>) => ipcRenderer.invoke("fix", opts),
});
