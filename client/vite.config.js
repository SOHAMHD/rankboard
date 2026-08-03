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
        //
        // Deliberately the function form, not the `{ name: [packages] }` object
        // form. The object form treats each string as a package ENTRY that Rollup
        // must resolve, which breaks on packages that only publish subpath
        // exports — @tiptap/pm has no "." export, so naming it there fails the
        // build outright. Matching resolved module paths avoids that entirely and
        // also catches the transitive prosemirror-* and d3-* packages, which is
        // where most of the weight actually is.
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (id.includes("@tiptap") || id.includes("prosemirror")) return "editor";
          if (id.includes("recharts") || id.includes("d3-") || id.includes("victory")) return "charts";
        },
      },
    },
  },
});
