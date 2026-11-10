"""Independently validate and extract the exact competition package."""
import argparse
import ast
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import stat
import unittest
import zipfile

PACKAGE = "runtime/runproof_runtime/effectwitness/"
SCRIPTS = {"start.ps1", "stop.ps1", "verify-witness.ps1", "competition-server.cjs", "START_HERE.zh-CN.md"}
INIT = {"runtime/__init__.py", "runtime/runproof_runtime/__init__.py", PACKAGE + "__init__.py"}
MODULES = {"effect_oracle", "ops_oracle", "product_local_contracts", "product_local_gateway",
           "product_local_ports", "product_local_session", "product_local_verify", "rpf112_competition_gateway"}
MANIFEST = "bundle-manifest.json"
REQUIRED = SCRIPTS | INIT | {PACKAGE + name + ".py" for name in MODULES} | {"site/index.html", MANIFEST}
ASSET = re.compile(r"site/assets/[A-Za-z0-9_-]+\.(?:js|css|svg|png|webp|jpg|woff2)", re.ASCII)
PRIVATE = re.compile(rb"(?i)(?:[A-Z]:[/\\](?:Users|CS)[/\\]|sk-(?:proj-)?[a-z0-9_-]{32,}|sourceMappingURL\s*=)")


def digest(raw):
    return sha256(raw).hexdigest()


def read_members(archive):
    files = {}
    for entry in archive.infolist():
        name = entry.filename
        if (name not in REQUIRED and not ASSET.fullmatch(name)) or name in files:
            raise ValueError("MEMBER_PATH")
        if (not stat.S_ISREG(entry.external_attr >> 16) or (entry.external_attr >> 16) & 0o111
                or entry.file_size > 4 * 1024 * 1024 or len(files) >= 64):
            raise ValueError("MEMBER_TYPE_OR_SIZE")
        files[name] = archive.read(entry)
    return files


def verify_and_extract(archive_path, destination):
    raw = archive_path.read_bytes()
    sidecar = Path(str(archive_path) + ".sha256").read_text(encoding="ascii").split()
    if sidecar != [digest(raw), archive_path.name] or not 0 < len(raw) < 500_000_000:
        raise ValueError("ZIP_DIGEST")
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        files = read_members(archive)
    if not REQUIRED <= files.keys() or not any(ASSET.fullmatch(name) for name in files):
        raise ValueError("MEMBERS_MISSING")
    manifest = json.loads(files[MANIFEST])
    if (not re.fullmatch("[0-9a-f]{40}", manifest["source_commit"]) or manifest["issuer"] != "NOT_ESTABLISHED"
            or manifest["release_eligible"] is not False
            or manifest["mode"] != ["CONTROLLED_LOCAL", "RULE_POLICY", "PROVIDER_0"]):
        raise ValueError("MANIFEST_BOUNDARY")
    declared = [(row["path"], row["bytes"], row["sha256"]) for row in manifest["members"]]
    actual = [(name, len(data), digest(data)) for name, data in files.items() if name != MANIFEST]
    if sorted(declared) != sorted(actual):
        raise ValueError("MEMBER_DIGEST")
    for name, data in files.items():
        if PRIVATE.search(data):
            raise ValueError("PRIVATE_DATA_MARKER: " + name)
    closure = set()
    pending = ["rpf112_competition_gateway", "product_local_verify"]
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        closure.add(name)
        tree = ast.parse(files[PACKAGE + name + ".py"])
        pending.extend(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level == 1)
    if closure != MODULES:
        raise ValueError("IMPORT_CLOSURE")
    destination.mkdir(exist_ok=False)
    for name, data in files.items():
        output = destination / name
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as handle:
            handle.write(data)
        if digest(output.read_bytes()) != digest(data):
            raise ValueError("EXTRACT_DIGEST")
    return {"bytes": len(raw), "sha256": digest(raw), "members": len(files), "python_closure": len(closure)}


class BundleTests(unittest.TestCase):
    def test_rejects_escape_and_unexpected_members(self):
        for name in ("../outside", "site/../index.html", ".local/token", "site/assets/bad.exe", "site/assets/a.js.map"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "MEMBER_PATH"):
                self.check_entry(name, stat.S_IFREG | 0o644)

    def test_rejects_symlink_and_executable(self):
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFREG | 0o755):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "MEMBER_TYPE_OR_SIZE"):
                self.check_entry("site/index.html", mode)

    def check_entry(self, name, mode):
        data = BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            entry = zipfile.ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = mode << 16
            archive.writestr(entry, "sample")
        with zipfile.ZipFile(data) as archive:
            read_members(archive)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_and_extract(args.archive, args.destination)))
