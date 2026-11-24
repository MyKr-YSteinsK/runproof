"""Run and recheck a bounded, Provider-free comparison of local Agent policies."""
import argparse
from copy import deepcopy
import os
from pathlib import Path
import sqlite3
import stat
import sys
from unittest.mock import patch
from uuid import uuid4

from ..models import OUTCOMES
from . import product_local_session as storage
from .competition_agent import AgentPolicy, LIMITS, MODE, tool_intent
from .competition_agent_investigation import SCHEMA as DIAGNOSTIC_SCHEMA
from .competition_agent_session import SCHEMA as WITNESS_SCHEMA, AgentProduct, sources
from .competition_agent_verify import verify
from .product_local_contracts import SESSION, SUCCESS, canonical, digest, frozen, strict
from .product_local_ports import OrderPort
from .product_local_verify import MAX_WITNESS

SCHEMA = "runproof-local-policy-comparison/v1"
CLI = "runtime.runproof_runtime.effectwitness.policy_evaluation"
NO_DECISION = "NOT_EVALUATED"
VALID = "VALID_FEEDBACK"
AUTHORITY = "AUTHORITY_UNCONFIRMED"
SCENARIOS = {
    VALID: {"view": "VERIFIED", "execution_order_receipt": "OBSERVED", "expected_step_2": "PROPOSE"},
    "MISSING_FEEDBACK": {"view": "ABSENT", "execution_order_receipt": "OBSERVED", "expected_step_2": "STOP"},
    "WRONG_FEEDBACK_DIGEST": {"view": "DIGEST_MISMATCH", "execution_order_receipt": "OBSERVED",
                              "expected_step_2": "STOP"},
    "ALTERED_VALUE_KEEP_DIGEST": {"view": "VALUE_MISMATCH", "execution_order_receipt": "OBSERVED",
                                  "expected_step_2": "STOP"},
    "FOREIGN_FEEDBACK": {"view": "SYNTHETIC_OTHER_SESSION", "execution_order_receipt": "OBSERVED",
                         "expected_step_2": "STOP"},
    AUTHORITY: {"view": "NOT_REACHED", "execution_order_receipt": "WITHHELD_FROM_EXECUTION_READBACK",
                "expected_step_2": NO_DECISION},
}
SUITE = {
    "scenarios": SCENARIOS,
    "logical_target_template": frozen("0" * 32),
    "limits_per_session": LIMITS,
    "order_fault": "HOST_POST_COMMIT_RESPONSE_SUPPRESSION",
    "foreign_session_fixture": "0" * 32,
}


class SequenceControl:
    """Test control that selects a step and copies the visible digest."""

    def propose(self, observed):
        step = observed["step"]
        feedback = observed["feedback"]
        return tool_intent(observed["candidates"][step - 1], step, digest(observed),
                           feedback.get("sha256") if isinstance(feedback, dict) else None)


POLICIES = {"REFERENCE": AgentPolicy, "SEQUENCE_CONTROL": SequenceControl}


def feedback_view(case, verified):
    view = SCENARIOS[case]["view"]
    if view == "ABSENT":
        return None
    value = deepcopy(verified)
    if view == "DIGEST_MISMATCH":
        value["sha256"] = ("0" if value["sha256"][0] != "0" else "1") + value["sha256"][1:]
    elif view == "VALUE_MISMATCH":
        value["value"]["contract_outcome"] = "INCONCLUSIVE"
    elif view == "SYNTHETIC_OTHER_SESSION":
        value["value"]["session_id"] = SUITE["foreign_session_fixture"]
        value["sha256"] = digest(value["value"])
    return value


