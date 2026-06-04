import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Builds a single embeddable JS bundle. Host pages drop in:
//   <div id="finflash-widget" data-api-base="https://api.example.com"></div>
//   <script src="finflash-widget.iife.js"></script>
export default defineConfig({
  plugins: [react()],
  define: { "process.env.NODE_ENV": '"production"' },
  build: {
    outDir: "dist-widget",
    lib: {
      entry: "src/widget.tsx",
      name: "FinFlashWidget",
      formats: ["iife"],
      fileName: () => "finflash-widget.iife.js",
    },
  },
});
