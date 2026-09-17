#!/usr/bin/env python3
"""Verify the small, repo-native public documentation contract.

This intentionally avoids a Markdown framework. It checks the invariants that
matter for RunProof's public boundary: paired docs, required semantics, local
links, command spelling, and accidental private path/credential material.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PAIRS = (
    ("README.md", "README.zh-CN.md"),
    ("docs/ARCHITECTURE.md", "docs/ARCHITECTURE.zh-CN.md"),
    ("docs/RELIABILITY_MODEL.md", "docs/RELIABILITY_MODEL.zh-CN.md"),
    ("docs/DEMO.md", "docs/DEMO.zh-CN.md"),
    ("docs/GLOSSARY.md", "docs/GLOSSARY.zh-CN.md"),
    ("docs/history/VERIFICATION_HISTORY.md", "docs/history/VERIFICATION_HISTORY.zh-CN.md"),
    ("docs/history/CAPABILITY_HISTORY.md", "docs/history/CAPABILITY_HISTORY.zh-CN.md"),
)

REQUIRED_FILES = (
    "README.md",
    "README.zh-CN.md",
    "docs/ARCHITECTURE.md",
    "docs/ARCHITECTURE.zh-CN.md",
    "docs/RELIABILITY_MODEL.md",
    "docs/RELIABILITY_MODEL.zh-CN.md",
    "docs/DEMO.md",
    "docs/DEMO.zh-CN.md",
    "docs/GLOSSARY.md",
    "docs/GLOSSARY.zh-CN.md",
    "docs/history/VERIFICATION_HISTORY.md",
    "docs/history/VERIFICATION_HISTORY.zh-CN.md",
    "docs/history/CAPABILITY_HISTORY.md",
    "docs/history/CAPABILITY_HISTORY.zh-CN.md",
    "docs/project/PROJECT_BRIEF.md",
    "docs/project/DECISIONS.md",
    "docs/project/CURRENT_STATE.md",
    "AGENTS.md",
)

REQUIRED_PHRASES = {
    "README.md": (
        "Agent Reliability",
        "Stateful Evaluation",
        "Production Change",
        "Incident Remediation",
        "Golden Demo",
        "ELIGIBLE",
        "Evidence-backed boundary",
    ),
    "README.zh-CN.md": (
        "有状态评测",
        "Production Change",
        "Incident Remediation",
        "Golden Demo",
        "ELIGIBLE",
        "有证据支持的边界",
    ),
    "docs/ARCHITECTURE.md": (
        "PostgreSQL",
        "Immutable Artifact Store",
        "Controlled Simulation Environment",
        "Provider boundary",
        "GitHub Actions Release Gate",
        "Production boundary",
    ),
    "docs/ARCHITECTURE.zh-CN.md": (
        "PostgreSQL",
        "Immutable Artifact Store",
        "Controlled Simulation Environment",
        "Provider boundary",
        "GitHub Actions Release Gate",
        "Production 边界",
    ),
    "docs/RELIABILITY_MODEL.md": (
        "PASS",
        "FAIL",
        "ERROR",
        "UNKNOWN_OUTCOME",
        "RECONCILE_REQUIRED",
        "Wilson",
        "OBSERVED_FLAKY",
        "ELIGIBLE",
    ),
    "docs/RELIABILITY_MODEL.zh-CN.md": (
        "PASS",
        "FAIL",
        "ERROR",
        "UNKNOWN_OUTCOME",
        "RECONCILE_REQUIRED",
        "Wilson",
        "OBSERVED_FLAKY",
        "ELIGIBLE",
    ),
    "docs/DEMO.md": (
        "start-demo.ps1",
        "stop-demo.ps1",
        "-RemoveData",
        "verify-lifecycle.ps1",
        "verify-golden-demo.py",
        "Incident remediation",
        "Response loss",
        "Statistical Reliability",
    ),
    "docs/DEMO.zh-CN.md": (
        "start-demo.ps1",
        "stop-demo.ps1",
        "-RemoveData",
        "verify-lifecycle.ps1",
        "verify-golden-demo.py",
        "Incident remediation",
        "response loss",
        "Statistical Reliability",
    ),
    "docs/GLOSSARY.md": (
        "Agent",
        "Run",
        "Evidence",
        "Regression",
        "Failure Intelligence",
        "Version Bisect",
        "Control Plane",
    ),
    "docs/GLOSSARY.zh-CN.md": (
        "Agent",
        "Run",
        "Evidence",
        "Regression",
        "Failure Intelligence",
        "Version Bisect",
        "Control Plane",
    ),
    "docs/history/VERIFICATION_HISTORY.md": (
        "source identities",
        "hosted runs",
        "RPF-25",
        "UNKNOWN_OUTCOME",
    ),
    "docs/history/VERIFICATION_HISTORY.zh-CN.md": (
        "source identity",
        "hosted run",
        "RPF-25",
        "UNKNOWN_OUTCOME",
    ),
    "docs/history/CAPABILITY_HISTORY.md": (
        "Stateful Run slice",
        "Cross-Agent investigation",
        "Presentation and public docs",
        "Stabilization",
    ),
    "docs/history/CAPABILITY_HISTORY.zh-CN.md": (
        "有状态 Run slice",
        "Cross-Agent 调查",
        "Presentation 与公共文档",
        "Stabilization",
    ),
}

LOCAL_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
WINDOWS_ABSOLUTE_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]|\\\\[A-Za-z0-9]")
UNSAFE_LITERAL_RE = re.compile(r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def check_local_links(root: Path, relative_path: str, text: str, errors: list[str]) -> None:
    source = root / relative_path
    for match in LOCAL_LINK_RE.finditer(text):
        target = match.group(1).strip()
        target = target.split(' "', 1)[0].split(" '", 1)[0].strip("<>")
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target_path, _, _anchor = target.partition("#")
        if not target_path:
            continue
        candidate = (source.parent / target_path).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            fail(errors, f"{relative_path}: local link escapes repository: {target}")
            continue
        if not candidate.exists():
            fail(errors, f"{relative_path}: local link target does not exist: {target}")


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    errors: list[str] = []

    for relative_path in REQUIRED_FILES:
        if not (root / relative_path).is_file():
            fail(errors, f"missing required file: {relative_path}")

    for english, chinese in PAIRS:
        english_path = root / english
        chinese_path = root / chinese
        if english_path.is_file() and chinese_path.is_file():
            english_text = english_path.read_text(encoding="utf-8")
            chinese_text = chinese_path.read_text(encoding="utf-8")
            if "[English]" not in english_text or "[简体中文]" not in english_text:
                fail(errors, f"{english}: missing bilingual navigation")
            if "[English]" not in chinese_text or "[简体中文]" not in chinese_text:
                fail(errors, f"{chinese}: missing bilingual navigation")
            check_local_links(root, english, english_text, errors)
            check_local_links(root, chinese, chinese_text, errors)

    for relative_path, phrases in REQUIRED_PHRASES.items():
        path = root / relative_path
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in phrases:
            if phrase not in text:
                fail(errors, f"{relative_path}: missing required semantic marker: {phrase}")
        if WINDOWS_ABSOLUTE_RE.search(text):
            fail(errors, f"{relative_path}: contains an absolute Windows path")
        if UNSAFE_LITERAL_RE.search(text):
            fail(errors, f"{relative_path}: contains a credential-shaped literal")

    for relative_path in ("README.md", "README.zh-CN.md"):
        path = root / relative_path
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if re.search(r"\bRPF-\d{2}\b", text):
                fail(errors, f"{relative_path}: public README contains plan-history identifiers")

    for forbidden in (
        "docs/project/PROJECT_BRIEF.en.md",
        "docs/project/PROJECT_BRIEF.zh-CN.md",
        "docs/project/DECISIONS.en.md",
        "docs/project/DECISIONS.zh-CN.md",
        "docs/project/CURRENT_STATE.en.md",
        "docs/project/CURRENT_STATE.zh-CN.md",
    ):
        if (root / forbidden).exists():
            fail(errors, f"governance must remain single-source; unexpected file exists: {forbidden}")

    demo_text = (root / "docs/DEMO.md").read_text(encoding="utf-8") if (root / "docs/DEMO.md").is_file() else ""
    root_text = (root / "README.md").read_text(encoding="utf-8") if (root / "README.md").is_file() else ""
    for required_command in (
        "powershell -ExecutionPolicy Bypass -File demo/start-demo.ps1",
        "powershell -ExecutionPolicy Bypass -File demo/stop-demo.ps1",
        "python demo/verify-golden-demo.py --root . --json",
        "powershell -ExecutionPolicy Bypass -File demo/verify-lifecycle.ps1 -Mode contracts",
        "npm test",
        "npm run typecheck",
        "npm run build",
    ):
        if required_command not in demo_text + root_text:
            fail(errors, f"public docs missing command contract: {required_command}")

    if errors:
        print("PUBLIC_DOCS_FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"PUBLIC_DOCS_PASS files={len(REQUIRED_FILES)} pairs={len(PAIRS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
