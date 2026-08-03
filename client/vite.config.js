import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": "http://localhost:4000" },
    fs: { allow: ["."] },
  },
  build: {
    // Raised so the warning reflects the intended chunk layout below rather than
    // firing on every build.
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        // Without this, Rollup folds anything shared by two screens into a single
        // common chunk — so recharts (large) shipped alongside the Dashboard even
        // for a user opening Keywords, and the TipTap editor rode along with it.
        // Giving the heavy libraries their own chunks means each is fetched only
        // by the screen that imports it, and they stay cached across deploys
        // because changing app code no longer invalidates them.
        manualChunks: {
          react: ["react", "react-dom"],
          charts: ["recharts"],
          editor: [
            "@tiptap/core",
            "@tiptap/react",
            "@tiptap/starter-kit",
            "@tiptap/pm",
            "@tiptap/suggestion",
            "@tiptap/extension-mention",
          ],
        },
      },
    },
  },
});
