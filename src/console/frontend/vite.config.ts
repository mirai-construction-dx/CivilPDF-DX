import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const apiTarget = (process.env.VITE_API_URL || "http://localhost:8000")
  .replace(/\/+$/, "")
  .replace(/\/api\/v1$/, "");

const securityHeaders = {
  "Content-Security-Policy":
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "no-referrer",
  "Permissions-Policy":
    "camera=(), microphone=(), geolocation=(), interest-cohort=()",
};

function securityHeadersPlugin(): Plugin {
  return {
    name: "security-headers",
    configureServer(server) {
      server.middlewares.use((_req, res, next) => {
        for (const [key, value] of Object.entries(securityHeaders)) {
          res.setHeader(key, value);
        }
        next();
      });
    },
    configurePreviewServer(server) {
      server.middlewares.use((_req, res, next) => {
        for (const [key, value] of Object.entries(securityHeaders)) {
          res.setHeader(key, value);
        }
        next();
      });
    },
  };
}

export default defineConfig(({ command }) => {
  // 外部 shell の NODE_ENV=development が vite build に漏れると DEV バンドル
  // (jsxDEV / import.meta.env.DEV=true → 認証スキップ) が本番配信される。
  // build 時は必ず production へ固定する (2026-08-04 の本番 DEV バンドル事故の再発防止)。
  if (command === "build") process.env.NODE_ENV = "production";
  // index.html の %VITE_APP_TITLE% / %VITE_FAVICON% を注入する。
  // favicon は本番 (build) = アンバー / dev サーバー = 紫でタブを見分ける。
  process.env.VITE_APP_TITLE ??= "CivilPDF DX";
  process.env.VITE_FAVICON ??=
    command === "build" ? "/favicon-prod.svg" : "/favicon.svg";
  return {
    plugins: [react(), tailwindcss(), securityHeadersPlugin()],
    server: {
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      port: 4173,
      host: true,
      // Cloudflare Tunnel 経由の公開ホスト名（本番 + MVP プレビュー）
      allowedHosts: [
        "civilpdf.mirai-dx-platform.com",
        "civilpdf-mvp.mirai-dx-platform.com",
      ],
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      chunkSizeWarningLimit: 400,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("node_modules")) {
              if (id.includes("react-dom") || id.includes("react/"))
                return "vendor";
              if (id.includes("react-router")) return "router";
              if (id.includes("@tanstack")) return "query";
              if (id.includes("zustand")) return "state";
              if (id.includes("axios")) return "http";
              if (id.includes("jose") || id.includes("jwt")) return "auth";
            }
          },
        },
      },
    },
  };
});
