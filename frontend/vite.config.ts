import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /api and /auth are proxied to the FastAPI server so cookies
// stay same-origin. In prod, point VITE_API_BASE at the backend URL.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/auth": "http://localhost:8000",
    },
  },
});
