"""Offline, local-content checks for RPF-46 trial/session binding; no live imports.

This wrapper is not an issuer signature or an external trusted anchor. The old
v2 Witness remains a separate artifact with its original eligibility rules.
"""
import json
import re
from .cross_core import validate_contracts, validate_snapshot, project_feedback, SPECS
from .witness_verify import (canonical, digest, _reject, _derive_fault_activation,
                             _verify_events, verify_bytes, _unique_object)

SCHEMA = "rpf-lab-exploration-v1"
LIMITS = {"provider_requests": 2, "steps": 16, "tokens": 12000, "cost_cny": 1.5,
          "seconds": 1200, "request_seconds": 90, "fault_trials": 2}
FAULTS = {"normal": "none", "planned-untriggered": "planned-not-triggered", "response-lost": "response-lost"}


def validate_trial(t, plan):
    _reject(set(t) == {"schema_version", "round", "candidate_id", "run_id", "plan_digest", "contracts",
        "observation", "events", "claims", "feedback", "feedback_sha256", "new_facts", "witness"}, "TRIAL_FIELDS")
    n = t["round"]
    _reject(type(n) is int and n in (1, 2) and t["candidate_id"] in FAULTS
            and t["schema_version"] == "rpf-lab-trial-v1" and t["plan_digest"] == digest(plan), "TRIAL_BINDING")
    c, o = t["contracts"], t["observation"]
    _, f, x = validate_contracts(c, "order", c["experiment"]["capture_id"])
    _reject(c == plan["trial_contracts"][n-1][t["candidate_id"]] and t["run_id"] == x["run_id"], "FROZEN_TRIAL_MISMATCH")
    before, after = [validate_snapshot(o[k], f, x, "order") for k in ("authority_before", "authority_after")]
    expected = {**SPECS["order"]["oracle"](f, x["environment_id"], before, after),
                "before_sha256": o["authority_before"]["sha256"], "after_sha256": o["authority_after"]["sha256"]}
    _reject(o["effect"] == expected and expected["contract_outcome"] == "CONTRACT_SATISFIED_IN_RUN", "TRIAL_ORACLE")
    fault = {"planned": t["candidate_id"] != "normal", "triggered": t["candidate_id"] == "response-lost",
             "observed": t["candidate_id"] == "response-lost", "reconciled": t["candidate_id"] == "response-lost"}
    fault["activation"] = _derive_fault_activation({**fault, "activation": "TRIGGERED" if fault["triggered"] else
                                                  "NOT_TRIGGERED" if fault["planned"] else "NOT_PLANNED"})
    _reject(o["fault"] == fault and o["run_outcome"] == "PASS", "TRIAL_FAULT")
    _reject(o["cleanup"] == {"status": "RESET_AND_REMOVED", "reset_generation": 1,
                             "receipt_count_after_reset": 0}, "TRIAL_CLEANUP")
    receipt = after["receipts"][0]
    expected_result = ({"status": "UNKNOWN_OUTCOME", "operation_id": f["operation_id"],
                        "reason": "CONTROLLED_POST_COMMIT_RESPONSE_LOSS"} if fault["triggered"] else
                       {"status": "COMMITTED", "receipt_id": receipt["receipt_id"], "operation_id": f["operation_id"], "committed_revision": 1})
    _reject(o["tool_calls"] == [{"name": "refund_order", "arguments": {k: f[k] for k in
            ("order_id", "operation_id", "amount_minor")}, "result": expected_result}], "TRIAL_TOOL_RESULT")
    _reject(o["reconciliation"] == ({"status": "RECONCILED_COMMITTED", "operation_id": f["operation_id"],
            "receipt_id": receipt["receipt_id"]} if fault["triggered"] else None), "TRIAL_RECONCILE")
    feedback = project_feedback("order", expected, fault)
    _reject(o["feedback"] == feedback and t["feedback"] == feedback and t["feedback_sha256"] == digest(feedback), "TRIAL_FEEDBACK")
    _reject(t["claims"] == {"contract_outcome": expected["contract_outcome"], "fault_activation": fault["activation"],
        "attribution_strength": "CORRELATIONAL_ONLY", "reproduction": "NOT_TESTED", "run_outcome": "PASS"}, "TRIAL_CLAIMS")
    _verify_events(t["events"], {**o, "experiment": x, "contracts": c})
    _reject(t["witness"]["status"] == ("CONTENT_CHECKED_LOCAL" if fault["triggered"] else
            "NOT_ISSUED_PROFILE_NOT_ELIGIBLE") and t["witness"]["external_anchor"] is False
            and t["witness"]["issuer_authenticity"] == "NOT_ESTABLISHED", "TRIAL_WITNESS_ELIGIBILITY")
    return feedback


