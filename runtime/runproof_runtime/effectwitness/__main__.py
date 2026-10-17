"""Root CLI: defaults to a free local demo; --live is a single-session opt-in."""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from pathlib import Path

from ..models import RuntimeFailure
from .contracts import (LOCAL_ROOT, FrozenContracts, canonical, make_contracts, owned_path,
                        quarantine_path, source_identity)
from .engine import Budget, Orchestrator
from .orders import AuthorityReader, OrderAdapter, OrderSandbox
from .verifier import OrderEffectVerifier


def write_result(path: Path, result: dict) -> None:
    # Same task-owned file, flushed before each paid attempt; no extra evidence files.
    path = owned_path(path)
    with path.open("wb") as stream:
        stream.write(canonical(result) + b"\n")
        stream.flush()
        import os
        os.fsync(stream.fileno())


def run(contracts: FrozenContracts, checkpoint=None) -> dict:
    contracts.validate()
    sandbox = OrderSandbox(contracts)
    reader = AuthorityReader(sandbox.path, contracts)
    adapter = OrderAdapter(sandbox)
    budget = Budget(contracts.execution["budgets"])
    result = {"schema_version": "rpf41-run-result-v1", "source_digest": source_identity(),
              "contracts": {"execution": contracts.execution, "effect": contracts.effect,
                            "experiment": contracts.experiment}, "contract_hashes": contracts.hashes,
              "run_outcome": "INCONCLUSIVE", "failure": None, "provider": {"requests": []},
              "fault_trials_outside_tests": 0}
    orchestrator = None

    def save(records=None):
        if records is not None:
            result["provider"]["requests"] = records
        result["budget"] = budget.public()
        result["fault_trials_outside_tests"] = budget.fault_trials
        if checkpoint:
            checkpoint(result)

    try:
        sandbox.initialize()
        orchestrator = Orchestrator(contracts, adapter, reader, budget)
        save()
        if contracts.execution["driver"] == "deepseek-http":
            from .provider import drive
            result["provider"] = drive(orchestrator, save)
        else:
            e = contracts.effect
            orchestrator.dispatch("refund_order", {k: e[k] for k in
                                                   ("order_id", "operation_id", "amount_minor")})
            if orchestrator.pending:
                if contracts.experiment["fault"] == "reconcile-unavailable":
                    reader.available = False
                orchestrator.reconcile()
        result["run_outcome"] = "PASS"
    except RuntimeFailure as failure:
        result["run_outcome"] = failure.outcome
        result["failure"] = {"domain": failure.domain, "code": failure.code}
    except (sqlite3.Error, OSError):
        result["run_outcome"] = "ERROR"
        result["failure"] = {"domain": "ENVIRONMENT", "code": "LOCAL_STORAGE_ERROR"}
    finally:
        if orchestrator:
            adapter.fault["reconciled"] = orchestrator.reconciled
            result["effect"] = orchestrator.effect_result(OrderEffectVerifier(contracts, reader))
            result["tool_calls"] = orchestrator.calls
        else:
            result["effect"] = {"contract_outcome": "INCONCLUSIVE",
                                "evidence_gaps": ["ENVIRONMENT_START_NOT_ESTABLISHED"]}
        result["fault"] = {**adapter.fault, "activation": "TRIGGERED" if adapter.fault["triggered"]
                           else "NOT_TRIGGERED" if adapter.fault["planned"] else "NOT_PLANNED"}
        if sandbox.created and sandbox.path.exists():
            try:
                # Resolve unknown state before reset; never replay a business mutation.
                if orchestrator and orchestrator.pending:
                    orchestrator.reconcile()
                result["cleanup"] = sandbox.cleanup()
            except (RuntimeFailure, OSError, sqlite3.Error) as failure:
                result["cleanup"] = {"status": "QUARANTINE_REQUIRED",
                                     "reason": getattr(failure, "code", type(failure).__name__)}
                try:
                    destination = quarantine_path(sandbox.directory)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    sandbox.directory.rename(destination)
                    result["cleanup"]["path"] = destination.relative_to(LOCAL_ROOT.parents[1]).as_posix()
                except (OSError, RuntimeFailure):
                    result["cleanup"]["path"] = sandbox.directory.relative_to(LOCAL_ROOT.parents[1]).as_posix()
        save()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--demo", action="store_true", help="free fresh SQLite refund and independent verification (default)")
    modes.add_argument("--self-check", action="store_true", help="validate frozen contracts only; no files/network")
    modes.add_argument("--live", action="store_true", help="one paid DeepSeek session; exclusive task ledger prevents reruns")
    args = parser.parse_args()
    contracts = make_contracts("run-" + uuid.uuid4().hex,
                               driver="deepseek-http" if args.live else "deterministic")
    if args.self_check:
        contracts.validate()
        print(json.dumps({"status": "VALID", "contract_hashes": contracts.hashes,
                          "provider_requests": 0}))
        return 0
    ledger = owned_path(LOCAL_ROOT / "live-result.json")
    checkpoint = None
    if args.live:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        try:
            with ledger.open("xb") as stream:
                stream.write(canonical({"status": "SESSION_RESERVED", "contracts": {
                    "execution": contracts.execution, "effect": contracts.effect,
                    "experiment": contracts.experiment}, "contract_hashes": contracts.hashes}) + b"\n")
        except FileExistsError:
            print('{"status":"REFUSED","reason":"RPF41_LIVE_SESSION_ALREADY_RESERVED"}')
            return 2
        checkpoint = lambda result: write_result(ledger, result)
    result = run(contracts, checkpoint)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if (result["run_outcome"] == "PASS"
                 and result["effect"]["contract_outcome"] == "CONTRACT_SATISFIED_IN_RUN"
                 and result.get("cleanup", {}).get("status") == "RESET_AND_REMOVED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
