import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The proxy makes the browser see one origin: any request to /api
// is forwarded to the Express server on :4000. This avoids CORS
// entirely during development.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": "http://localhost:4000" },
  },
});
