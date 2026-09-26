import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    environmentOptions: {
      jsdom: {
        url: "http://localhost/",
      },
    },
    setupFiles: ["./src/test/setup.ts"],
    // e2e/** holds Playwright specs (*.spec.ts) — excluded so vitest does not
    // try to run them with its own runner.
    exclude: ["node_modules/**", "**/.claude/**", "dist/**", "e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      exclude: ["node_modules/", "src/test/", "dist/"],
    },
  },
});
