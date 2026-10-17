"""Zero-provider, task-owned two-domain capture through shared ports and Witness core."""
import argparse
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .contracts import ROOT, canonical, digest, owned_path, quarantine_path, require
from .cross_contracts import CrossContracts
from .cross_core import LIMITS, SCHEMA, SPECS, project_feedback
from .engine import Budget, Orchestrator
from .ops import OpsAdapter, OpsAuthorityReader, OpsSandbox
from .orders import AuthorityReader, OrderAdapter, OrderSandbox
from .witness import _package_source_digest
from .witness_verify import (ISSUER_ID, LIMITATIONS, _derive_fault_activation, verify_bytes)


def run_trial(contracts, *, before_cleanup_hook=None, storage_task="rpf-44", event_hook=None, quarantine_id=None, deadline=None):
    """Both domains traverse this exact orchestration/event/feedback pipeline.

    Seven budgeted actions: initialize, initial authority, dispatch, reconcile,
    final authority/effect, feedback, cleanup. Cleanup still runs on failure.
    """
    contracts.validate()
    require(storage_task in ("rpf-44", "rpf-45", "rpf-46"), "STORAGE_TASK_REJECTED")
    require(quarantine_id is None or (storage_task in ("rpf-45", "rpf-46") and isinstance(quarantine_id, str)
            and re.fullmatch(r"session-[a-f0-9]{32}", quarantine_id)), "QUARANTINE_ID_REJECTED")
    x, f = contracts.experiment, contracts.effect
    domain = x["domain"]
    spec = SPECS[domain]
    class TrialBudget(Budget):
        def check_time(self):
            super().check_time()
            require(deadline is None or time.monotonic() < deadline, "SESSION_TIME_EXHAUSTED")
    budget = TrialBudget(contracts.execution["budgets"])
    sandbox_type, reader_type, adapter_type = (OpsSandbox, OpsAuthorityReader, OpsAdapter) if domain == "ops" else (
        OrderSandbox, AuthorityReader, OrderAdapter)
    sandbox = sandbox_type(contracts, storage_task=storage_task)
    events = []
    failed = False

    def emit(name, facts):
        events.append({"seq": len(events) + 1, "event_id": f"event-{x['run_id']}-{len(events)+1:02d}",
                       "observed_at": datetime.now(timezone.utc).isoformat(), "type": name,
                       "facts": json.loads(canonical(facts)), "facts_sha256": digest(facts)})
        if event_hook:
            event_hook(json.loads(canonical(events[-1])))

    emit("contracts_preregistered", {"owner": x["owner"], "capture_id": x["capture_id"],
                                      "contract_hashes": contracts.hashes})
    try:
        budget.step()
        sandbox.initialize()
        emit("environment_initialized", {k: x[k] for k in ("owner", "run_id", "environment_id")})
        reader, adapter = reader_type(sandbox.path, contracts, storage_task=storage_task), adapter_type(sandbox)
        budget.step()
        orchestrator = Orchestrator(contracts, adapter, reader, budget)
        emit("authority_before_verified", {"snapshot_sha256": orchestrator.before.sha256})
        args = {k: f[k] for k in spec["arguments"]}
        orchestrator.dispatch(spec["tool"], args)
        emit("tool_result_observed", orchestrator.calls[0])
        emit("fault_activation_observed", {k: adapter.fault[k] for k in ("planned", "triggered", "observed")})
        budget.step()
        reconciliation = orchestrator.reconcile() if orchestrator.pending else None
        adapter.fault["reconciled"] = orchestrator.reconciled
        emit("receipt_reconciled", reconciliation)

        def verifier(before, after):
            result = spec["oracle"](f, x["environment_id"], reader.validate(before), reader.validate(after))
            return {**result, "before_sha256": before.sha256, "after_sha256": after.sha256}

        budget.step()
        after_snapshots = []
        effect = orchestrator.effect_result(verifier, after_snapshot_hook=after_snapshots.append)
        require(after_snapshots and "receipt_hash" in effect, "AUTHORITY_CAPTURE_INCONCLUSIVE", "ENVIRONMENT")
        before, after = orchestrator.before.public(), after_snapshots[0].public()
        emit("authority_after_verified", {"snapshot_sha256": after["sha256"]})
        emit("effect_verified", {k: effect[k] for k in ("contract_outcome", "before_sha256",
                                                       "after_sha256", "verifier_id", "verifier_version")})
        fault = {**adapter.fault, "activation": "UNKNOWN"}
        # Derivation validates its own assertion; choose the assertion from observed flags.
        fault["activation"] = ("TRIGGERED" if all(adapter.fault.values()) else
            "NOT_TRIGGERED" if fault["planned"] and not any(fault[k] for k in
                ("triggered", "observed", "reconciled")) else "NOT_PLANNED" if not any(adapter.fault.values()) else "UNKNOWN")
        _derive_fault_activation(fault)
        budget.step()
        observation = {"run_outcome": "PASS", "effect": effect, "fault": fault,
                       "tool_calls": orchestrator.calls, "reconciliation": reconciliation,
                       "authority_before": before, "authority_after": after,
                       "feedback": project_feedback(domain, effect, fault)}
        # Freeze before reset; the hook can independently read the still-live DB.
        frozen_observation = canonical(observation)
        if before_cleanup_hook:
            before_cleanup_hook(sandbox, json.loads(frozen_observation))
        budget.step()
    except Exception:
        failed = True
        raise
    finally:
        if sandbox.created:
            def quarantine():
                destination = quarantine_path(sandbox.directory, task=storage_task)
                if quarantine_id:
                    destination = destination.with_name(quarantine_id)
                    require(not destination.exists(), "QUARANTINE_ALREADY_EXISTS")
                destination.parent.mkdir(parents=True, exist_ok=True)
                sandbox.directory.rename(destination)

            if failed:
                # Preserve uncertain effects/receipts; never reset away failure evidence.
                quarantine()
            else:
                try:
                    cleanup = sandbox.cleanup()
                except Exception:
                    if sandbox.directory.exists():
                        quarantine()
                    raise
    observation = {**json.loads(frozen_observation), "cleanup": cleanup}
    emit("cleanup_completed", cleanup)
    claims = {"contract_outcome": effect["contract_outcome"], "fault_activation": fault["activation"],
              "attribution_strength": "CORRELATIONAL_ONLY", "reproduction": "NOT_TESTED", "run_outcome": "PASS"}
    bundle = {"schema_version": SCHEMA, "domain": domain, "oracle_version": "1",
              "issuer": {"issuer_id": ISSUER_ID, "issuer_version": "2", "attestation": "UNSIGNED_LOCAL_TOOL",
                         "source_digest": _package_source_digest()},
              "capture": {"capture_id": x["capture_id"], "captured_at": events[-1]["observed_at"],
                          "source_level": spec["source"], "target_driver": "DETERMINISTIC_CONTROLLED_TARGET",
                          "session_reference": {"kind": "DETERMINISTIC_CAPTURE", "session_id": None,
                                                "session_digest": None, "policy": "NOT_APPLICABLE"},
                          "environment": {"owner": x["owner"], "run_id": x["run_id"],
                                          "environment_id": x["environment_id"], "revision": x["environment_revision"]}},
              "contracts": contracts.document(), "observation": observation, "events": events, "claims": claims,
              "limitations": LIMITATIONS + ["RPF28_DOCKER_INTEGRATION_NOT_PROVEN"]}
    bundle["digests"] = {k: digest(bundle[k]) for k in ("contracts", "observation", "events", "claims")}
    if x["fault"] == "response-lost":
        verify_bytes(canonical(bundle))
    return bundle, budget.public()


