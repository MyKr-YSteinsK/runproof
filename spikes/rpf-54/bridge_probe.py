"""DISPOSABLE_INCOMPATIBILITY_SPIKE: published-byte projection, never execution.

This schema is local to RPF-54. It is not an adopted Runtime/PGE interface.
Importing this module performs no artifact reads, network, credential access or writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.runproof_runtime.effectwitness.witness_verify import verify_bytes as verify_order
from runtime.runproof_runtime.effectwitness.config_live_verify import verify_bytes as verify_config

KIND = "DISPOSABLE_INCOMPATIBILITY_SPIKE"
SCHEMA = "rpf54-readonly-feedback-projection-test-v1"
REFS = {
    "order": {"path": "spikes/rpf-43/sample-witness.json",
        "sha256": "ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e",
        "run_id": "rpf43-fb6cf612bf444c1fae5d2d896d4192b7"},
    "config": {"path": "spikes/rpf-53/rev-6/config-live-evidence.json",
        "sha256": "f5e46947ae2a2583db51727e85c4f9e3d6c9d6499a1b24833dfffe1799438b43",
        "run_id": "rpf53-live-917c3dda02fb4ad7"},
}


class ProjectionRejected(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise ProjectionRejected(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def is_sha(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def validate_projection(value):
    """One shared field check for both domains; no upgrade of authority/provenance."""
    require(type(value) is dict and set(value) == {
        "schema_version", "source_kind", "artifact_sha256", "source_schema", "domain",
        "run_id", "experiment_sha256", "contract_hashes", "evaluation_scope", "target_source",
        "authority", "effect", "fault", "pge_session", "attribution", "reproduction"}, "PROJECTION_FIELDS")
    require(value["schema_version"] == SCHEMA and value["source_kind"] in ("PUBLISHED_REPLAY", "SYNTHETIC_NEGATIVE"),
            "PROJECTION_SOURCE")
    require(value["domain"] in ("order", "config") and type(value["run_id"]) is str
            and value["run_id"] and is_sha(value["artifact_sha256"])
            and is_sha(value["experiment_sha256"]), "PROJECTION_IDENTITY")
    require(set(value["contract_hashes"]) == {"execution", "effect", "experiment"}
            and all(is_sha(v) for v in value["contract_hashes"].values())
            and value["experiment_sha256"] == value["contract_hashes"]["experiment"], "CONTRACT_BINDING")
    require(value["evaluation_scope"] == "MANAGED_EVALUATION", "EXTERNAL_ONLY_NOT_MANAGED")
    authority = value["authority"]
    require(type(authority) is dict and set(authority) == {"scope", "refs", "database_independence"}
            and authority["scope"] in ("OWNED_SQLITE_SEPARATE_READONLY_READER", "SAME_SERVICE_HTTP_GET")
            and len(authority["refs"]) >= 2 and all(is_sha(v) for v in authority["refs"])
            and authority["database_independence"] == "NOT_ESTABLISHED", "AUTHORITY_REQUIRED")
    effect = value["effect"]
    require(type(effect) is dict and set(effect) == {"outcome", "violated_rules", "gaps", "state_diff", "receipt_sha256"}
            and effect["outcome"] == "CONTRACT_SATISFIED_IN_RUN"
            and effect["violated_rules"] == effect["gaps"] == []
            and type(effect["state_diff"]) is dict and effect["state_diff"]
            and (effect["receipt_sha256"] is None or is_sha(effect["receipt_sha256"])), "EFFECT_FIELDS")
    fault = value["fault"]
    require(type(fault) is dict and set(fault) == {"planned", "triggered", "observed", "activation"}, "FAULT_FIELDS")
    if value["domain"] == "config":
        require(fault == {"planned": None, "triggered": None, "observed": None, "activation": "UNKNOWN"}
                and value["target_source"] == "REAL_PROVIDER_TARGET"
                and authority["scope"] == "SAME_SERVICE_HTTP_GET"
                and effect["receipt_sha256"] is None, "CONFIG_FAULT_OR_AUTHORITY_OVERCLAIM")
    else:
        require(all(fault[k] is True for k in ("planned", "triggered", "observed"))
                and fault["activation"] == "TRIGGERED"
                and value["target_source"] == "DETERMINISTIC_CONTROLLED_TARGET"
                and authority["scope"] == "OWNED_SQLITE_SEPARATE_READONLY_READER", "ORDER_SOURCE_BINDING")
    require(value["pge_session"] == {"session_id": None, "candidate_id": None,
            "selection": "NOT_DERIVABLE_FROM_PUBLISHED_WITNESS"}, "SESSION_UPGRADE_REJECTED")
    require(value["attribution"] == "CORRELATIONAL_ONLY" and value["reproduction"] == "NOT_TESTED",
            "ATTRIBUTION_OVERCLAIM")
    return value


def project_bytes(domain, raw, expected_sha256, expected_run_id, *, source_kind="PUBLISHED_REPLAY"):
    require(domain in REFS, "DOMAIN_NOT_REGISTERED")
    require(type(raw) is bytes and 0 < len(raw) <= 2_000_000
            and is_sha(expected_sha256) and hashlib.sha256(raw).hexdigest() == expected_sha256, "EXTERNAL_ANCHOR_MISMATCH")
    try:
        if domain == "order":
            verify_order(raw, expected_sha256)
            doc = json.loads(raw)
            c, o = doc["contracts"], doc["observation"]
            require(doc["capture"]["source_level"] == "MANAGED_LOCAL_SIMULATION", "EXTERNAL_ONLY_NOT_MANAGED")
            hashes = c["sha256"]
            before, after = o["authority_before"]["data"]["order"], o["authority_after"]["data"]["order"]
            effect = {"outcome": o["effect"]["contract_outcome"],
                "violated_rules": o["effect"]["violated_rules"], "gaps": o["effect"]["evidence_gaps"],
                "state_diff": {k: {"before": before[k], "after": after[k]}
                               for k in ("status", "refunded_minor", "revision")},
                "receipt_sha256": o["effect"]["receipt_hash"]}
            authority = {"scope": "OWNED_SQLITE_SEPARATE_READONLY_READER",
                "refs": [o[k]["sha256"] for k in ("authority_before", "authority_after")],
                "database_independence": "NOT_ESTABLISHED"}
            fault = {k: o["fault"][k] for k in ("planned", "triggered", "observed")}
            fault["activation"] = doc["claims"]["fault_activation"]
            target = doc["capture"]["target_driver"]
        else:
            oracle = verify_config(raw)
            envelope = json.loads(raw)
            doc = envelope["payload"]
            c = doc["contracts"]
            hashes = {k: digest(c[k]) for k in ("execution", "effect", "experiment")}
            rows = doc["http_observations"]
            final = rows[doc["authority_after"]["current_seq"] - 1]["response"]["data"]
            effect = {"outcome": oracle["outcome"], "violated_rules": oracle["violations"],
                "gaps": oracle["gaps"], "state_diff": {"value": {"before": None, "after": final["value"]},
                    "version": {"before": None, "after": final["version"]}}, "receipt_sha256": None}
            authority = {"scope": "SAME_SERVICE_HTTP_GET", "database_independence": "NOT_ESTABLISHED",
                "refs": [rows[n - 1]["response_body_sha256"] for n in (
                    doc["authority_before"]["current_seq"], *doc["authority_after"].values())]}
            # No frozen fault candidate/activation proof exists in this Live schema.
            fault = {"planned": None, "triggered": None, "observed": None, "activation": "UNKNOWN"}
            target = "REAL_PROVIDER_TARGET"
        run_id = c["experiment"]["run_id"]
        require(run_id == expected_run_id, "RUN_ID_MISMATCH")
        return validate_projection({"schema_version": SCHEMA, "source_kind": source_kind,
            "artifact_sha256": expected_sha256, "source_schema": json.loads(raw)["schema_version"],
            "domain": domain, "run_id": run_id, "experiment_sha256": hashes["experiment"],
            "contract_hashes": hashes, "evaluation_scope": "MANAGED_EVALUATION", "target_source": target,
            "authority": authority, "effect": effect, "fault": fault,
            "pge_session": {"session_id": None, "candidate_id": None,
                "selection": "NOT_DERIVABLE_FROM_PUBLISHED_WITNESS"},
            "attribution": "CORRELATIONAL_ONLY", "reproduction": "NOT_TESTED"})
    except ProjectionRejected:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        raise ProjectionRejected("SOURCE_WITNESS_REJECTED") from None


def require_claim(projection, claim):
    validate_projection(projection)
    require(projection["source_kind"] == "PUBLISHED_REPLAY", "SYNTHETIC_NOT_REAL_EVIDENCE")
    if claim == "CONTRACT_SATISFIED_IN_RETAINED_RUN":
        return True
    if claim == "FAULT_TRIGGERED":
        require(projection["fault"]["activation"] == "TRIGGERED", "NO_FAULT_ACTIVATION_PROOF")
        return True
    if claim == "PGE_ADAPTATION_OBSERVED":
        raise ProjectionRejected("NO_PREREGISTERED_SESSION_OR_SELECTION_LINEAGE")
    if claim == "VIOLATION_CONFIRMED":
        raise ProjectionRejected("SATISFIED_EFFECT_IS_NOT_VIOLATION")
    raise ProjectionRejected("CLAIM_NOT_SUPPORTED")


def published_projections():
    return {domain: project_bytes(domain, (ROOT / ref["path"]).read_bytes(), ref["sha256"], ref["run_id"])
            for domain, ref in REFS.items()}


def offline_auditor(counters):
    allowed = ROOT / ".local" / "rpf-54"
    forbidden = ROOT / "docs" / "reviews"
    def audit(event, args):
        if event.startswith("socket."):
            counters["network_attempts"] += 1
            raise PermissionError("RPF54_NETWORK_FORBIDDEN")
        if event in ("subprocess.Popen", "os.system", "os.posix_spawn"):
            counters["child_process_attempts"] += 1
            raise PermissionError("RPF54_CHILD_PROCESS_FORBIDDEN")
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            require(not path.is_relative_to(forbidden), "PROTECTED_DIRECTORY_FORBIDDEN")
            if path.is_relative_to(ROOT / ".local"):
                require(path.is_relative_to(allowed), "OLD_LOCAL_ACCESS_FORBIDDEN")
            mode = args[1]
            flags = args[2] if len(args) > 2 and type(args[2]) is int else 0
            writing = ((isinstance(mode, str) and any(k in mode for k in "wax+"))
                       or flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC | os.O_EXCL))
            if writing:
                require(path.is_relative_to(allowed), "OUTPUT_OUTSIDE_TASK")
        if event in ("os.mkdir", "os.remove", "os.rmdir", "os.rename"):
            paths = args[:2] if event == "os.rename" else args[:1]
            require(all(Path(os.fsdecode(p)).resolve().is_relative_to(allowed) for p in paths),
                    "MUTATION_OUTSIDE_TASK")
    return audit


def install_offline_guard():
    counters = {"network_attempts": 0, "child_process_attempts": 0}
    audit = offline_auditor(counters)
    sys.addaudithook(audit)
    return counters


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    counters = install_offline_guard()
    projections = published_projections()
    result = {"kind": KIND, "source": "PUBLISHED_REPLAY", "status": "PASS",
        "projections": projections, "guard": counters,
        "execution_bridge": "INCOMPATIBLE_WITH_CURRENT_SESSION_AND_RUNNER_CONTRACTS",
        "new_pge_adaptation": "NOT_PROVEN", "next_selection_eligibility": "BLOCKED_MISSING_PREREGISTERED_SESSION",
        "provider_requests": 0, "tokens": 0, "cost_cny": 0,
        "java_processes": 0, "business_http_posts": 0, "fault_trials": 0}
    if args.output:
        target = args.output.resolve()
        require(target.is_relative_to((ROOT / ".local/rpf-54").resolve()), "OUTPUT_OUTSIDE_TASK")
        require(not target.exists(), "OUTPUT_ALREADY_EXISTS")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(canonical(result))
    print(canonical(result).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
