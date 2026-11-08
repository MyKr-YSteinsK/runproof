"""Read only the three pinned historical sources through existing verifiers."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from runtime.runproof_runtime.effectwitness.witness_verify import verify_file

ROOT = Path(__file__).resolve().parents[2]
SOURCE_COMMIT = "69dfe3079f5778cf6e569e82cf8382e4e3ec04a8"
SOURCES = {
    "rpf46-summary": ("order", "RECORDED_REDACTED_SUMMARY", "spikes/rpf-46/session-report.json", "f450803b8fd3ec51fe2663ba95370577c92f0eb70cc0dd05f4d7e5b98ab25d15"),
    "rpf43-order-sample": ("order", "HISTORICAL_WITNESS_SAMPLE", "spikes/rpf-43/sample-witness.json", "ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e"),
    "rpf44-ops-sample": ("ops", "HISTORICAL_WITNESS_SAMPLE", "spikes/rpf-44/sample-ops-witness.json", "21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873"),
}

class SourceError(ValueError):
    pass

def _verifier():
    path = ROOT / "spikes/rpf-47/verify_evidence.py"
    spec = importlib.util.spec_from_file_location("rpf47_readonly_verifier", path)
    if spec is None or spec.loader is None:
        raise SourceError("SOURCE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _id(source_id: str, allowed: set[str]):
    if type(source_id) is not str or source_id not in allowed:
        raise SourceError("INVALID_SOURCE")

def verified_sources():
    try:
        for relative in ["spikes/rpf-47/EVIDENCE_MANIFEST.json", *(entry[2] for entry in SOURCES.values())]:
            path = ROOT
            for part in Path(relative).parts:
                path = path / part
                info = path.lstat()
                if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise SourceError("SOURCE_UNAVAILABLE")
        env = {"SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"), "PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}
        # Preserve only explicitly supplied isolation paths; do not copy credentials.
        for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "UV_CACHE_DIR", "PIP_CACHE_DIR", "TEMP", "TMP"):
            if key in os.environ:
                env[key] = os.environ[key]
        process = subprocess.run([sys.executable, "-B", str(ROOT / "spikes/rpf-47/verify_evidence.py"), "--root", str(ROOT)], cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=20, check=False)
        if process.returncode != 0:
            raise SourceError("SOURCE_TAMPERED")
        value = json.loads(process.stdout)
        if value.get("status") != "VERIFIED":
            raise SourceError("SOURCE_TAMPERED")
        return value
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise SourceError("SOURCE_UNAVAILABLE") from exc
    except FileNotFoundError as exc:
        raise SourceError("SOURCE_UNAVAILABLE") from exc
    except SourceError:
        raise
    except (ValueError, OSError) as exc:
        raise SourceError("SOURCE_TAMPERED") from exc

def capabilities():
    verified_sources()
    return {"schema_version": "rpf95-readonly-v1", "sources": [{"source_id": k, "domain": v[0], "source_kind": v[1], "status": "AVAILABLE"} for k,v in SOURCES.items()], "tools": ["get_capabilities", "inspect_recorded_experiment", "verify_witness"], "write_capability": "DISABLED_BY_TASK", "provider_capability": "DISABLED_BY_TASK"}

def inspect(source_id: str):
    _id(source_id, {"rpf46-summary"})
    result = verified_sources()
    report = result["sources"][source_id]["claims"]
    verifier = _verifier()
    raw = verifier.canonical_text_bytes((ROOT / SOURCES[source_id][2]).read_bytes())
    if hashlib.sha256(raw).hexdigest() != SOURCES[source_id][3]:
        raise SourceError("SOURCE_TAMPERED")
    original = verifier.parse_json(raw, source_id)
    verifier.validate_summary(original)
    trials = [{"round": t["round"], "candidate_id": t["candidate_id"], "outcome": t["effect"]["contract_outcome"], "state_diff": t["effect"]["state_diff"], "fault": {**t["fault"], "agent_exposed": "NOT_RECORDED"}} for t in original["trials"]]
    selections = [{k: s.get(k) for k in ("round", "candidate_id", "tool_call_id", "response_id", "input_feedback_hash")} for s in original["selections"]]
    return {"schema_version": "rpf95-readonly-v1", "source_id": source_id, "source_kind": SOURCES[source_id][1], "source_commit": SOURCE_COMMIT, "bound_sha256": SOURCES[source_id][3], "verification_status": "HASH_AND_COMMIT_VERIFIED", "issuer_authenticity": "NOT_ESTABLISHED", "evidence_gaps": ["NO_PROVIDER_CONVERSATION", "NO_FULL_LIVE_WITNESS", "NO_CAUSAL_PROOF"], "summary": report, "trials": trials, "selections": selections}

def witness(source_id: str):
    _id(source_id, {"rpf43-order-sample", "rpf44-ops-sample"})
    verified_sources()
    try:
        verdict = verify_file(ROOT / SOURCES[source_id][2], SOURCES[source_id][3])
    except ValueError as exc:
        raise SourceError("WITNESS_REJECTED") from exc
    return {"schema_version": "rpf95-readonly-v1", "source_id": source_id, "source_kind": SOURCES[source_id][1], "source_commit": SOURCE_COMMIT, "bound_sha256": SOURCES[source_id][3], "verification_status": verdict["status"], "issuer_authenticity": verdict["issuer_authenticity"], "evidence_gaps": ["NO_ISSUER_SIGNATURE", "NO_SHARED_RPF46_SESSION"], "verdict": verdict}
