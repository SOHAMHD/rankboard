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
    // The dev server may serve NOTHING outside client/. It used to allow
    // ["﻿.."] (the whole tree, including server-python/.env and the Google
    // service-account key), then just the shared location seed JSON. The client
    // no longer imports anything from the server at all — the geo picker reads
    // /api/locations — so the allowance is back to the client directory only.
    fs: { allow: ["."] },
  },
});
