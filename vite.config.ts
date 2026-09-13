import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 4173,
    strictPort: true,
    proxy: {
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
