import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../..");
const [nonce, python, profile] = process.argv.slice(2);
const complete = profile === "--complete";
const ownerBase = complete ? "rpf-114-complete" : "rpf-113";
const owner = path.join(repo, ".local", ownerBase, nonce || "");
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

if (!(process.argv.length === 4 || (process.argv.length === 5 && complete)) || !/^[a-f0-9]{32}$/.test(nonce || "")
  || !path.isAbsolute(python || "") || /WindowsApps|PyManager/i.test(python)
  || !fs.lstatSync(python).isFile()) throw Error("Usage: node build-bundle.mjs <fresh-32hex> <absolute CPython> [--complete]");
if (fs.realpathSync.native(repo) !== repo || git("rev-parse", "--show-toplevel").replaceAll("/", path.sep) !== repo) {
  throw Error("REPOSITORY_IDENTITY");
}
const source = git("rev-parse", "HEAD");
if (!/^[a-f0-9]{40}$/.test(source)) throw Error("SOURCE_REQUIRED");
const webConfig = ["index.html", "package.json", "package-lock.json", "vite.config.ts", "tsconfig.json"];
const inputs = ["web", ...webConfig, ...runtime];
if (git("status", "--porcelain", "--untracked-files=all", "--", ...inputs)) throw Error("BUILD_SOURCE_DIRTY");
if (git("check-ignore", "--", path.relative(repo, owner).split(path.sep).join("/")) === "") throw Error("OUTPUT_NOT_IGNORED");
checkedDirectory(path.join(repo, ".local"));
checkedDirectory(path.join(repo, ".local", ownerBase));
if (complete) checkedDirectory(owner);
else fs.mkdirSync(owner);  // Legacy output is exclusive.
const env = { TEMP: owner, TMP: owner, VITE_CONTROL_PLANE_DATA_SOURCE: "fixture" };
for (const key of ["SystemRoot", "WINDIR", "SystemDrive", "ComSpec"]) {
  if (process.env[key]) env[key] = process.env[key];
}
const stage = path.join(owner, "stage");
const app = complete ? "app/" : "";
const site = path.join(stage, app, "site");
fs.mkdirSync(stage);  // Existing output is never overwritten.
const deliverables = path.join(owner, "deliverables");
if (complete) {
  fs.mkdirSync(path.join(stage, "app"));
  checkedDirectory(deliverables);
}
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
record(app + "site/index.html");
for (const name of fs.readdirSync(path.join(site, "assets"))) {
  if (!asset.test(name)) throw Error("UNEXPECTED_SITE_ASSET: " + name);
  record(app + "site/assets/" + name);
}
const frozenBytes = name => run("git", ["show", source + ":" + name]);
const tracked = (...prefixes) => git("ls-tree", "-r", "--name-only", source, "--", ...prefixes).split("\n").filter(Boolean);
const runtimeRoot = "runtime/runproof_runtime/";
function pythonClosure(roots) {
  return JSON.parse(run(python, ["-I", "-B", "-c", [
    "import ast,json,pathlib,subprocess,sys",
    "available,roots,commit=json.load(sys.stdin)",
    "available=set(available)",
    "seen=set()",
    "while roots:",
    " p=roots.pop()",
    " if p in seen: continue",
    " if p not in available: raise ValueError('Missing runtime input: '+p)",
    " seen.add(p)",
    " tree=ast.parse(subprocess.check_output(['git','show',commit+':'+p]))",
    " folder=pathlib.PurePosixPath(p).parent",
    " for node in ast.walk(tree):",
    "  if not isinstance(node,ast.ImportFrom) or not node.level: continue",
    "  parent=folder",
    "  for _ in range(node.level-1): parent=parent.parent",
    "  for name in ([node.module] if node.module else [a.name for a in node.names]):",
    "   base=(parent/name.replace('.','/')).as_posix()",
    "   for candidate in (base+'.py',base+'/__init__.py'):",
    "    if candidate in available: roots.append(candidate)",
    "print(json.dumps(sorted(seen)))",
  ].join("\n")], { input: JSON.stringify([tracked("runtime"), roots, source]) }));
}
let sourceFixtures = {};
if (complete) {
  const entry = runtimeRoot + "effectwitness/";
  const appFiles = pythonClosure([...runtime.slice(0, 3), entry + "competition_agent_gateway.py",
    entry + "competition_agent_verify.py"]);
  for (const name of appFiles) copy(app + name, frozenBytes(name));
  for (const name of support) copy(app + name, frozenBytes("demo/competition-bundle/" + name));
  copy("app/bundle-manifest.json", Buffer.from(JSON.stringify({
    schema: "runproof-competition-complete/v1", source_commit: source,
    members: entries.filter(e => e.path.startsWith("app/site/")).map(e => ({ ...e, path: e.path.slice(4) })),
  }) + "\n"));

  const allResearch = tracked(entry).filter(p => /\/pge_r110_[a-z_]+\.py$/.test(p));
  const platform = ["agent.py", "agent_contract.py", "deepseek_provider.py", "runner.py", "durable_worker.py",
    "verifier.py", "evaluation.py"].map(name => runtimeRoot + name);
  const sources = new Set([...pythonClosure([...appFiles, ...platform, ...allResearch]), ...webConfig,
    ...tracked("web/src", "control-plane/src", "control-plane/pom.xml", "integrations/jiuwenswarm",
      "runtime/requirements.txt", "demo/competition-bundle")]);
  const fixtureCopies = new Map();
  for (const name of sources) {
    if (!name.startsWith("web/src/") || !/\.tsx?$/.test(name)) continue;
    const bytes = frozenBytes(name).toString();
    for (const [, relative] of bytes.matchAll(/(?:from\s+|import\s*)["'](\.[^"']+\.json)(?:\?raw)?["']/g)) {
      const input = path.posix.normalize(path.posix.join(path.posix.dirname(name), relative));
      if (input.startsWith("runtime/reviewed-") || input === "demo/rpf-19-golden-demo-v1.json") {
        fixtureCopies.set(input, "source/" + input);
      }
      else if (/^spikes\/rpf-(?:43|44|46|47)\/[A-Za-z0-9_.-]+\.json$/.test(input)) {
        fixtureCopies.set(input, "source/build-inputs/" + input.split("/").slice(1).join("-"));
      } else if (!input.startsWith("web/src/")) throw Error("UNREVIEWED_WEB_INPUT: " + input);
    }
  }
  sourceFixtures = Object.fromEntries(fixtureCopies);
  for (const name of sources) copy("source/" + name, frozenBytes(name));
  for (const [name, dest] of fixtureCopies) copy(dest, frozenBytes(name));
  copy("START_HERE.zh-CN.md", frozenBytes("demo/competition-bundle/README-COMPLETE.zh-CN.md"));
  copy("ARCHITECTURE.md", Buffer.from([
    "# RunProof EffectWitness", "",
    "app/ is the offline reference Agent, Controller, SQLite ports, readback and Witness CLI.",
    "source/runtime retains the existing Agent, DeepSeek and RPF-110 interface sources. Java Control Plane",
    "and JiuwenSwarm MCP are source extensions. The offline app uses reviewed Web fixtures for platform pages.",
    "", "## Rebuild the Web", "",
    "Work on a fresh copy of source/. For each web_build_inputs entry in the root manifest,",
    "copy the archived path (relative to the project ZIP root) to its key (relative to the source copy),",
    "creating parent directories. Existing runtime inputs already have their intended paths.",
    "Then use the pinned package-lock with npm ci and npm run build. The supplied app/site needs neither step.",
    "", "## Architecture boundaries", "",
    "competition_agent.py proposes; competition_agent_session.py gates and executes approved intents;",
    "product_local_ports.py reads receipts in query-only mode; competition_agent_verify.py checks the certificate.",
    "Reference policy executes locally. Provider and MCP sources are extension interfaces.", "",
  ].join("\n")));
  const notices = ["# Third-party notices", "", "Browser runtime license notices follow.", ""];
  for (const name of ["react", "react-dom", "scheduler"]) {
    notices.push("## " + name, "", fs.readFileSync(path.join(repo, "node_modules", name, "LICENSE"), "utf8"), "");
  }
  copy("LICENSES.md", Buffer.from(notices.join("\n")));
} else {
  for (const name of runtime) copy(name, frozenBytes(name));
  for (const name of support) copy(name, fs.readFileSync(path.join(here, name)));
}
entries.sort((a, b) => a.path.localeCompare(b.path, "en"));

const pyVersion = run(python, ["-I", "-B", "-c", "import platform,sqlite3; print(platform.python_version(),sqlite3.sqlite_version)"], { env }).toString().trim();
const manifest = {
  schema: complete ? "runproof-competition-complete/v1" : "runproof-competition-bundle/v1", source_commit: source,
  build: { node: process.versions.node, python_sqlite: pyVersion, generator_sha256: sha256(fs.readFileSync(fileURLToPath(import.meta.url))) },
  mode: [complete ? "OFFLINE_REFERENCE_AGENT" : "CONTROLLED_LOCAL", "RULE_POLICY", "PROVIDER_0"],
  issuer: "NOT_ESTABLISHED", release_eligible: false,
  ...(complete ? { web_build_inputs: sourceFixtures } : {}), members: entries,
};
fs.writeFileSync(path.join(stage, "bundle-manifest.json"), JSON.stringify(manifest, null, 2) + "\n", { flag: "wx" });
const zip = complete ? path.join(deliverables, "RunProof-EffectWitness-Complete-Project.zip")
  : path.join(owner, "EffectWitness-Competition-Demo-" + source.slice(0, 12) + ".zip");
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
