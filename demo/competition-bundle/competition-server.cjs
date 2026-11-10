"use strict";

const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { createHash } = require("node:crypto");

const origin = "http://127.0.0.1:4187";
const prefix = "/effectwitness-product-api";
const pages = new Set(["/", "/effectwitness/workbench", "/effectwitness/recorded", "/effectwitness/live-local"]);
const asset = /^assets\/[A-Za-z0-9_-]+\.(?:js|css|svg|png|webp|jpg|woff2)$/;
const types = {
  html: "text/html; charset=utf-8", js: "text/javascript; charset=utf-8", css: "text/css; charset=utf-8",
  svg: "image/svg+xml", png: "image/png", webp: "image/webp", jpg: "image/jpeg", woff2: "font/woff2",
};

function plainFile(root, name) {
  let file = root;
  for (const part of name.split("/")) {
    file = path.join(file, part);
    if (fs.lstatSync(file).isSymbolicLink() || fs.realpathSync.native(file) !== file) throw Error("LINKED_BUNDLE_PATH");
  }
  if (!fs.statSync(file).isFile()) throw Error("BUNDLE_FILE_REQUIRED");
  return fs.readFileSync(file);
}

function loadSite(root) {
  root = path.resolve(root);
  if (fs.realpathSync.native(root) !== root) throw Error("LINKED_BUNDLE_ROOT");
  const manifest = JSON.parse(plainFile(root, "bundle-manifest.json"));
  const site = new Map();
  for (const entry of manifest.members) {
    if (!entry.path.startsWith("site/")) continue;
    const name = entry.path.slice(5);
    if ((name !== "index.html" && !asset.test(name)) || site.has(name)) throw Error("INVALID_SITE_MEMBER");
    const bytes = plainFile(root, entry.path);
    if (bytes.length !== entry.bytes || createHash("sha256").update(bytes).digest("hex") !== entry.sha256) {
      throw Error("SITE_HASH_MISMATCH");
    }
    site.set(name, bytes);
  }
  if (!site.has("index.html") || site.size < 2) throw Error("MISSING_SITE");
  return site;
}

function single(req, name) {
  const values = req.headersDistinct[name] || [];
  return values.length === 1 ? values[0] : undefined;
}

function reply(res, status, bytes, headers = {}) {
  res.writeHead(status, {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
    ...headers,
    "Content-Length": bytes.length,
  });
  res.end(bytes);
}

function error(res, status, reason) {
  reply(res, status, Buffer.from(JSON.stringify({ error: reason })), { "Content-Type": "application/json" });
}

async function readBounded(stream, max) {
  const chunks = [];
  let length = 0;
  for await (const chunk of stream) {
    length += chunk.length;
    if (length > max) throw Error("BODY_LIMIT");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks, length);
}

function gateway(route, method, token, body) {
  return new Promise((resolve, reject) => {
    const headers = { Host: "127.0.0.1:8780", Origin: origin, Authorization: "Bearer " + token };
    if (method === "POST") {
      headers["Content-Type"] = "application/json";
      headers["Content-Length"] = body.length;
    }
    const upstream = http.request({
      hostname: "127.0.0.1", port: 8780, path: route, method, headers, agent: false,
      signal: AbortSignal.timeout(8000),
    }, response => {
      readBounded(response, 262144).then(bytes => resolve({ response, bytes }), reject);
    });
    upstream.on("error", reject);
    upstream.end(body);
  });
}

function createServer(site, token) {
  if (!/^[a-f0-9]{64}$/.test(token || "")) throw Error("GATEWAY_TOKEN_REQUIRED");
  const server = http.createServer({
    maxHeaderSize: 8192, requestTimeout: 8000, headersTimeout: 5000, connectionsCheckingInterval: 1000,
  }, async (req, res) => {
    const host = single(req, "host");
    const requestOrigin = single(req, "origin");
    const hasOrigin = Object.hasOwn(req.headersDistinct, "origin");
    if (req.socket.remoteAddress !== "127.0.0.1" || host !== "127.0.0.1:4187"
      || (hasOrigin && requestOrigin !== origin)) return error(res, 403, "ORIGIN_REJECTED");

    const [route, query] = req.url.split("?", 2);
    if (!/^\/[A-Za-z0-9_./-]*$/.test(route) || route.includes("//")
      || route.split("/").some(part => part === "." || part === "..")) return error(res, 400, "INVALID_PATH");

    const post = req.method === "POST";
    const get = req.method === "GET";
    const length = single(req, "content-length");
    const transfer = Object.hasOwn(req.headersDistinct, "transfer-encoding");
    if (route.startsWith(prefix + "/") || route === prefix) {
      const suffix = route.slice(prefix.length);
      const read = /^(?:\/capability|\/(?:session|witness)\/[a-f0-9]{32}|\/request\/[A-Za-z0-9_-]{8,80})$/.test(suffix);
      if (query !== undefined || (!read && suffix !== "/session")) return error(res, 404, "NOT_FOUND");
      if (!(get && read) && !(post && suffix === "/session")) return error(res, 405, "METHOD_REJECTED");
      if (post && requestOrigin !== origin) return error(res, 403, "ORIGIN_REJECTED");
      if (transfer || (post
        ? single(req, "content-type") !== "application/json" || !/^[1-9][0-9]{0,3}$/.test(length || "")
        : length !== undefined && length !== "0")) return error(res, 400, "INVALID_BODY");
      if (post && Number(length) > 4096) return error(res, 413, "BODY_LIMIT");
      try {
        const body = post ? await readBounded(req, 4096) : undefined;
        if (post && body.length !== Number(length)) return error(res, 400, "INVALID_BODY");
        const { response, bytes } = await gateway(route, req.method, token, body);
        const headers = { "Content-Type": "application/json" };
        const hash = single(response, "x-witness-sha256");
        if (suffix.startsWith("/witness/") && response.statusCode === 200 && /^[a-f0-9]{64}$/.test(hash || "")) {
          headers["X-Witness-SHA256"] = hash;
          headers["Content-Disposition"] = 'attachment; filename="rpf100-witness.json"';
        }
        return reply(res, response.statusCode, bytes, headers);
      } catch {
        return error(res, 503, "GATEWAY_UNAVAILABLE");
      }
    }

    if (!get || transfer || (length !== undefined && length !== "0")) return error(res, 405, "METHOD_REJECTED");
    const name = pages.has(route) ? "index.html" : route.slice(1);
    if (!pages.has(route) && !asset.test(name)) return error(res, 404, "NOT_FOUND");
    const bytes = site.get(name);
    if (!bytes) return error(res, 404, "NOT_FOUND");
    return reply(res, 200, bytes, { "Content-Type": types[name.split(".").at(-1)] });
  });
  server.setTimeout(10000, socket => socket.destroy());
  return server;
}

if (require.main === module) {
  createServer(loadSite(__dirname), process.env.RPF100_GATEWAY_TOKEN)
    .listen({ host: "127.0.0.1", port: 4187, exclusive: true });
}

module.exports = { createServer, loadSite };
