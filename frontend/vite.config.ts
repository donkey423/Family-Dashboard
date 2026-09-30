import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "FAMILY_FINANCE_HUB_");
  return {
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    allowedHosts: env.FAMILY_FINANCE_HUB_PREVIEW_HOST ? [env.FAMILY_FINANCE_HUB_PREVIEW_HOST] : [],
    proxy: { "/api": env.FAMILY_FINANCE_HUB_API_URL || "http://127.0.0.1:8000" },
  },
  };
});
