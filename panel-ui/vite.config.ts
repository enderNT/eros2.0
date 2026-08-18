import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The panel ships inside the FastAPI container: the bundle is written straight
// into the package's static directory (already included in the wheel) and is
// served from /admin/static/panel, which is why `base` is not "/".
export default defineConfig({
  plugins: [react()],
  base: "/admin/static/panel/",
  build: {
    outDir: "../src/agente/web/static/panel",
    emptyOutDir: true,
  },
  server: {
    // `npm run dev` talks to a locally running uvicorn; the cookie is
    // same-origin through this proxy, so there is no CORS in development
    // either.
    proxy: { "/admin/api": "http://127.0.0.1:8000" },
  },
});
