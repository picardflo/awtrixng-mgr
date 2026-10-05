import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Pure logic only (i18n, pixel font): no DOM environment needed.
  test: { environment: "node", include: ["src/**/*.test.ts"] },
  server: {
    // In development Vite plays the role nginx holds in production: a single
    // origin, so there is no CORS to deal with (ADR-003).
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