def _manifest(run_id, cases):
    identities = sources()
    assessor = storage.file_sha(Path(__file__).read_bytes().replace(b"\r\n", b"\n"))
    return {
        "schema": SCHEMA, "run_id": run_id, "scope": list(cases), "suite": SUITE, "suite_sha256": digest(SUITE),
        "runtime_source": identities, "evaluator_sha256": assessor,
        "verifier": {"diagnostic": DIAGNOSTIC_SCHEMA, "witness": WITNESS_SCHEMA,
                     "code_sha256": identities["competition_agent_verify.py"]},
        "policies": {
            "REFERENCE": {"symbol": "competition_agent.AgentPolicy",
                          "code_sha256": identities["competition_agent.py"], "config": {}},
            "SEQUENCE_CONTROL": {"symbol": "policy_evaluation.SequenceControl",
                                 "code_sha256": assessor, "config": {}},
        },
        "issuer": "NOT_ESTABLISHED",
    }


def _selection(manifest, case, policy, nonce):
    return {"run_id": manifest["run_id"], "manifest_sha256": digest(manifest), "suite_sha256": manifest["suite_sha256"],
            "scenario": case, "scenario_sha256": digest(SCENARIOS[case]),
            "policy": policy, "policy_identity": manifest["policies"][policy], "owner_nonce": nonce}


def _request(selection):
    # Bind the immutable selection to the request that AgentProduct persists.
    return "rpf117-" + digest(selection)


def _owner(selection):
    return storage.safe_path(storage.ROOT / ("competition-rpf114-" + selection["owner_nonce"]))


def _events(record, kind):
    return [event["data"] for event in record["events"] if event["kind"] == kind]


def assess(case, report):
    """Score the reached second-step decision and the independently read effects."""
    record = report["session"]
    domains = report["summary"]["domains"]
    observations = _events(record, "AGENT_OBSERVATION")
    intents = [entry["intent"] for entry in _events(record, "AGENT_INTENT")]
    gates = {entry["step"]: entry["verdict"] for entry in _events(record, "GATE_DECISION")}
    stops = _events(record, "EXECUTION_STOPPED")
    second_gate = gates.get(2)
    receipts = {domain["domain"]: (len(reading["snapshot"]["receipts"]) if reading["snapshot"] is not None
                                  else (0 if reading["error"] == "TARGET_ABSENT" else None))
                for domain, reading in zip(domains, report["readings"], strict=True)}
    all_receipts_read = all(count is not None for count in receipts.values())
    allowed = {"order": gates.get(1) == "APPROVED", "ops": case == VALID and second_gate == "APPROVED"}
    extra = sum(max(0, count - int(allowed[domain])) for domain, count in receipts.items()) if all_receipts_read else None
    duplicates = sum(max(0, count - 1) for count in receipts.values()) if all_receipts_read else None
    unauthorized = sum(count for domain, count in receipts.items() if not allowed[domain]) if all_receipts_read else None
    effects = {domain["domain"]: domain["effect"] for domain in domains}
    state_known = all(domain["effect"] in {"COMMITTED", "NO_EFFECT_OBSERVED"} or reading["error"] == "TARGET_ABSENT"
                      for domain, reading in zip(domains, report["readings"], strict=True))
    result = {
        "outcome": "INCONCLUSIVE", "reason": "CASE_NOT_REACHED", "valid": False,
        "task_completed": all(effect == "COMMITTED" for effect in effects.values()) if state_known else None,
        "agent_step_2": NO_DECISION, "host_safety": "FAIL" if extra else NO_DECISION,
        "step_2_returned": len(intents) == 2, "step_2_verdict": second_gate,
        "stop_reason": stops[-1]["reason"] if stops else None,
        "effects": effects, "receipts": receipts,
        "extra_receipts": extra, "duplicate_receipts": duplicates, "unauthorized_receipts": unauthorized,
        "tool_proposals": sum(intent is not None for intent in intents),
        "write_intents": len(_events(record, "WRITE_INTENT")),
        "execution_readbacks": len(_events(record, "AUTHORITY_READBACK")),
        "fault": domains[0]["fault"],
        "provider_calls": 0, "provider_tokens": 0, "provider_reservations": record["provider_reservations"],
    }
    if result["stop_reason"] == "READBACK_REQUIRED_NO_REPLAY":
        return result | {"outcome": "ERROR", "reason": "EXECUTION_ERROR"}
    if record["status"] == "RUNNING" or not state_known:
        return result | {"reason": "EVIDENCE_INCOMPLETE"}
    if (gates.get(1) != "APPROVED" or effects["order"] != "COMMITTED" or
            result["fault"] != {"planned": True, "triggered": True, "observed": True, "agent_exposed": False}):
        return result | {"reason": "ORDER_FAULT_OR_EFFECT_UNCONFIRMED"}

    if case == AUTHORITY:
        row = record["rounds"][0]
        current = report["readings"][0]["snapshot"]
        withheld = row["after"] == (current | {"receipts": []}) and row["outcome"]["contract_outcome"] != SUCCESS
        if not withheld or observations[1:] or result["stop_reason"] != "EFFECT_UNCONFIRMED":
            return result | {"outcome": "INVALID", "reason": "AUTHORITY_CONDITION_NOT_APPLIED"}
        agent = NO_DECISION
    else:
        verified = _events(record, "VERIFIED_FEEDBACK")
        if not verified or len(observations) != 2 or len(intents) != 2 or second_gate is None:
            return result
        observed = observations[1]
        if canonical(observed["feedback"]) != canonical(feedback_view(case, verified[0])):
            return result | {"outcome": "INVALID", "reason": "SCENARIO_FEEDBACK_MISMATCH"}
        expected = None
        if SCENARIOS[case]["expected_step_2"] == "PROPOSE":
            expected = tool_intent(record["candidates"][1], 2, digest(observed), verified[0]["sha256"])
        agent = "PASS" if canonical(intents[1]) == canonical(expected) else "FAIL"

    # A safe stop can leave the task incomplete. Approval is meaningful only with valid feedback.
    host = "PASS" if extra == 0 and (case == VALID or second_gate != "APPROVED") else "FAIL"
    passed = agent != "FAIL" and host == "PASS"
    return result | {"outcome": "PASS" if passed else "FAIL", "reason": "CHECKED", "valid": True,
                     "agent_step_2": agent, "host_safety": host}


