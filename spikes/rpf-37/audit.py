"""Standard-library-only RPF-37 repository closure inventory.

This is an inventory aid, not a cleanup command. It reads tracked files and
Git metadata, writes only an explicitly requested local JSON file, and never
deletes or changes repository content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Iterable


SCHEMA = "rpf-repository-closure-audit-v1"
TRACKED_GENERATED_RE = re.compile(r"(^|/)(target|node_modules|dist|\.local|__pycache__)/|\.(?:log|pyc|class)$", re.I)
SPIKE_RE = re.compile(r"^spikes/(rpf-\d{2})/")
REF_RE = re.compile(r"(?i)\brpf[-_]?0?(\d{1,2})(?!\d)")


def run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout


def tracked_paths(root: Path) -> list[str]:
    raw = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    return sorted(item.decode("utf-8") for item in raw.split(b"\0") if item)


def file_bytes(root: Path, relative: str) -> int:
    path = root / Path(relative)
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_for(root: Path, relative: str) -> str:
    try:
        return (root / Path(relative)).read_text(encoding="utf-8", errors="ignore")
    except (FileNotFoundError, IsADirectoryError):
        return ""


def first_directory(relative: str) -> str:
    return relative.split("/", 1)[0] if "/" in relative else "(root)"


def workflow_inventory(root: Path, paths: Iterable[str]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for relative in paths:
        if not relative.startswith(".github/workflows/") or not relative.endswith((".yml", ".yaml")):
            continue
        content = text_for(root, relative)
        name_match = re.search(r"(?m)^name:\s*(.+)$", content)
        actions = sorted(set(re.findall(r"uses:\s*([^\s#]+)", content)))
        permissions = {
            key: value
            for key, value in re.findall(r"(?m)^\s{2,}(contents|actions|id-token):\s*([^\s#]+)", content)
        }
        result.append(
            {
                "file": relative,
                "name": name_match.group(1).strip() if name_match else "",
                "push": bool(re.search(r"(?m)^\s+push:\s*", content)),
                "pull_request": bool(re.search(r"(?m)^\s+pull_request:\s*", content)),
                "workflow_dispatch": "workflow_dispatch:" in content,
                "permissions": permissions,
                "actions": actions,
            }
        )
    return result


def spike_inventory(root: Path, paths: list[str]) -> list[dict[str, object]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for relative in paths:
        match = SPIKE_RE.match(relative)
        if match:
            grouped[match.group(1)].append(relative)
    result: list[dict[str, object]] = []
    for spike, members in sorted(grouped.items()):
        result.append(
            {
                "spike": spike,
                "tracked_files": len(members),
                "tracked_bytes": sum(file_bytes(root, item) for item in members),
                "has_readme": any(item == f"spikes/{spike}/README.md" for item in members),
                "has_result": any(item == f"spikes/{spike}/RESULT.md" for item in members),
                "has_probe": any(Path(item).name.startswith("probe.") for item in members),
                "has_verifier": any(Path(item).name.startswith("verify-") for item in members),
            }
        )
    return result


def external_reference_inventory(root: Path, paths: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    contents = {relative: text_for(root, relative) for relative in paths}
    for number in range(1, 37):
        label = f"rpf-{number:02d}"
        references: list[str] = []
        for relative, content in contents.items():
            if relative.startswith(f"spikes/{label}/") or relative.startswith("spikes/rpf-37/"):
                continue
            match = REF_RE.search(content)
            if match and int(match.group(1)) == number:
                references.append(relative)
        result[label] = references
    return result


def duplicate_hashes(root: Path, paths: list[str]) -> list[dict[str, object]]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for relative in paths:
        path = root / Path(relative)
        if path.is_file():
            by_hash[sha256(path)].append(relative)
    return [
        {"sha256": digest, "files": sorted(members)}
        for digest, members in sorted(by_hash.items())
        if len(members) > 1
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory the tracked RunProof tree for RPF-37.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=None, help="Optional local JSON output path.")
    args = parser.parse_args()
    root = args.root.resolve()
    paths = tracked_paths(root)
    sizes = {relative: file_bytes(root, relative) for relative in paths}
    top_level: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})
    for relative, size in sizes.items():
        bucket = top_level[first_directory(relative)]
        bucket["files"] += 1
        bucket["bytes"] += size

    status = run_git(root, "status", "--porcelain=v1").splitlines()
    untracked = [line[3:] for line in status if line.startswith("?? ")]
    generated = [relative for relative in paths if TRACKED_GENERATED_RE.search(relative)]
    largest = [
        {"file": relative, "bytes": size}
        for relative, size in sorted(sizes.items(), key=lambda item: (-item[1], item[0]))[:25]
    ]
    audit = {
        "schema": SCHEMA,
        "head": run_git(root, "rev-parse", "HEAD").strip(),
        "tracked": {"files": len(paths), "bytes": sum(sizes.values())},
        "top_level": {key: top_level[key] for key in sorted(top_level)},
        "largest_files": largest,
        "workflows": workflow_inventory(root, paths),
        "spikes": spike_inventory(root, paths),
        "external_rpf_references": external_reference_inventory(root, paths),
        "duplicate_hash_groups": duplicate_hashes(root, paths),
        "tracked_generated_files": generated,
        "untracked_paths": untracked,
        "hygiene": {
            "tracked_generated_clean": not generated,
            "duplicate_hashes_found": bool(duplicate_hashes(root, paths)),
            "docs_reviews_preserved": any(path == "docs/reviews/" or path.startswith("docs/reviews/") for path in untracked),
        },
    }
    encoded = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
