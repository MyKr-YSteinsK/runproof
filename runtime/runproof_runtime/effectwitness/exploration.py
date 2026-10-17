"""Two-trial feedback state machine over the existing order authority boundary."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from ..models import RuntimeFailure
from .contracts import canonical, digest, owned_path, quarantine_path, require
from .engine import Budget, Orchestrator
from .orders import AuthorityReader, OrderAdapter, OrderSandbox
from .pge_contracts import PGE_ROOT, SessionPlan, TARGET, utc
from .verifier import OrderEffectVerifier


class Ledger:
    """Exclusive session reservation; existing or corrupt ledgers never resume."""
    def __init__(self, path: Path, initial: dict):
        self.path = owned_path(path, task="rpf-42")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("xb") as stream:
            stream.write(canonical(initial) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def write(self, result: dict) -> None:
        # A crash/torn write still leaves the exclusive path occupied; fail closed.
        with self.path.open("r+b") as stream:
            raw = canonical(result) + b"\n"
            stream.seek(0)
            stream.write(raw)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())


class SessionBudget(Budget):
    def __init__(self, limits: dict, checkpoint):
        super().__init__(limits)
        self.checkpoint = checkpoint
        self.policies = {"PGE": 0, "B0": 0}

    def step(self) -> None:
        super().step()
        self.checkpoint()

    def reserve_trial(self, policy: str) -> None:
        require(policy in self.policies and self.policies[policy] < 2, "POLICY_TRIAL_BUDGET")
        super().fault_trial()  # all physical trials, including no-fault controls
        self.policies[policy] += 1
        self.checkpoint()

    def public(self) -> dict:
        return {**super().public(), "physical_trials_by_policy": dict(self.policies),
                "physical_trials": self.fault_trials}


class _TrialBudget:
    """No fresh quota: Orchestrator steps debit the shared session budget."""
    def __init__(self, contracts, session_budget):
        self.limits = contracts.execution["budgets"]
        self.shared = session_budget

    def step(self):
        self.shared.step()

    def fault_trial(self):
        # Already write-ahead reserved by reserve_trial before sandbox creation.
        require(self.shared.fault_trials > 0, "TRIAL_NOT_RESERVED")


def run_trial(contracts, shared: SessionBudget) -> dict:
    sandbox = OrderSandbox(contracts)
    reader = AuthorityReader(sandbox.path, contracts)
    adapter = OrderAdapter(sandbox)
    orchestrator = None
    result = {"contracts": {"execution": contracts.execution, "effect": contracts.effect,
                             "experiment": contracts.experiment}, "contract_hashes": contracts.hashes,
              "target_driver": TARGET, "run_outcome": "INCONCLUSIVE", "failure": None}
    try:
        sandbox.initialize()
        orchestrator = Orchestrator(contracts, adapter, reader, _TrialBudget(contracts, shared))
        e = contracts.effect
        orchestrator.dispatch("refund_order", {k: e[k] for k in ("order_id", "operation_id", "amount_minor")})
        if orchestrator.pending:
            orchestrator.reconcile()
        result["run_outcome"] = "PASS"
    except RuntimeFailure as failure:
        result.update(run_outcome=failure.outcome, failure={"domain": failure.domain, "code": failure.code})
    except (sqlite3.Error, OSError):
        result.update(run_outcome="ERROR", failure={"domain": "ENVIRONMENT", "code": "LOCAL_STORAGE_ERROR"})
    finally:
        if orchestrator:
            adapter.fault["reconciled"] = orchestrator.reconciled
            result["effect"] = orchestrator.effect_result(OrderEffectVerifier(contracts, reader))
            result["tool_calls"] = orchestrator.calls
        else:
            result["effect"] = {"contract_outcome": "INCONCLUSIVE", "evidence_gaps": ["TRIAL_NOT_STARTED"]}
        result["fault"] = {**adapter.fault, "activation": "TRIGGERED" if adapter.fault["triggered"]
                           else "NOT_TRIGGERED" if adapter.fault["planned"] else "NOT_PLANNED"}
        if sandbox.created:
            try:
                if orchestrator and orchestrator.pending:
                    orchestrator.reconcile()  # receipt read only, never repeat the mutation
                result["cleanup"] = sandbox.cleanup()
            except (RuntimeFailure, sqlite3.Error, OSError) as failure:
                result["cleanup"] = {"status": "QUARANTINE_REQUIRED",
                                     "reason": getattr(failure, "code", type(failure).__name__)}
                try:
                    destination = quarantine_path(sandbox.directory, task="rpf-42")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    sandbox.directory.rename(destination)
                    result["cleanup"]["path"] = destination.relative_to(PGE_ROOT.parents[1]).as_posix()
                except (RuntimeFailure, OSError):
                    result["cleanup"]["path"] = sandbox.directory.relative_to(PGE_ROOT.parents[1]).as_posix()
    return result


def project_feedback(plan: SessionPlan, trial: dict, policy: str, candidate_id: str,
                     seen_facts: set[str]) -> dict:
    from .contracts import FrozenContracts
    contracts = FrozenContracts.freeze(**trial["contracts"])
    plan.validate_trial(contracts, policy, candidate_id)
    require(trial["contract_hashes"] == contracts.hashes and trial["target_driver"] == TARGET,
            "FEEDBACK_CONTRACT_IDENTITY")
    effect = trial["effect"]
    require(trial["run_outcome"] == "PASS" and not effect.get("evidence_gaps")
            and effect["contract_outcome"] == "CONTRACT_SATISFIED_IN_RUN"
            and trial.get("cleanup", {}).get("status") == "RESET_AND_REMOVED", "FEEDBACK_NOT_VERIFIED")
    # The verifier ran against live authenticated reader snapshots in run_trial.
    # Recompute saved hashes/identity before projecting their public whitelist.
    x, e = contracts.experiment, contracts.effect
    for name in ("before", "after"):
        snapshot = effect[name]
        data = snapshot["data"]
        require(digest(data) == snapshot["sha256"] and data["source_id"] == e["authority_id"]
                and data["environment"]["run_id"] == x["run_id"]
                and data["environment"]["environment_id"] == x["environment_id"]
                and data["environment"]["owner"] == "rpf-42"
                and data["reader_id"] == "rpf41-sqlite-authority-reader"
                and data["reader_version"] == "1", "FEEDBACK_AUTHORITY_MISMATCH")
    require(effect["verifier_id"] == e["verifier_id"] and effect["verifier_version"] == "1"
            and effect["receipt_hash"] == digest(effect["after"]["data"]["receipts"]), "FEEDBACK_VERIFIER_MISMATCH")
    f = trial["fault"]
    expected_flags = ((False, False, False, False, "NOT_PLANNED") if candidate_id == "normal" else
                      (True, False, False, False, "NOT_TRIGGERED") if candidate_id == "planned-untriggered" else
                      (True, True, True, True, "TRIGGERED"))
    require(tuple(f[k] for k in ("planned", "triggered", "observed", "reconciled", "activation"))
            == expected_flags, "FEEDBACK_FAULT_PROVENANCE")
    facts = {"effect:" + effect["contract_outcome"], "activation:" + trial["fault"]["activation"]}
    if trial["fault"]["reconciled"]:
        facts.add("recovery:RECONCILED_COMMITTED_RECEIPT")
    return {"schema_version": "rpf-exploration-feedback-v1", "session_digest": plan.sha256,
            "candidate_id": candidate_id, "run_id": x["run_id"], "experiment_digest": contracts.hashes["experiment"],
            "authority_ref": {"reader": "rpf41-sqlite-authority-reader/1", "source_id": e["authority_id"],
                              "before": effect["before"]["sha256"], "after": effect["after"]["sha256"],
                              "receipts": effect["receipt_hash"]},
            "verifier": e["verifier_id"] + "/1", "fault": trial["fault"],
            "contract_outcome": effect["contract_outcome"], "run_outcome": trial["run_outcome"],
            "evidence_gaps": [], "facts": sorted(facts), "new_facts": sorted(facts - seen_facts),
            "coverage_before": sorted(seen_facts),
            "information_gain_proxy": len(facts - seen_facts), "attribution": "CORRELATIONAL_ONLY"}


class ExplorationSession:
    def __init__(self, plan: SessionPlan, *, ledger_path: Path | None = None, live: bool = False):
        plan.validate()
        require(not live or ledger_path == PGE_ROOT / "live-result.json", "LIVE_LEDGER_REQUIRED")
        self.plan = plan
        self.result = {"schema_version": "rpf42-session-result-v1", "plan": plan.document,
                       "plan_digest": plan.sha256, "mode": "LIVE_EXPLORER" if live else "MOCK_POLICY_ONLY",
                       "events": [], "provider_requests": [], "trials": [], "feedback": [],
                       "stop_reason": None, "failure": None}
        self.budget = SessionBudget(plan.document["limits"], self.save)
        self.ledger = Ledger(ledger_path, self.result) if ledger_path else None
        self.seen = {"PGE": set(), "B0": set()}
        self.halted = False
        self.save()

    def save(self):
        self.result["budget"] = self.budget.public()
        if getattr(self, "ledger", None):
            self.ledger.write(self.result)

    def event(self, name: str, **details):
        self.result["events"].append({"sequence": len(self.result["events"]) + 1,
                                      "at": utc(), "name": name, **details})
        self.save()

    def execute(self, policy: str, candidate_id: str) -> dict:
        require(not self.halted, "SESSION_SAFE_STOP")
        self.plan.candidate(candidate_id)
        self.budget.step()  # accepted structured selection, including deterministic B0
        contracts = self.plan.trial_contracts(policy, candidate_id)
        self.plan.validate_trial(contracts, policy, candidate_id)
        self.event("TRIAL_RESERVED", policy=policy, candidate_id=candidate_id,
                   run_id=contracts.experiment["run_id"], contract_hashes=contracts.hashes)
        self.budget.reserve_trial(policy)  # shared write-ahead reservation before init/side effect
        trial = run_trial(contracts, self.budget)
        self.result["trials"].append(trial)
        self.event("TRIAL_COMPLETED", policy=policy, run_id=contracts.experiment["run_id"],
                   cleanup=trial.get("cleanup"))
        try:
            feedback = project_feedback(self.plan, trial, policy, candidate_id, self.seen[policy])
        except (RuntimeFailure, KeyError, TypeError, ValueError) as failure:
            self.halted = True
            self.result.update(stop_reason="SAFE_STOP", failure={"domain": "ENVIRONMENT",
                               "code": getattr(failure, "code", "FEEDBACK_MALFORMED")})
            self.save()
            raise RuntimeFailure("ENVIRONMENT", "TRIAL_FEEDBACK_SAFE_STOP") from failure
        self.seen[policy].update(feedback["facts"])
        feedback["budget_remaining"] = {"policy_trials": 2 - self.budget.policies[policy],
            "physical_trials": self.budget.limits["fault_trials"] - self.budget.fault_trials,
            "provider_requests": self.budget.limits["provider_requests"] - self.budget.requests,
            "steps": self.budget.limits["steps"] - self.budget.steps,
            "tokens": self.budget.limits["tokens"] - self.budget.tokens if self.budget.usage_known else None}
        entry = {"policy": policy, "document": feedback, "sha256": digest(feedback)}
        self.result["feedback"].append(entry)
        self.event("FEEDBACK_VALIDATED", policy=policy, feedback_hash=entry["sha256"])
        return entry

    def finish(self):
        pge = [f["document"] for f in self.result["feedback"] if f["policy"] == "PGE"]
        complete = len(pge) == 2
        requests = self.result["provider_requests"]
        linked = (len(requests) == 2 and all(r.get("status") == "RECEIVED" and r.get("http_status") == 200
                   and r.get("selection") for r in requests)
                  and complete and requests[1].get("input_feedback_hash") == digest(pge[0])
                  and requests[1].get("tool_results_submitted") == [requests[0]["selection"]["tool_call_id"]])
        l2 = (complete and pge[0]["candidate_id"] != pge[1]["candidate_id"]
              and pge[1]["information_gain_proxy"] > 0
              and self.result["mode"] == "LIVE_EXPLORER"
              and linked)
        self.result["research"] = {"L1": bool(linked) and self.result["mode"] == "LIVE_EXPLORER",
                                   "L2": bool(l2), "H1": "SUPPORTED_IN_THIS_CASE" if l2 else "NOT_PROVEN",
                                   "attribution": "CORRELATIONAL_ONLY", "statistical_claim": False}
        self.result["comparison"] = {policy: {
            "physical_trials": self.budget.policies[policy], "distinct_valid_facts": sorted(self.seen[policy]),
            "confirmed_activations": sum(t["fault"]["triggered"] and t["fault"]["observed"]
                for t in self.result["trials"] if t["contracts"]["experiment"]["policy"] == policy),
            "provider_requests": self.budget.requests if policy == "PGE" else 0}
            for policy in ("PGE", "B0")}
        self.result["comparison"]["cost_equivalent"] = False
        if self.result["stop_reason"] is None:
            self.result["stop_reason"] = "EVIDENCE_GAIN" if complete and pge[1]["new_facts"] else "NO_NEW_INFORMATION"
        self.save()
        return self.result


def run_session(*, live=False, demo_choices=("normal", "response-lost")) -> dict:
    plan = SessionPlan.create()  # baseline order frozen before any provider/trial
    session = ExplorationSession(plan, live=live, ledger_path=PGE_ROOT / "live-result.json" if live else None)
    try:
        if live:
            from .pge_provider import explore
            explore(session)
        else:
            for candidate_id in demo_choices:
                session.execute("PGE", candidate_id)
        for candidate_id in plan.document["baseline_order"]:
            session.execute("B0", candidate_id)
    except RuntimeFailure as failure:
        session.halted = True
        session.result.update(stop_reason="PLATFORM_ERROR" if failure.domain == "PROVIDER" else
                              "BUDGET_EXHAUSTED" if "BUDGET" in failure.code else "SAFE_STOP",
                              failure={"domain": failure.domain, "code": failure.code})
    return session.finish()
