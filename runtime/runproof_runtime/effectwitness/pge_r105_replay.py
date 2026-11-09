"""Deterministic, zero-effect synthetic selection and fixed-order comparison."""
import json

from . import pge_r105_contracts as c
from .pge_r105_gate import admit

SCENARIOS = ("INITIAL_FROZEN_SEED", "MISSING_CONTINUATION_FEEDBACK", "VERIFIED_NORMAL", "UNKNOWN_LATCHED")


def proposal(catalog, ledger, candidate_id, proposal_id):
    return {"schema": c.PROPOSAL, "proposal_id": proposal_id, "candidate_id": candidate_id,
            "candidate_sha256": catalog[candidate_id]["candidate_sha256"], "ledger_sha256": c.digest(ledger)}


def fixture_inputs(scenario):
    if scenario not in SCENARIOS:
        raise ValueError("FIXTURE_SCENARIO")
    scope = {"origin": "LOCAL", "source_git_sha": "1" * 40, "run_id": "2" * 32, "owner": "3" * 32}
    catalog = c.candidate_catalog(scope)
    initial = scenario == "INITIAL_FROZEN_SEED"
    unknown = scenario == "UNKNOWN_LATCHED"
    ledger = {"schema": c.LEDGER, "scope": scope, "mode": c.FIXTURE, "revision": 0 if initial else 1,
              "seed": c.NORMAL, "completed": [] if initial else [c.NORMAL],
              "consumed_proposals": [] if initial else ["4" * 32], "latched": unknown,
              "reconciliation": "COMMITTED" if unknown else "NONE", "expected_feedback_sha256": None,
              "remaining": dict(c.LIMIT) if initial else {key: cap - catalog[c.NORMAL]["cost"][key]
                                                          for key, cap in c.LIMIT.items()}}
    if initial:
        return catalog, ledger, None
    prior = catalog[c.NORMAL]
    contract = c.frozen_case(scope, "NORMAL")["contracts"]["order"]
    readback = {"case": "NORMAL", "effect": "SYNTHETIC_CONFIRMED",
                "outcome": "CONTRACT_SATISFIED_IN_RUN"}
    feedback = {"schema": c.FEEDBACK, "evidence_origin": c.FIXTURE, "scope": dict(scope),
                "ledger_revision": 1, "candidate_id": c.NORMAL, "case": "NORMAL",
                "contract_sha256": prior["contract_sha256"], "effect_contract_sha256": contract["sha256"],
                "operation_id": contract["execution"]["operation_id"],
                "environment_id": contract["execution"]["environment_id"], "oracle": c.FEEDBACK_ORACLE,
                "authority": c.FEEDBACK_AUTHORITY, "outcome": readback["outcome"],
                "evidence_sha256": c.digest(readback)}
    ledger["expected_feedback_sha256"] = c.digest(feedback)
    return catalog, ledger, None if scenario == "MISSING_CONTINUATION_FEEDBACK" else feedback


def replay():
    traces = []
    for scenario in SCENARIOS:
        catalog, ledger, feedback = fixture_inputs(scenario)
        ordinal = len(ledger["completed"])
        fixed = (c.NORMAL, c.UNKNOWN)[ordinal]
        # Keep the candidate and proposal ID fixed between the missing and
        # verified feedback scenarios to isolate the admission input.
        selected = c.STOP if ledger["latched"] else fixed
        fixture_proposal = proposal(catalog, ledger, selected, "5" * 32)
        fixed_proposal = proposal(catalog, ledger, fixed, "5" * 32)
        traces.append({
            "scenario": scenario,
            "remaining_budget": dict(ledger["remaining"]),
            "feedback_quality": ("VERIFIED_SHAPE_FIXTURE" if feedback is not None else "MISSING"
                                 if ordinal else "NO_PREVIOUS_ROUND"),
            "feedback_anchor": c.digest(feedback) if feedback is not None else None,
            "fixture": {"proposal": fixture_proposal, "admission": admit(fixture_proposal, catalog, feedback, ledger)},
            "fixed_order": {"proposal": fixed_proposal, "admission": admit(fixed_proposal, catalog, feedback, ledger)},
            "candidate_filter": {name: admit(proposal(catalog, ledger, name, "5" * 32), catalog, feedback, ledger)
                                 for name in catalog},
            "actual_execution": "NOT_RUN",
        })
    return {"schema": "rpf105-selection-replay-v1", "evidence_origin": c.FIXTURE,
            "explorer_kind": "FIXTURE", "actual_tool_calls": 0, "physical_runs": 0,
            "real_explorer": "NOT_RUN", "traces": traces}


if __name__ == "__main__":
    print(json.dumps(replay(), sort_keys=True))
