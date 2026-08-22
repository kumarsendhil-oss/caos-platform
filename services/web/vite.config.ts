import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Desktop-first PWA per ADR 0006 — dev server proxies /api to the FastAPI
// backend so the frontend never needs CORS workarounds in local dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