def _reserve_trial(domain):
    """Durable reservation, before stateful I/O; failed attempts also consume quota."""
    path = owned_path(ROOT / ".local/rpf-44/trial-budget.json", task="rpf-44")
    now = datetime.now(timezone.utc)
    ledger = json.loads(path.read_bytes()) if path.exists() else {"started_at": now.isoformat(), "trials": []}
    require(len(ledger["trials"]) < 3 and (now - datetime.fromisoformat(ledger["started_at"])).total_seconds() < 2700,
            "RPF44_SESSION_BUDGET_EXHAUSTED")
    run_id = "rpf44-" + uuid.uuid4().hex
    ledger["trials"].append({"domain": domain, "run_id": run_id, "reserved_at": now.isoformat()})
    with path.open("wb") as stream:
        stream.write(canonical(ledger))
        stream.flush()
        os.fsync(stream.fileno())
    return run_id


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=tuple(SPECS), required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.output:
        require(args.domain == "ops" and args.output.resolve() ==
                (ROOT / "spikes/rpf-44/sample-ops-witness.json").resolve() and not args.output.exists(),
                "WITNESS_OUTPUT_NOT_ALLOWLISTED")
    run_id = _reserve_trial(args.domain)
    bundle, usage = run_trial(CrossContracts.create(args.domain, run_id))
    raw = canonical(bundle)
    result = verify_bytes(raw, hashlib.sha256(raw).hexdigest())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    print(json.dumps({"run_id": run_id, "domain": args.domain, "verification": result,
                      "source_digest": bundle["issuer"]["source_digest"], "usage": usage,
                      "cleanup": bundle["observation"]["cleanup"],
                      "feedback": bundle["observation"]["feedback"], "bytes": len(raw)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
