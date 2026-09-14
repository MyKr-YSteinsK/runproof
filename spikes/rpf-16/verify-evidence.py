"""Offline verifier for the reviewed RPF-16 Incident corpus."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["--verify"]))
