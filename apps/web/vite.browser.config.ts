import { defineConfig } from "vite";

// Serve built assets only. Never inherit the development API proxy.
export default defineConfig({
  preview: { host: "127.0.0.1", port: 4173, strictPort: true, proxy: {} },
});
