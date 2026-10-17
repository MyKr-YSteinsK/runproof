"""RPF-43 one-run Witness issuer. Verification lives in the stdlib-only sibling module."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from .witness_verify import (LIMITATIONS, SCHEMA_VERSION, VerificationRejected, canonical, digest,
                             verify_bytes)

ROOT = Path(__file__).resolve().parents[3]
ISSUER_ID = "runproof-effectwitness-witness-issuer"
ISSUER_VERSION = "1"
MAX_BUNDLE_BYTES = 128 * 1024


class IssueFailed(RuntimeError):
    pass


def _event_document(event: dict, seq: int, run_id: str) -> dict:
    facts = event["facts"]
    return {"seq": seq, "event_id": f"event-{run_id}-{seq:02d}",
            "observed_at": event["observed_at"], "type": event["name"],
            "facts": facts, "facts_sha256": digest(facts)}


def _live_effect(effect: dict) -> dict:
    return {"contract_outcome": effect.get("contract_outcome"),
            "verifier_id": effect.get("verifier_id"),
            "verifier_version": effect.get("verifier_version"),
            "violated_rules": effect.get("violated_rules"),
            "evidence_gaps": effect.get("evidence_gaps"),
            "receipt_hash": effect.get("receipt_hash"),
            "before_sha256": effect.get("before", {}).get("sha256"),
            "after_sha256": effect.get("after", {}).get("sha256")}


def _precleanup_capture(trial: dict, events: list[dict]) -> bytes:
    """Freeze authenticated authority facts in memory before the sandbox is reset."""
    effect = trial.get("effect", {})
    if (trial.get("run_outcome") != "PASS"
            or effect.get("contract_outcome") != "CONTRACT_SATISFIED_IN_RUN"
            or not effect.get("before") or not effect.get("after")
            or trial.get("fault", {}).get("activation") != "TRIGGERED"
            or trial.get("reconciliation", {}).get("status") != "RECONCILED_COMMITTED"):
        raise IssueFailed("PRE_CLEANUP_EVIDENCE_INCOMPLETE")
    capture = {"precleanup_schema": "rpf-effect-witness-capture-v1",
               "contracts": {**trial["contracts"], "sha256": trial["contract_hashes"]},
               "target_driver": trial["target_driver"], "run_outcome": trial["run_outcome"],
               "effect": _live_effect(effect), "fault": trial["fault"],
               "tool_calls": trial["tool_calls"], "reconciliation": trial["reconciliation"],
               "authority_before": effect["before"], "authority_after": effect["after"],
               "events": [_event_document(event, index, trial["contracts"]["experiment"]["run_id"])
                          for index, event in enumerate(events, start=1)]}
    return canonical(capture)


def _final_bundle(capture: dict, cleanup: dict, events: list[dict], source_digest: str) -> dict:
    contracts = capture["contracts"]
    execution, effect_contract, experiment = (contracts["execution"], contracts["effect"],
                                               contracts["experiment"])
    run_id = experiment["run_id"]
    all_events = [_event_document(event, index, run_id) for index, event in enumerate(events, start=1)]
    observation = {"run_outcome": capture["run_outcome"], "effect": capture["effect"],
                   "fault": capture["fault"], "tool_calls": capture["tool_calls"],
                   "reconciliation": capture["reconciliation"],
                   "authority_before": capture["authority_before"],
                   "authority_after": capture["authority_after"], "cleanup": cleanup}
    outcome = capture["effect"]["contract_outcome"]
    activation = capture["fault"]["activation"]
    bundle = {"schema_version": SCHEMA_VERSION,
              "issuer": {"issuer_id": ISSUER_ID, "issuer_version": ISSUER_VERSION,
                         "attestation": "UNSIGNED_LOCAL_TOOL", "source_digest": source_digest},
              "capture": {"capture_id": experiment["capture_id"],
                          "captured_at": all_events[-1]["observed_at"],
                          "source_level": "MANAGED_LOCAL_SIMULATION",
                          "target_driver": capture["target_driver"],
                          "session_reference": {"kind": "DETERMINISTIC_CAPTURE", "session_id": None,
                                                "session_digest": None, "policy": "NOT_APPLICABLE"},
                          "environment": {"owner": experiment["owner"], "run_id": run_id,
                                          "environment_id": experiment["environment_id"],
                                          "revision": experiment["environment_revision"]}},
              "contracts": contracts,
              "observation": observation,
              "events": all_events,
              "claims": {"contract_outcome": outcome, "fault_activation": activation,
                         "attribution_strength": "CORRELATIONAL_ONLY", "reproduction": "NOT_TESTED",
                         "run_outcome": capture["run_outcome"]},
              "digests": {}, "limitations": list(LIMITATIONS)}
    bundle["digests"] = {"contracts": digest(bundle["contracts"]),
                         "observation": digest(bundle["observation"]),
                         "events": digest(bundle["events"]), "claims": digest(bundle["claims"])}
    # Keep names explicit in source so static inspection sees the frozen business contract.
    if execution["driver"] != "deterministic" or effect_contract["required_status"] != "REFUNDED":
        raise IssueFailed("CONTRACT_CAPTURE_MISMATCH")
    return bundle


def _validate_output_path(output: Path) -> Path:
    resolved = output.resolve()
    expected_parent = (ROOT / "spikes" / "rpf-43").resolve()
    if resolved.parent != expected_parent or resolved.name != "sample-witness.json":
        raise IssueFailed("OUTPUT_PATH_NOT_ALLOWLISTED")
    if not expected_parent.is_dir():
        raise IssueFailed("OUTPUT_DIRECTORY_MISSING")
    return resolved


def _package_source_digest() -> str:
    """Hash the package source map with universal newlines for cross-platform stability."""
    folder = Path(__file__).parent
    source_hashes = {path.name: hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                     for path in sorted(folder.glob("*.py"))}
    return digest(source_hashes)


def issue(output: Path) -> dict:
    """Run one deterministic, owner-rpf-43 response-lost trial and issue its bounded witness."""
    output = _validate_output_path(output)
    if output.exists():
        raise IssueFailed("OUTPUT_ALREADY_EXISTS")
    started = time.monotonic()

    from .contracts import FrozenContracts, make_contracts
    from .exploration import SessionBudget, run_trial
    from .pge_contracts import LIMITS

    run_id = "rpf43-" + uuid.uuid4().hex
    capture_id = "capture-" + uuid.uuid4().hex
    base = make_contracts(run_id, fault="response-lost")
    experiment = {**base.experiment, "schema_version": "rpf-experiment-v3", "owner": "rpf-43",
                  "capture_id": capture_id, "capture_mode": "DETERMINISTIC_CAPTURE"}
    contracts = FrozenContracts.freeze(base.execution, base.effect, experiment)
    contracts.validate()

    events = []

    def record_event(event):
        events.append(event)

    captured_before_cleanup = []

    def capture_before_cleanup(trial):
        captured_before_cleanup.append(_precleanup_capture(trial, events))

    issue_limits = dict(LIMITS)
    issue_limits["seconds"] = min(issue_limits["seconds"], 15 * 60)
    shared = SessionBudget(issue_limits, lambda: None)
    shared.reserve_trial("PGE")
    trial = run_trial(contracts, shared, event_hook=record_event,
                      before_cleanup_hook=capture_before_cleanup)
    if len(captured_before_cleanup) != 1:
        raise IssueFailed("PRE_CLEANUP_CAPTURE_MISSING")
    if trial.get("capture_hook_error"):
        raise IssueFailed("CAPTURE_HOOK_FAILED")
    if trial.get("cleanup", {}).get("status") != "RESET_AND_REMOVED":
        raise IssueFailed("OWNER_CLEANUP_NOT_VERIFIED")
    elapsed = time.monotonic() - started
    if elapsed > 15 * 60:
        raise IssueFailed("ISSUANCE_TIME_LIMIT")
    if len(events) != 9 or events[-1].get("name") != "cleanup_completed":
        raise IssueFailed("OBSERVED_EVENT_SEQUENCE_INCOMPLETE")

    frozen_capture = json.loads(captured_before_cleanup[0].decode("utf-8"))
    source_digest = _package_source_digest()
    bundle = _final_bundle(frozen_capture, trial["cleanup"], events, source_digest)
    raw = canonical(bundle)
    if len(raw) > MAX_BUNDLE_BYTES:
        raise IssueFailed("WITNESS_SIZE_LIMIT")
    # Schema and oracle checks run locally before the only persistent output is opened.
    verify_bytes(raw)
    try:
        with output.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise IssueFailed("OUTPUT_ALREADY_EXISTS") from error
    return {"status": "ISSUED", "schema_version": SCHEMA_VERSION,
            "run_id": run_id, "capture_id": capture_id, "owner": "rpf-43",
            "run_outcome": trial["run_outcome"],
            "contract_outcome": trial["effect"]["contract_outcome"],
            "fault_activation": trial["fault"]["activation"],
            "reconciled": trial["fault"]["reconciled"],
            "cleanup": trial["cleanup"]["status"], "source_digest": source_digest,
            "provider_requests": shared.requests, "provider_tokens": shared.tokens,
            "provider_cost_cny": shared.cost_cny,
            "non_test_trials": shared.fault_trials,
            "elapsed_seconds": round(elapsed, 3),
            "file_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="must be spikes/rpf-43/sample-witness.json")
    args = parser.parse_args(argv)
    try:
        result = issue(args.output)
    except (IssueFailed, VerificationRejected) as error:
        result = {"status": "REJECTED", "reason": getattr(error, "code", str(error))}
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
