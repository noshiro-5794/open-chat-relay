import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "./",
  plugins: [react()],
  resolve: {
    alias: {
      "@openchatrelay/sdk": path.resolve(rootDir, "../../packages/sdk-js/src/index.ts"),
    },
  },
  server: {
    port: 5174,
  },
  build: {
    outDir: "dist",
  },
});
