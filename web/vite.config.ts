import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const srcPath = (path: string) => new URL(`./src/${path}`, import.meta.url).pathname;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@app": srcPath("app"),
      "@routes": srcPath("routes"),
      "@features": srcPath("features"),
      "@shared": srcPath("shared"),
      "@lib": srcPath("lib")
    }
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/ws": {
        target: "ws://127.0.0.1:8765",
        ws: true
      }
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    projects: [
      {
        extends: true,
        test: {
          name: "web-unit",
          include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
          exclude: ["src/App.test.tsx"],
          sequence: { groupOrder: 0 }
        }
      },
      {
        extends: true,
        test: {
          name: "app-integration",
          include: ["src/App.test.tsx"],
          sequence: { groupOrder: 1 }
        }
      }
    ]
  }
});
