import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies the API to FastAPI; `npm run build` emits dist/ which FastAPI serves.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000", "/healthz": "http://127.0.0.1:8000" } },
  build: { outDir: "dist", chunkSizeWarningLimit: 900 },
});