def verify_session(s):
    _reject(s["schema_version"] == SCHEMA and s["plan_digest"] == digest(s["plan"])
            and s["session_id"] == s["plan"]["session_id"] and s["plan"]["limits"] == LIMITS
            and s["source"] == "LIVE_LOCAL_SIMULATION" and s["explorer"] == "LIVE_EXPLORER_DEEPSEEK"
            and s["target_driver"] == "DETERMINISTIC_CONTROLLED_TARGET" and s["rationale"] == "RATIONALE_NOT_RECORDED",
            "SESSION_BINDING")
    _reject(len(s["trials"]) <= len(s["trial_reservations"]) <= 2 and len(s["selections"]) <= 2
            and len(s["provider_requests"]) <= 2 and len(s["trials"]) <= len(s["selections"]), "SESSION_COUNTS")
    for i, e in enumerate(s["events"], 1):
        _reject(e["seq"] == i and e["event_id"] == "pge-event-"+str(i)
                and e["facts_sha256"] == digest(e["facts"]), "SESSION_EVENT_IDENTITY")
    call_ids = set()
    for i, selection in enumerate(s["selections"], 1):
        _reject(selection["round"] == i and selection["candidate_id"] in FAULTS
                and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", selection["tool_call_id"])
                and selection["tool_call_id"] not in call_ids, "SESSION_SELECTION_IDENTITY")
        call_ids.add(selection["tool_call_id"])
    seen = set()
    for i, t in enumerate(s["trials"], 1):
        _reject(t["round"] == i and s["trial_reservations"][i-1]["run_id"] == t["run_id"]
                and s["trial_reservations"][i-1]["status"] == "COMPLETED", "SESSION_TRIAL_SEQUENCE")
        validate_trial(t, s["plan"])
        fact = "fault_activation=" + t["observation"]["fault"]["activation"]
        _reject(t["new_facts"] == ([] if fact in seen else [fact]), "INFORMATION_GAIN")
        seen.add(fact)
        selection = s["selections"][t["round"]-1]
        _reject(selection["candidate_id"] == t["candidate_id"] and selection["round"] == t["round"], "SELECTION_BINDING")
        if t["round"] == 2:
            prior = s["trials"][0]
            _reject(selection["input_feedback_hash"] == prior["feedback_sha256"], "FEEDBACK_LINK")
            frozen = [e for e in s["events"] if e["type"] == "PROVIDER_INPUT_FROZEN" and e["facts"]["round"] == 2]
            feedback = [e for e in s["events"] if e["type"] == "AUTHORITY_FEEDBACK_VALIDATED" and e["facts"]["round"] == 1]
            _reject(len(frozen) == len(feedback) == 1 and feedback[0]["seq"] < frozen[0]["seq"]
                    and frozen[0]["facts"]["feedback_hash"] == prior["feedback_sha256"]
                    and frozen[0]["facts"]["delivered_tool_call_id"] == s["selections"][0]["tool_call_id"]
                    and frozen[0]["facts"]["messages_hash"] == selection["input_messages_hash"], "FEEDBACK_EVENT_ORDER")
    if s["status"] == "COMPLETED":
        _reject(len(s["trials"]) == len(s["provider_requests"]) == len(s["selections"]) == 2
                and s["usage"]["usage_known"] is True and s["usage"]["provider_requests"] == 2
                and s["usage"]["steps"] == 16 and s["usage"]["tokens"] <= LIMITS["tokens"]
                and s["usage"]["estimated_cost_cny_upper"] <= LIMITS["cost_cny"]
                and s["run_outcome"] == "PASS", "SESSION_COMPLETION")
        l2 = s["selections"][0]["candidate_id"] != s["selections"][1]["candidate_id"] and bool(s["trials"][1]["new_facts"])
        _reject(s["research"] == {"L1": True, "L2": l2, "H1": "LIMITED_MECHANISM_EVIDENCE_ONLY" if l2 else
                "NOT_PROVEN_IN_THIS_RUN", "attribution": "CORRELATIONAL_ONLY"}, "RESEARCH_OVERCLAIM")
    return {"status": "CONTENT_CHECKED_LOCAL", "external_anchor": False, "issuer_authenticity": "NOT_ESTABLISHED"}


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("session")
    a = p.parse_args()
    try:
        from pathlib import Path
        raw = Path(a.session).read_bytes()
        _reject(len(raw) <= 262144, "SESSION_TOO_LARGE")
        s = json.loads(raw, object_pairs_hook=_unique_object)
        print(json.dumps(verify_session(s), sort_keys=True))
        return 0
    except Exception:
        print('{"status":"INCONCLUSIVE","error_code":"SESSION_EVIDENCE_REJECTED"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
