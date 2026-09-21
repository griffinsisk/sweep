import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: /api and /auth proxy to the FastAPI server so cookies stay same-origin.
// Build: output goes straight into the Python package, which serves it.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../backend/sweep/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/auth": "http://127.0.0.1:8000",
    },
  },
});
