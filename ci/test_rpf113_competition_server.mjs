import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { test } from "node:test";
import serverModule from "../demo/competition-bundle/competition-server.cjs";

test("static routing and API admission reject unexpected inputs without a Gateway", async () => {
  const token = "a".repeat(64);
  const server = serverModule.createServer(new Map([
    ["index.html", Buffer.from("<html>public</html>")],
    ["assets/main-A1.js", Buffer.from("/* public */")],
  ]), token);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const validOrigin = "http://127.0.0.1:4187";
  function request(path, { method = "GET", headers = {}, body } = {}) {
    return new Promise((resolve, reject) => {
      const req = http.request({
        hostname: "127.0.0.1", port: server.address().port, path, method,
        headers: { Host: "127.0.0.1:4187", ...headers },
      }, async res => {
        const chunks = [];
        for await (const chunk of res) chunks.push(chunk);
        resolve({ status: res.statusCode, text: Buffer.concat(chunks).toString(), headers: res.headers });
      });
      req.on("error", reject);
      req.end(body);
    });
  }
  try {
    for (const [path, status] of [
      ["/effectwitness/live-local?session=" + "a".repeat(32), 200], ["/assets/main-A1.js", 200],
      ["/api", 404], ["/runtime/runproof_runtime/__init__.py", 404], ["/.local/ledger.sqlite", 404],
      ["/start.ps1", 404], ["/assets/../start.ps1", 400], ["/assets/%2e%2e/start.ps1", 400],
      ["/assets/%256d.js", 400], ["/effectwitness-product-api/not-routed", 404],
    ]) assert.equal((await request(path)).status, status, path);
    assert.equal((await request("/", { headers: { Host: "localhost:4187" } })).status, 403);
    assert.equal((await request("/", { method: "POST" })).status, 405);
    assert.equal((await request("/", { method: "PUT" })).status, 405);
    const options = { method: "POST", body: "{}", headers: { "Content-Type": "application/json", "Content-Length": 2 } };
    const route = "/effectwitness-product-api/session";
    assert.equal((await request(route, options)).status, 403);
    assert.equal((await request(route, { ...options, headers: { ...options.headers, Origin: "http://example.invalid" } })).status, 403);
    assert.equal((await request(route, { ...options, headers: { ...options.headers, Origin: validOrigin,
      "Content-Type": "text/plain" } })).status, 400);
    const staticPage = await request("/");
    assert(!staticPage.text.includes(token));
    assert(!JSON.stringify(staticPage.headers).includes(token));
  } finally {
    server.closeAllConnections();
    await new Promise((resolve, reject) => server.close(err => err ? reject(err) : resolve()));
  }
});
