import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../..");
const [nonce, python] = process.argv.slice(2);
const owner = path.join(repo, ".local", "rpf-113", nonce || "");
const sha256 = bytes => createHash("sha256").update(bytes).digest("hex");
const modules = [
  "effect_oracle", "ops_oracle", "product_local_contracts", "product_local_gateway",
  "product_local_ports", "product_local_session", "product_local_verify", "rpf112_competition_gateway",
];
const runtime = [
  "runtime/__init__.py", "runtime/runproof_runtime/__init__.py",
  "runtime/runproof_runtime/effectwitness/__init__.py",
  ...modules.map(name => "runtime/runproof_runtime/effectwitness/" + name + ".py"),
];
const support = ["competition-server.cjs", "start.ps1", "stop.ps1", "verify-witness.ps1", "START_HERE.zh-CN.md"];
const asset = /^[A-Za-z0-9_-]+\.(?:js|css|svg|png|webp|jpg|woff2)$/;

function run(exe, args, options = {}) {
  const result = spawnSync(exe, args, { cwd: repo, timeout: 180000, maxBuffer: 4 * 1024 * 1024, ...options });
  if (result.status !== 0) throw Error(result.error?.message || result.stderr?.toString() || exe + " failed");
  return result.stdout;
}

function git(...args) {
  return run("git", args).toString().trim();
}

function checkedDirectory(dir) {
  if (fs.existsSync(dir)) {
    if (fs.realpathSync.native(dir) !== dir || !fs.lstatSync(dir).isDirectory()) throw Error("LINKED_OUTPUT");
  } else fs.mkdirSync(dir);
}

if (process.argv.length !== 4 || !/^[a-f0-9]{32}$/.test(nonce || "")
  || !path.isAbsolute(python || "") || /WindowsApps|PyManager/i.test(python)
  || !fs.lstatSync(python).isFile()) throw Error("Usage: node build-bundle.mjs <fresh-32hex> <absolute CPython>");
if (fs.realpathSync.native(repo) !== repo || git("rev-parse", "--show-toplevel").replaceAll("/", path.sep) !== repo) {
  throw Error("REPOSITORY_IDENTITY");
}
const source = git("rev-parse", "HEAD");
if (!/^[a-f0-9]{40}$/.test(source)) throw Error("SOURCE_REQUIRED");
const inputs = ["web", "index.html", "package.json", "package-lock.json", "vite.config.ts", "tsconfig.json", ...runtime];
if (git("status", "--porcelain", "--untracked-files=all", "--", ...inputs)) throw Error("BUILD_SOURCE_DIRTY");
if (git("check-ignore", "--", path.relative(repo, owner).split(path.sep).join("/")) === "") throw Error("OUTPUT_NOT_IGNORED");
checkedDirectory(path.join(repo, ".local"));
checkedDirectory(path.join(repo, ".local", "rpf-113"));
fs.mkdirSync(owner);  // Exclusive. Existing evidence remains intact.
const env = { TEMP: owner, TMP: owner, VITE_CONTROL_PLANE_DATA_SOURCE: "fixture" };
for (const key of ["SystemRoot", "WINDIR", "SystemDrive", "ComSpec"]) {
  if (process.env[key]) env[key] = process.env[key];
}
const stage = path.join(owner, "stage");
const site = path.join(stage, "site");
fs.mkdirSync(stage);
run(process.execPath, ["node_modules/typescript/bin/tsc", "--noEmit"], { env, stdio: "inherit" });
run(process.execPath, ["--input-type=module", "-e",
  "import {build} from 'vite'; await build({envDir:false,publicDir:false,build:{outDir:process.argv[1],sourcemap:false,emptyOutDir:false}})",
  site], { env, stdio: "inherit" });

const entries = [];
function record(member) {
  const file = path.join(stage, member);
  if (!fs.lstatSync(file).isFile() || fs.realpathSync.native(file) !== file) throw Error("LINKED_MEMBER");
  const bytes = fs.readFileSync(file);
  entries.push({ path: member, bytes: bytes.length, sha256: sha256(bytes) });
}
function copy(member, bytes) {
  const dest = path.join(stage, member);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, bytes, { flag: "wx" });
  record(member);
}
if (fs.readdirSync(site).sort().join(",") !== "assets,index.html") throw Error("UNEXPECTED_SITE_ROOT");
record("site/index.html");
for (const name of fs.readdirSync(path.join(site, "assets"))) {
  if (!asset.test(name)) throw Error("UNEXPECTED_SITE_ASSET: " + name);
  record("site/assets/" + name);
}
for (const name of runtime) copy(name, run("git", ["show", source + ":" + name]));
for (const name of support) copy(name, fs.readFileSync(path.join(here, name)));
entries.sort((a, b) => a.path.localeCompare(b.path, "en"));

const pyVersion = run(python, ["-I", "-B", "-c", "import platform,sqlite3; print(platform.python_version(),sqlite3.sqlite_version)"], { env }).toString().trim();
const manifest = {
  schema: "runproof-competition-bundle/v1", source_commit: source,
  build: { node: process.versions.node, python_sqlite: pyVersion, generator_sha256: sha256(fs.readFileSync(fileURLToPath(import.meta.url))) },
  mode: ["CONTROLLED_LOCAL", "RULE_POLICY", "PROVIDER_0"],
  issuer: "NOT_ESTABLISHED", release_eligible: false,
  members: entries,
};
fs.writeFileSync(path.join(stage, "bundle-manifest.json"), JSON.stringify(manifest, null, 2) + "\n", { flag: "wx" });
const zip = path.join(owner, "EffectWitness-Competition-Demo-" + source.slice(0, 12) + ".zip");
run(python, ["-I", "-B", "-c", [
  "import json,pathlib,sys,zipfile",
  "root=pathlib.Path(sys.argv[1])",
  "manifest=json.loads((root/'bundle-manifest.json').read_text(encoding='utf-8'))",
  "names=sorted([row['path'] for row in manifest['members']]+['bundle-manifest.json'])",
  "with zipfile.ZipFile(sys.argv[2],'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:",
  "    for name in names:",
  "        info=zipfile.ZipInfo(name)",
  "        info.create_system=3",
  "        info.external_attr=0o100644<<16",
  "        archive.writestr(info,(root/name).read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)",
].join("\n"), stage, zip], { env });
const bytes = fs.readFileSync(zip);
if (bytes.length >= 500_000_000) throw Error("BUNDLE_SIZE_LIMIT");
const digest = sha256(bytes);
fs.writeFileSync(zip + ".sha256", digest + "  " + path.basename(zip) + "\n", { flag: "wx" });
console.log(JSON.stringify({ zip, bytes: bytes.length, sha256: digest, members: entries.length + 1, source }));
