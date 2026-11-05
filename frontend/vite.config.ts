/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = process.env.BOOKMIND_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: backend, changeOrigin: true } },
  },
  build: {
    rollupOptions: {
      // Libraries change less often than the app: separate files stay cached between releases.
      output: { manualChunks: { react: ["react", "react-dom"], markdown: ["react-markdown", "remark-gfm"] } },
    },
  },
  test: {
    environment: "jsdom",
    pool: "threads", // forks can time out starting on a busy Windows machine
    include: ["src/**/*.test.{ts,tsx}"],
    testTimeout: 15000, // rendering the whole landing page can take seconds on a busy machine
  },
});
