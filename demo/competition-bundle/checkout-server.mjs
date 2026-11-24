import { build } from "vite";
import server from "./competition-server.cjs";

// Serve the checkout through the same route and API boundary used by the extracted package.
const output = await build({
  configLoader: "runner", envDir: false, publicDir: false, logLevel: "error",
  build: { write: false, sourcemap: false },
});
const site = new Map();
for (const item of output.output) {
  site.set(item.fileName, Buffer.from(item.type === "chunk" ? item.code : item.source));
}
server.createServer(site, process.env.RPF100_GATEWAY_TOKEN)
  .listen({ host: "127.0.0.1", port: 4187, exclusive: true });
