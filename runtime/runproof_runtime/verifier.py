"""Deterministic state and trajectory verification."""

from __future__ import annotations

from typing import Any

from .models import INITIAL_STATE, TARGET_STATE, state_diff


VERIFIER_ID = "rpf-deterministic-state-verifier"
VERIFIER_VERSION = "1.0.0"


def verify_run(
    initial_state: dict[str, Any] | None,
    actual_state: dict[str, Any] | None,
    *,
    initial_verified: bool,
    mutation_count: int,
    readback_observed: bool,
    unresolved_unknown: bool,
    blind_retry_attempts: int,
    fault: dict[str, Any],
) -> dict[str, Any]:
    checks = {
        "initial_state_verified": initial_verified and initial_state == INITIAL_STATE,
        "required_target_state": actual_state == TARGET_STATE,
        "exactly_one_mutation": mutation_count == 1,
        "actual_state_read_back": readback_observed,
        "no_unresolved_unknown_outcome": not unresolved_unknown,
        "no_blind_retry_attempt": blind_retry_attempts == 0,
        "planned_fault_triggered_and_observed": not fault["planned"] or (fault["triggered"] and fault["observed"]),
        "planned_fault_reconciled": not fault["planned"] or fault["reconciled"],
    }
    violated = [name for name, passed in checks.items() if not passed]
    return {
        "layer": "Verified Result",
        "verifier_id": VERIFIER_ID,
        "verifier_version": VERIFIER_VERSION,
        "expected_state": TARGET_STATE,
        "initial_state": initial_state,
        "actual_state": actual_state,
        "state_diff": state_diff(initial_state, actual_state),
        "checks": checks,
        "violated_invariants": violated,
        "passed": not violated,
        "evidence": {
            "mutation_count": mutation_count,
            "readback_observed": readback_observed,
            "unresolved_unknown": unresolved_unknown,
            "blind_retry_attempts": blind_retry_attempts,
        },
    }
