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
    // Allow importing ONLY the shared location seed that lives with the server
    // (server-python/app/locations.json). Previously this was ["﻿.."], which let
    // the dev server serve the WHOLE rankboard-admin tree over /@fs — including
    // server-python/.env and the Google service-account key. Scope it to exactly
    // the one file the client imports; everything else stays unreachable.
    fs: { allow: [".", "../server-python/app/locations.json"] },
  },
});