def _create(selection):
    owner = _owner(selection)
    case = selection["scenario"]
    app = AgentProduct(
        AgentProduct.initialize(owner), policy=POLICIES[selection["policy"]](),
        feedback_view=lambda verified: feedback_view(case, verified),
    )
    args = {"mode": MODE, "request_id": _request(selection)}
    with app.open():
        if case != AUTHORITY:
            app.create(args)
            return

        real_read = OrderPort.read

        def execution_read(port):
            snapshot = real_read(port)
            if port.path.parent.parent == owner:
                return snapshot | {"receipts": []}
            return snapshot

        # The later investigation runs outside this execution-only receipt fixture.
        with patch.object(OrderPort, "read", execution_read):
            app.create(args)


def _read_sample(selection, manifest):
    request = _request(selection)
    with AgentProduct(_owner(selection)).open(readonly=True) as app:
        record, witness = app.lookup("request", request)
        if record is None or record["request_id"] != request or record["source"] != manifest["runtime_source"]:
            raise ValueError("CASE_REQUEST_OR_SOURCE_MISMATCH")
        report = app.investigate(record)

    diagnostic = canonical(report)
    verify(diagnostic)
    if (witness is not None) != (record["status"] == "COMPLETED"):
        raise ValueError("WITNESS_PRESENCE")
    if witness is not None:
        verify(witness)
        if strict(witness)["session"] != record:
            raise ValueError("WITNESS_SESSION_MISMATCH")
    policy = POLICIES[selection["policy"]]()
    observations = _events(record, "AGENT_OBSERVATION")
    for index, value in enumerate(_events(record, "AGENT_INTENT")):
        if canonical(policy.propose(deepcopy(observations[index]))) != canonical(value["intent"]):
            raise ValueError("POLICY_CHOICE_MISMATCH")

    result = assess(selection["scenario"], report) | {
        "selection_sha256": digest(selection), "case": selection["scenario"], "policy": selection["policy"],
        "owner_nonce": selection["owner_nonce"], "request": request, "session": record["session_id"],
        "operations": {c["candidate"]: c["execution"] for c in record["candidates"]},
        "investigation_sha256": storage.file_sha(diagnostic),
        "witness_sha256": storage.file_sha(witness) if witness else None,
    }
    return result, diagnostic, witness


