"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { seal, verify, createServer, listen, request } = require("./effectwitness-preview.cjs");

function fixture() {
  const root = path.resolve(__dirname, "../.local/rpf-99-product-delivery");
  fs.mkdirSync(root, { recursive: true });
  if (fs.realpathSync(root) !== root) throw Error("LINKED_TEST_ROOT");
  const run = fs.mkdtempSync(path.join(root, "test-"));
  const bundle = path.join(run, "bundle");
  fs.mkdirSync(path.join(bundle, "site", "assets"), { recursive: true });
  fs.writeFileSync(path.join(bundle, "site", "index.html"), "<h1>Recorded</h1>");
  fs.writeFileSync(path.join(bundle, "site", "assets", "app.js"), "void 0;");
  fs.writeFileSync(path.join(bundle, "START_HERE.md"), "Recorded");
  fs.copyFileSync(path.join(__dirname, "effectwitness-preview.cjs"), path.join(bundle, "effectwitness-preview.cjs"));
  return { run, bundle };
}

test("manifest rejects missing, changed, extra, linked and foreign schema members", () => {
  const { run, bundle } = fixture();
  assert.throws(() => verify(bundle), /MANIFEST_MISSING/);
  seal(bundle, "a".repeat(40));
  const member = path.join(bundle, "site", "index.html");
  const bytes = fs.readFileSync(member);
  fs.writeFileSync(member, "tampered");
  assert.throws(() => verify(bundle), /MANIFEST_MISMATCH/);
  fs.writeFileSync(member, bytes);
  const extra = path.join(bundle, "unexpected.exe");
  fs.writeFileSync(extra, "");
  assert.throws(() => verify(bundle), /MANIFEST_MISMATCH/);
  fs.unlinkSync(extra);
  const link = path.join(bundle, "site", "escape");
  fs.mkdirSync(path.join(run, "outside"));
  fs.symlinkSync(path.join(run, "outside"), link, process.platform === "win32" ? "junction" : "dir");
  assert.throws(() => verify(bundle), /LINKED_MEMBER/);
  process.platform === "win32" ? fs.rmdirSync(link) : fs.unlinkSync(link);
  const manifestPath = path.join(bundle, "manifest.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath));
  fs.writeFileSync(manifestPath, JSON.stringify({ ...manifest, issuer_signature: "untrusted" }, null, 2) + "\n");
  assert.throws(() => verify(bundle), /MANIFEST_MISMATCH/);
  fs.writeFileSync(manifestPath, JSON.stringify({ ...manifest, schema: "unknown" }, null, 2) + "\n");
  assert.throws(() => verify(bundle), /MANIFEST_MISMATCH/);
});

test("loopback serves only verified static GET and HEAD requests", async () => {
  const { bundle } = fixture();
  const sealed = seal(bundle, "b".repeat(40));
  const port = Number(process.env.RPF99_TEST_PORT || 4174);
  const server = createServer(sealed, port);
  await listen(server, port);
  try {
    await assert.rejects(listen(createServer(sealed, port), port), { code: "EADDRINUSE" });
    for (const [url, status, options] of [
      ["/", 200], ["/effectwitness/workbench?domain=ops&event=one", 200],
      ["/assets/app.js", 200, { method: "HEAD" }], ["/assets/missing.js", 404],
      ["/api/v1", 503], ["/effectwitness-api", 503], ["/%61pi/v1", 503],
      ["/", 403, { headers: { Host: "external.invalid" } }], ["/", 405, { method: "POST" }],
      ["/../manifest.json", 400], ["/%2e%2e/manifest.json", 400], ["/%252e%252e/file", 400],
      ["/manifest.json", 404], ["/START_HERE.md", 404],
    ]) assert.equal(await request(port, url, options), status, url);
  } finally { await new Promise((resolve) => server.close(resolve)); }
});
