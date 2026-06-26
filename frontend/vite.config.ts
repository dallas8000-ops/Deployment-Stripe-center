import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendPort = env.DEV_BACKEND_PORT || process.env.DEV_BACKEND_PORT || "8000";
  const apiTarget = `http://127.0.0.1:${backendPort}`;

  return {
    plugins: [react()],
    server: {
      host: "localhost",
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
        "/ws": {
          target: `ws://127.0.0.1:${backendPort}`,
          ws: true,
          changeOrigin: true,
        },
      },
    },
  };
});
