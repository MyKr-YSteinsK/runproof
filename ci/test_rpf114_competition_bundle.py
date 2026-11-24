"""Independent complete-project archive admission and extraction."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import unittest
from zipfile import ZipFile

EXACT = {"ARCHITECTURE.md", "LICENSES.md", "START_HERE.zh-CN.md", "bundle-manifest.json",
         "app/bundle-manifest.json", "app/competition-server.cjs", "app/start.ps1", "app/stop.ps1",
         "app/verify-witness.ps1", "app/START_HERE.zh-CN.md", "app/site/index.html"}
APP = re.compile(r"app/(?:runtime/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\.py|site/assets/[A-Za-z0-9_-]+\.(?:js|css|svg|png|webp|jpg|woff2))")
SOURCE = re.compile(
    r"source/(?:index\.html|package(?:-lock)?\.json|tsconfig\.json|vite\.config\.ts|"
    r"web/src/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:ts|tsx|css|json|svg|png)|"
    r"runtime/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_.-]+\.(?:py|txt|json)|"
    r"control-plane/(?:pom\.xml|src/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.(?:java|properties))|"
    r"integrations/jiuwenswarm/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.(?:py|md|txt)|"
    r"demo/(?:rpf-19-golden-demo-v1\.json|competition-bundle/[A-Za-z0-9_.-]+\.(?:md|ps1|mjs|cjs))|"
    r"build-inputs/rpf-(?:43|44|46|47)-[A-Za-z0-9_.-]+\.json)"
)
SECRET = re.compile(rb"(?i)(?:[A-Z]:[/\\](?:Users|CS)[/\\]|sk-(?:proj-)?[a-z0-9_-]{32,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
REQUIRED = EXACT | {
    "app/runtime/runproof_runtime/effectwitness/competition_agent.py",
    "app/runtime/runproof_runtime/effectwitness/competition_agent_session.py",
    "app/runtime/runproof_runtime/effectwitness/competition_agent_verify.py",
    "app/runtime/runproof_runtime/effectwitness/competition_agent_investigation.py",
    "source/web/src/CanonicalApp.tsx",
    "source/runtime/runproof_runtime/agent.py",
    "source/runtime/runproof_runtime/deepseek_provider.py",
    "source/runtime/runproof_runtime/effectwitness/pge_r110_live_provider.py",
    "source/runtime/runproof_runtime/effectwitness/pge_r110_live_verify.py",
    "source/control-plane/pom.xml", "source/integrations/jiuwenswarm/mcp_readonly.py",
    "source/web/src/App.tsx", "source/package-lock.json",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def member_admitted(name, mode):
    parts = name.split("/")
    return (not any(p in {"", ".", ".."} or p.startswith(".") for p in parts)
            and (name in EXACT or APP.fullmatch(name) is not None or SOURCE.fullmatch(name) is not None)
            and stat.S_ISREG(mode) and not mode & 0o111)


def verify_extract(archive, target):
    raw = archive.read_bytes()
    sidecar = Path(str(archive) + ".sha256").read_text(encoding="ascii").split()
    if len(raw) >= 500_000_000 or sidecar != [digest(raw), archive.name]:
        raise ValueError("ARCHIVE_DIGEST")
    with ZipFile(archive) as z:
        files = {}
        folded = set()
        for member in z.infolist():
            name = member.filename
            if (not member_admitted(name, member.external_attr >> 16)
                    or member.file_size > 4 * 1024 * 1024 or name.casefold() in folded):
                raise ValueError("MEMBER_DENIED: " + name)
            folded.add(name.casefold())
            files[name] = z.read(member)
            if SECRET.search(files[name]):
                raise ValueError("PRIVATE_CONTENT: " + name)
    if not REQUIRED <= files.keys():
        raise ValueError("REQUIRED_MEMBERS: " + str(REQUIRED - files.keys()))
    manifest = json.loads(files["bundle-manifest.json"])
    if manifest["schema"] != "runproof-competition-complete/v1" or not re.fullmatch("[0-9a-f]{40}", manifest["source_commit"]):
        raise ValueError("MANIFEST_SCHEMA")
    if (manifest.get("mode") != ["OFFLINE_REFERENCE_AGENT", "RULE_POLICY", "PROVIDER_0"]
            or manifest.get("issuer") != "NOT_ESTABLISHED" or manifest.get("release_eligible") is not False):
        raise ValueError("MANIFEST_BOUNDARY")
    declared = sorted((v["path"], v["bytes"], v["sha256"]) for v in manifest["members"])
    actual = sorted((n, len(v), digest(v)) for n, v in files.items() if n != "bundle-manifest.json")
    if declared != actual:
        raise ValueError("MEMBER_DIGEST")
    app = json.loads(files["app/bundle-manifest.json"])
    if app["source_commit"] != manifest["source_commit"]:
        raise ValueError("APP_SOURCE")
    expected_site = sorted((n.removeprefix("app/"), len(v), digest(v))
                           for n, v in files.items() if n.startswith("app/site/"))
    if (app.get("schema") != manifest["schema"] or
            sorted((v["path"], v["bytes"], v["sha256"]) for v in app["members"]) != expected_site):
        raise ValueError("APP_SITE_MANIFEST")
    for n, data in files.items():
        if n.startswith("app/runtime/") and data != files["source/" + n.removeprefix("app/")]:
            raise ValueError("SOURCE_RUNTIME_MISMATCH")
    for parent in target.parents:
        if parent.exists() and (parent.is_symlink() or getattr(parent.lstat(), "st_file_attributes", 0) & 1024):
            raise ValueError("LINKED_OUTPUT")
    target.mkdir(exist_ok=False)
    for name, data in files.items():
        path = target.joinpath(*PurePosixPath(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as file:
            file.write(data)
        if digest(path.read_bytes()) != digest(data):
            raise ValueError("EXTRACT_DIGEST")
    return {"sha256": digest(raw), "bytes": len(raw), "members": len(files), "source": manifest["source_commit"]}


class AdmissionTests(unittest.TestCase):
    def test_rehashed_archives_retain_semantic_boundary(self):
        files = dict.fromkeys(REQUIRED - {"bundle-manifest.json"}, b"fixture")
        for name in list(files):
            if name.startswith("app/runtime/"):
                files["source/" + name[4:]] = files[name]
        source = "1" * 40
        schema = "runproof-competition-complete/v1"
        entry = lambda name, raw: {"path": name, "bytes": len(raw), "sha256": digest(raw)}
        files["app/bundle-manifest.json"] = json.dumps({
            "schema": schema, "source_commit": source,
            "members": [entry("site/index.html", files["app/site/index.html"])]}).encode()
        manifest = {"schema": schema, "source_commit": source, "issuer": "NOT_ESTABLISHED",
                    "release_eligible": False, "mode": ["OFFLINE_REFERENCE_AGENT", "RULE_POLICY", "PROVIDER_0"],
                    "members": [entry(n,v) for n,v in files.items()]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for field, changes in (("mode", [None, "OFFLINE_REFERENCE_AGENT", ["LIVE"]]),
                                   ("issuer", [None, 1, "EXTERNAL"]), ("release_eligible", [None, 0, True])):
                for value in changes:
                    with self.subTest(field=field, value=value):
                        altered = manifest.copy()
                        if value is None:
                            del altered[field]
                        else:
                            altered[field] = value
                        archive = root / "candidate.zip"
                        with ZipFile(archive, "w") as z:
                            from zipfile import ZipInfo
                            for name, raw in (files | {"bundle-manifest.json": json.dumps(altered).encode()}).items():
                                info = ZipInfo(name)
                                info.external_attr = (stat.S_IFREG | 0o644) << 16
                                z.writestr(info, raw)
                        Path(str(archive) + ".sha256").write_text(digest(archive.read_bytes()) + "  " + archive.name)
                        with self.assertRaisesRegex(ValueError, "^MANIFEST_BOUNDARY$"):
                            verify_extract(archive, root / "extract")

    def test_archive_escape_link_and_executable_refused(self):
        for name in ("../x", "app/site/../start.ps1", ".local/ledger", "app/site/assets/a.js.map",
                     "source/spikes/rpf-1/run.json", "source/runtime/.env", "app/site/assets/x.exe"):
            self.assertFalse(member_admitted(name, stat.S_IFREG | 0o644))
        self.assertFalse(member_admitted("app/start.ps1", stat.S_IFLNK | 0o777))
        self.assertFalse(member_admitted("app/start.ps1", stat.S_IFREG | 0o755))
        self.assertTrue(member_admitted("app/start.ps1", stat.S_IFREG | 0o644))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    p.add_argument("target", type=Path)
    args = p.parse_args()
    print(json.dumps(verify_extract(args.archive, args.target)))