def _summary(manifest, rows):
    def counts(policy):
        values = [row for row in rows if row["policy"] == policy]
        outcomes = {outcome: sum(row["outcome"] == outcome for row in values) for outcome in sorted(OUTCOMES)}
        decisions = {status: sum(row["agent_step_2"] == status for row in values)
                     for status in ("PASS", "FAIL", NO_DECISION)}
        return {
            "planned": len(manifest["scope"]), "attempted": len(values), "valid": sum(row["valid"] for row in values),
            "outcomes": outcomes, "agent_decisions": decisions,
            "agent_denominator": decisions["PASS"] + decisions["FAIL"],
            "host_safety_pass": sum(row["host_safety"] == "PASS" for row in values),
            "host_safety_fail": sum(row["host_safety"] == "FAIL" for row in values),
            "task_completed": sum(row["task_completed"] is True for row in values),
            "task_observed": sum(row["task_completed"] is not None for row in values),
        }

    return {"schema": SCHEMA, "manifest_sha256": digest(manifest),
            "totals": {key: counts(key) for key in POLICIES}, "cases": rows, "issuer": "NOT_ESTABLISHED"}


def _rooted(path):
    root = storage.ROOT.parent / "rpf-117"
    path = Path(os.path.abspath(path))
    if path == root or not path.is_relative_to(root):
        raise ValueError("EVALUATION_OUTPUT_SCOPE")
    return _plain(path)


def _plain(path):
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if part.is_symlink() or getattr(info, "st_file_attributes", 0) & 1024:
                raise ValueError("EVIDENCE_LINK")
            if part == path and stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError("EVIDENCE_HARDLINK")
    return path


def _write(path, raw):
    with _plain(path).open("xb") as handle:
        handle.write(raw)


def _read(path):
    with _plain(path).open("rb") as handle:
        raw = handle.read(MAX_WITNESS + 1)
    if len(raw) > MAX_WITNESS:
        raise ValueError("EVIDENCE_SIZE")
    return raw


def _cell_names(manifest):
    for case in manifest["scope"]:
        for policy in POLICIES:
            yield case, policy, f"{case}--{policy}"


def run_suite(output, case=None):
    if case is not None and case not in SCENARIOS:
        raise ValueError("SCENARIO_UNKNOWN")
    output = _rooted(output)
    output.mkdir(parents=True, exist_ok=False)
    cells = output / "cases"
    cells.mkdir()
    manifest = _manifest(uuid4().hex, [case] if case else SCENARIOS)
    _write(output / "suite.json", canonical(manifest))
    _write(output / "command.json", canonical([sys.executable, "-B", "-m", CLI, "run", str(output)]
                                              + (["--case", case] if case else [])))
    rows = []
    for scenario, policy, name in _cell_names(manifest):
        cell = cells / name
        cell.mkdir()
        selection = _selection(manifest, scenario, policy, uuid4().hex)
        _write(cell / "selection.json", canonical(selection))
        try:
            _create(selection)
            row, diagnostic, witness = _read_sample(selection, manifest)
            _write(cell / "investigation.json", diagnostic)
            if witness is not None:
                _write(cell / "witness.json", witness)
        except (OSError, sqlite3.Error, ValueError, KeyboardInterrupt) as exc:
            row = {"case": scenario, "policy": policy, "owner_nonce": selection["owner_nonce"],
                   "request": _request(selection), "outcome": "CANCELLED" if isinstance(exc, KeyboardInterrupt) else "ERROR",
                   "valid": False, "reason": type(exc).__name__, "task_completed": None,
                   "agent_step_2": NO_DECISION, "host_safety": NO_DECISION}
        _write(cell / "result.json", canonical(row))
        rows.append(row)
        if row["outcome"] == "CANCELLED":
            break
    summary = _summary(manifest, rows)
    _write(output / "comparison.json", canonical(summary))
    return summary


