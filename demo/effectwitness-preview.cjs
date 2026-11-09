"use strict";

const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const crypto = require("node:crypto");

const manifestName = "manifest.json";
const schema = "effectwitness-delivery-v1";
const mode = "RECORDED_NO_PROVIDER_NO_LOCAL_BUSINESS_WRITE";
const routes = new Set(["/", "/overview", "/effectwitness/workbench", "/effectwitness/recorded",
  "/effectwitness", "/effectwitness/explorations", "/effectwitness/cross-domain"]);
const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
  ".ico": "image/x-icon", ".woff2": "font/woff2", ".json": "application/json" };
const sha = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");

function readRegular(file) {
  const before = fs.lstatSync(file);
  if (!before.isFile() || before.nlink !== 1) throw Error("NON_REGULAR_MEMBER");
  const fd = fs.openSync(file, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0));
  try {
    const actual = fs.fstatSync(fd);
    if (!actual.isFile() || actual.nlink !== 1 || actual.ino !== before.ino || actual.dev !== before.dev) {
      throw Error("MEMBER_REPLACED");
    }
    return fs.readFileSync(fd);
  } finally { fs.closeSync(fd); }
}

function inventory(root) {
  root = path.resolve(root);
  for (let dir = root; ; dir = path.dirname(dir)) {
    if (fs.lstatSync(dir).isSymbolicLink()) throw Error("LINKED_ROOT");
    if (dir === path.dirname(dir)) break;
  }
  const files = new Map();
  const names = new Set();
  function walk(dir, prefix) {
    for (const name of fs.readdirSync(dir).sort()) {
      if (!/^[a-zA-Z0-9_-][a-zA-Z0-9_.-]*$/.test(name) || name.endsWith(".")) throw Error("UNSAFE_MEMBER_NAME");
      const member = prefix + name;
      if (names.has(member.toLowerCase())) throw Error("MEMBER_CASE_COLLISION");
      names.add(member.toLowerCase());
      const full = path.join(dir, name);
      const info = fs.lstatSync(full);
      if (info.isSymbolicLink()) throw Error("LINKED_MEMBER");
      if (info.isDirectory()) walk(full, member + "/");
      else files.set(member, readRegular(full));
    }
  }
  walk(root, "");
  return files;
}

function describe(files) {
  return [...files].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([name, bytes]) => ({ name, bytes: bytes.length, sha256: sha(bytes) }));
}

function requireBundle(files) {
  for (const name of ["site/index.html", "effectwitness-preview.cjs", "START_HERE.md"]) {
    if (!files.has(name)) throw Error("REQUIRED_MEMBER_MISSING");
  }
}

function seal(root, commit) {
  if (!/^[a-f0-9]{40}$/.test(commit)) throw Error("INVALID_COMMIT");
  const files = inventory(root);
  requireBundle(files);
  const manifest = { schema, mode, commit, files: describe(files) };
  fs.writeFileSync(path.join(root, manifestName), JSON.stringify(manifest, null, 2) + "\n", { flag: "wx" });
  return verify(root);
}

function verify(root) {
  const files = inventory(root);
  const raw = files.get(manifestName);
  if (!raw) throw Error("MANIFEST_MISSING");
  const manifest = JSON.parse(raw);
  files.delete(manifestName);
  requireBundle(files);
  const expected = { schema, mode, commit: manifest.commit, files: describe(files) };
  if (!/^[a-f0-9]{40}$/.test(manifest.commit) ||
      raw.toString("utf8") !== JSON.stringify(expected, null, 2) + "\n") throw Error("MANIFEST_MISMATCH");
  return { manifest: expected, manifestSha256: sha(raw), files };
}

function requestPath(url) {
  const raw = url.split("?")[0];
  if (!raw.startsWith("/") || raw.includes("//") || /%(?:2f|5c|25)/i.test(raw)) throw Error("INVALID_PATH");
  const decoded = decodeURIComponent(raw);
  if (/[\\\x00-\x1f\x7f:#]/.test(decoded) || decoded.split("/").some((part) => part === "." || part === "..")) {
    throw Error("INVALID_PATH");
  }
  return decoded;
}

function createServer(bundle, port) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw Error("INVALID_PORT");
  return http.createServer((req, res) => {
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Content-Security-Policy", "default-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");
    function reply(status, body, type = "text/plain; charset=utf-8") {
      res.writeHead(status, { "Content-Type": type, "Content-Length": Buffer.byteLength(body) });
      res.end(req.method === "HEAD" ? undefined : body);
    }
    if (req.headers.host !== `127.0.0.1:${port}`) return reply(403, "HOST_REJECTED");
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.setHeader("Allow", "GET, HEAD");
      return reply(405, "METHOD_REJECTED");
    }
    let target;
    try { target = requestPath(req.url); } catch { return reply(400, "INVALID_PATH"); }
    if (/^\/(api|effectwitness-api)(\/|$)/i.test(target)) {
      return reply(503, '{"schema_version":"rpf-lab-v1","error_code":"LAB_DISABLED"}', "application/json");
    }
    const name = routes.has(target) ? "/index.html" : target;
    const bytes = bundle.files.get("site" + name);
    const type = types[path.extname(name)];
    if (!bytes || !type) return reply(404, "NOT_FOUND");
    reply(200, bytes, type);
  });
}

function listen(server, port) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", resolve);
  });
}

function request(port, target, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ hostname: "127.0.0.1", port, path: target, ...options }, (res) => {
      res.resume();
      res.on("end", () => resolve(res.statusCode));
      res.on("error", reject);
    });
    req.setTimeout(5000, () => req.destroy(Error("HTTP_TIMEOUT")));
    req.on("error", reject);
    req.end();
  });
}

async function main() {
  const [command = "serve", root = __dirname, value] = process.argv.slice(2);
  if (command === "seal" || command === "verify") {
    const { manifest, manifestSha256 } = command === "seal" ? seal(root, value) : verify(root);
    console.log(JSON.stringify({ status: "VERIFIED", commit: manifest.commit, manifestSha256, members: manifest.files.length }));
    return;
  }
  if (command !== "serve" && command !== "probe") throw Error("UNKNOWN_COMMAND");
  const port = Number(value ?? 4174);
  const bundle = verify(root);
  const server = createServer(bundle, port);
  await listen(server, port);
  if (command === "probe") {
    try {
      const asset = bundle.manifest.files.find(({ name }) => name.startsWith("site/assets/") && name.endsWith(".js"));
      if (!asset) throw Error("JS_ASSET_MISSING");
      for (const [target, expected] of [["/", 200], ["/effectwitness/workbench?domain=ops", 200],
        [asset.name.slice(4), 200], ["/api/v1", 503], ["/effectwitness-api", 503]]) {
        if (await request(port, target) !== expected) throw Error("HTTP_PROBE_FAILED");
      }
      console.log(JSON.stringify({ status: "VERIFIED", bind: `127.0.0.1:${port}`,
        commit: bundle.manifest.commit, manifestSha256: bundle.manifestSha256, http: "PASS" }));
    } finally { await new Promise((resolve) => server.close(resolve)); }
    return;
  }
  console.log(`RECORDED preview at http://127.0.0.1:${port}/effectwitness/workbench`);
  for (const signal of ["SIGINT", "SIGTERM"]) process.once(signal, () => server.close());
}

module.exports = { seal, verify, createServer, listen, request };
if (require.main === module) main().catch((error) => { console.error(error.message); process.exitCode = 1; });
