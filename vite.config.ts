import { defineConfig, type Plugin, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

const labEnabled = process.env.RPF_EW_LAB_ENABLED === "1";
const labToken = process.env.RPF_EW_LAB_GATEWAY_TOKEN || "";
const taskOutput = process.env.RPF_EW_LAB_TASK_OUTPUT === "1";
const taskId = process.env.RPF_EW_LAB_TASK_ID === "rpf-60" ? "rpf-60" : process.env.RPF_EW_LAB_TASK_ID === "rpf-46" ? "rpf-46" : "rpf-45";
const labBoundary: Plugin = {
  name: "local-lab-boundary",
  configureServer(server) {
    server.middlewares.use((request, response, next) => {
      if (!request.url?.startsWith("/effectwitness-api")) return next();
      const allowedHosts = ["127.0.0.1:4185"];
      const origin = request.headers.origin;
      const validOrigin = origin === "http://127.0.0.1:4185";
      const denied = !allowedHosts.includes(request.headers.host || "") ||
        (origin !== undefined && !validOrigin) || (request.method === "POST" && !validOrigin);
      if (denied || !labEnabled || labToken.length < 32) {
        response.statusCode = denied ? 403 : 503;
        response.setHeader("Content-Type", "application/json");
        response.setHeader("Cache-Control", "no-store");
        response.end(JSON.stringify({ schema_version: "rpf-lab-v1", error_code: denied ? "ORIGIN_REJECTED" : "LAB_DISABLED" }));
        return;
      }
      next();
    });
  },
};

export default defineConfig({
  plugins: [labBoundary, react()],
  ...(taskOutput ? { cacheDir: `.local/${taskId}/node-cache`, build: { outDir: `.local/${taskId}/web-build` } } : {}),
  server: {
    host: "127.0.0.1",
    watch: { ignored: ["**/.local/**", "**/docs/reviews/**"] },
    port: labEnabled ? 4185 : 4173,
    strictPort: true,
    proxy: {
      ...(labEnabled && labToken.length >= 32 ? {
        "/effectwitness-api": {
          target: "http://127.0.0.1:8765",
          changeOrigin: true,
          configure: (proxy: Parameters<NonNullable<ProxyOptions["configure"]>>[0]) => {
            proxy.on("proxyReq", (request) => request.setHeader("Authorization", "Bearer " + labToken));
            proxy.removeAllListeners("error");
            proxy.on("error", (_error, _request, response) => {
              if ("writeHead" in response && !response.headersSent) {
                response.writeHead(503, { "Content-Type": "application/json", "Cache-Control": "no-store" });
                response.end(JSON.stringify({ schema_version: "rpf-lab-v1", error_code: "GATEWAY_UNAVAILABLE" }));
              }
            });
          },
        },
      } : {}),
      "/api": {
        target: process.env.RPF_CONTROL_PLANE_PROXY_TARGET || "http://127.0.0.1:8081",
        changeOrigin: false,
        configure: (proxy) => {
          const readToken = process.env.RPF_CONTROL_PLANE_READ_TOKEN || process.env.RPF_AUTH_READ_TOKEN;
          proxy.on("proxyReq", (request) => {
            if (readToken) request.setHeader("Authorization", "Bearer " + readToken);
          });
        },
      },
    },
  },
});