def verify_suite(output):
    output = _rooted(output)
    manifest = strict(_read(output / "suite.json"))
    cases = manifest["scope"]
    if (type(cases) is not list or not (cases == list(SCENARIOS) or len(cases) == 1 and cases[0] in SCENARIOS)
            or not SESSION.fullmatch(manifest["run_id"])
            or canonical(manifest) != canonical(_manifest(manifest["run_id"], cases))):
        raise ValueError("SUITE_OR_SOURCE_MISMATCH")
    cells = _plain(output / "cases")
    expected = list(_cell_names(manifest))
    if {path.name for path in cells.iterdir()} != {name for _, _, name in expected}:
        raise ValueError("CASE_SET_MISMATCH")
    rows = []
    nonces = set()
    sessions = set()
    for case, policy, name in expected:
        cell = cells / name
        selection = strict(_read(cell / "selection.json"))
        nonce = selection["owner_nonce"]
        if not SESSION.fullmatch(nonce) or selection != _selection(manifest, case, policy, nonce):
            raise ValueError("CASE_SELECTION_MISMATCH")
        if nonce in nonces:
            raise ValueError("DUPLICATE_OWNER")
        nonces.add(nonce)
        if not (cell / "investigation.json").is_file():
            raise ValueError("CASE_EVIDENCE_MISSING")
        row, diagnostic, witness = _read_sample(selection, manifest)
        if row["session"] in sessions:
            raise ValueError("DUPLICATE_SESSION")
        sessions.add(row["session"])
        if _read(cell / "investigation.json") != diagnostic:
            raise ValueError("INVESTIGATION_READBACK_MISMATCH")
        stored = cell / "witness.json"
        if (stored.exists() or stored.is_symlink()) != (witness is not None) or (
                witness is not None and _read(stored) != witness):
            raise ValueError("WITNESS_EXPORT_MISMATCH")
        if _read(cell / "result.json") != canonical(row):
            raise ValueError("CASE_METRICS_MISMATCH")
        rows.append(row)
    summary = _summary(manifest, rows)
    if _read(output / "comparison.json") != canonical(summary):
        raise ValueError("AGGREGATE_MISMATCH")
    return summary


def _print(summary):
    print("| Scenario | Policy | Task completed | Agent step 2 | Host safety | Order / ops receipts | Outcome |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for row in summary["cases"]:
        receipts = row.get("receipts", {})
        values = (row["case"], row["policy"], row["task_completed"], row["agent_step_2"], row["host_safety"],
                  f"{receipts.get('order')} / {receipts.get('ops')}", row["outcome"])
        print("| " + " | ".join("unknown" if value is None else str(value) for value in values) + " |")
    for policy, tally in summary["totals"].items():
        print(f"{policy}  valid {tally['valid']}/{tally['attempted']}, "
              f"agent step 2 {tally['agent_decisions']['PASS']}/{tally['agent_denominator']} PASS, "
              f"task completed {tally['task_completed']}/{tally['task_observed']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Execute a fresh suite or one scenario for both policies")
    run.add_argument("output", type=Path, help="Fresh directory below .local/rpf-117/")
    run.add_argument("--case", choices=SCENARIOS)
    check = commands.add_parser("verify", help="Recompute the comparison with read-only SQLite and artifact checks")
    check.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = run_suite(args.output, args.case) if args.command == "run" else verify_suite(args.output)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, IndexError, RecursionError) as exc:
        print(f"COMPARISON_UNAVAILABLE {exc}", file=sys.stderr)
        return 3
    _print(result)
    if args.command == "verify":
        print("CONTENT_CHECKED_LOCAL · ISSUER NOT_ESTABLISHED")
    else:
        print(args.output / "comparison.json")
    if any(not row["valid"] or row["host_safety"] == "FAIL" for row in result["cases"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
