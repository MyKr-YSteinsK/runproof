"""Run and independently recheck the opted-in RPF-128 / RPF-129 timeout comparison."""
import argparse
from contextlib import closing, nullcontext
from hashlib import sha256
import os
from pathlib import Path
import platform
import sqlite3
from uuid import uuid4

from . import timeout_jiuwen
from .competition_agent import AgentPolicy, tool_intent
from .competition_agent_session import ControllerGate, append, observation, readback, sources
from .competition_agent_verify import verify_snapshot
from .policy_evaluation import _plain, _read, _scoped, _write
from .product_local_contracts import SESSION, SUCCESS, canonical, digest, frozen, strict
from .product_local_ports import OpsPort, OrderPort
from .product_local_session import ResponseLost


SCHEMA = "runproof-timeout-experiment/v1"
SCOPE = "rpf-128-129"
TASK = "Refund the paid order once. Apply the configuration only after the refund is verified."
SIGNAL = {"tool": "refund_order", "response": "TIMEOUT", "status": "UNKNOWN_OUTCOME"}
FAULT = {"planned": True, "triggered": True, "observed": True, "agent_exposed": False}
FOLLOW = "follow"
SEQUENCE = "sequence"
APPLY = "APPLY_CONFIG"
NO_EFFECT = "REPORT_NO_EFFECT"
HUMAN = "HANDOFF_NO_RETRY"
ACTIONS = {"REFUND_VERIFIED": APPLY, "ROLLED_BACK_NO_EFFECT": NO_EFFECT, "UNRESOLVED": HUMAN}
CASES = {
    "A": ("REFUND_VERIFIED", "APPROVED", "APPROVED", (1, 1), (1, 1)),
    "B": ("ROLLED_BACK_NO_EFFECT", "NO_EFFECT_REPORTED", "VERIFIED_FEEDBACK_REQUIRED", (0, 0), (0, 0)),
    "C": ("UNRESOLVED", "HUMAN_REVIEW_NO_RETRY", "UNKNOWN_PENDING", (1, 0), (1, 0)),
}
COMMITTED = {"executor": "SYNCHRONOUS_SQLITE", "transaction": "COMMITTED", "connection_closed": True}
ROLLED_BACK = {"executor": "SYNCHRONOUS_SQLITE", "transaction": "ROLLED_BACK", "connection_closed": True,
               "began": True, "state_rows_staged": 1, "receipts_staged": 1, "transaction_active": False}


class DecisionAuthorityUnavailable(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def scope(path):
    return _scoped(path, SCOPE)


def runtime_source():
    files = (Path(__file__), Path(timeout_jiuwen.__file__))
    return sources() | {p.name: sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in files}


def write_json(path, value):
    _write(path, canonical(value))


def locked_read(path, cls, contract):
    # A sealed experiment has no live SQLite sidecars. Reject them before opening.
    path = _plain(path)
    for ending in ("-journal", "-wal", "-shm"):
        require(not _plain(Path(str(path) + ending)).exists(), "AUTHORITY_NOT_CLOSED")
    return cls(path, contract, readonly=True).read()  # mode=ro and query_only in DomainPort


def rollback_refund(order):
    """Stage both changes inside one owned transaction and close after synchronous rollback."""
    with closing(sqlite3.connect(order.path.as_uri() + "?mode=rw", uri=True)) as db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        began = db.in_transaction
        changed = db.execute("UPDATE state SET payload=? WHERE id=1 AND payload=?",
                             (canonical(order.updated()), canonical(order.initial()))).rowcount
        inserted = db.execute("INSERT INTO receipts VALUES (?,?)",
                              (order.effect["operation_id"], canonical(order.receipt()))).rowcount
        db.rollback()
        active = db.in_transaction
    return {"executor": "SYNCHRONOUS_SQLITE", "transaction": "ROLLED_BACK", "began": began,
            "state_rows_staged": changed, "receipts_staged": inserted,
            "transaction_active": active, "connection_closed": True}


def initial(port):
    return {port.key: port.initial(), "receipts": []}


def case_record(manifest, cell):
    return {"session_id": cell["session_id"], "source": manifest["source"],
            "candidates": frozen(cell["session_id"]), "events": []}


def order_binding(record, value):
    contract = record["candidates"][0]
    execution = contract["execution"]
    return {"session_id": record["session_id"], "environment_id": execution["environment_id"],
            "operation_id": execution["operation_id"], "contract_sha256": contract["sha256"], **value}


def decision_snapshot(order, simulate_unavailable):
    if simulate_unavailable:
        raise DecisionAuthorityUnavailable
    return locked_read(order.path, OrderPort, order.contract)


def decision_view(record, before, closure, cut):
    """Classify only the order evidence available at the decision cut."""
    require(closure == order_binding(record, {k: v for k, v in closure.items()
                                               if k in ROLLED_BACK}), "CLOSURE_BINDING")
    state = cut["snapshot"]
    reason = None if cut["status"] == "READ" else "FIXTURE_AUTHORITY_UNAVAILABLE"
    require(cut == order_binding(record, {"snapshot": state, "status": cut["status"], "reason": reason}),
            "EVIDENCE_BINDING")
    finding = "UNRESOLVED"
    trusted = None
    rollback_proof = None
    if cut["status"] == "READ":
        contract = record["candidates"][0]
        verify_snapshot(state, "order", contract["execution"]["operation_id"])
        order_result = readback(contract, before, state, record)
        if order_result["outcome"]["contract_outcome"] == SUCCESS:
            finding = "REFUND_VERIFIED"
            trusted = order_result["feedback"]
        elif canonical(before) == canonical(state) and closure == order_binding(record, ROLLED_BACK):
            finding = "ROLLED_BACK_NO_EFFECT"
            rollback_proof = closure
    else:
        require(cut["status"] == "UNAVAILABLE" and state is None, "DECISION_READBACK_STATUS")
    view = {
        "task": TASK, "timeout": SIGNAL, "fault": FAULT | {"agent_exposed": True},
        "decision_readback": cut, "finding": finding, "rollback_proof": rollback_proof,
        "reference_observation": observation(record, 2, trusted),
    }
    return view


def proposal_for(view, action):
    cut = view["decision_readback"]
    return {"action": action, "session_id": cut["session_id"], "operation_id": cut["operation_id"],
            "observation_sha256": digest(view)}


def reference_proposal(view):
    action = ACTIONS[view["finding"]]
    if action == APPLY:
        require(AgentPolicy().propose(view["reference_observation"]) is not None, "REFERENCE_INTENT")
    return proposal_for(view, action)


def adjudicate(gate, proposal, view, candidates):
    action = proposal["action"]
    require(action in ACTIONS.values() and proposal == proposal_for(view, action), "PROPOSAL_BINDING")
    finding = view["finding"]
    if action == APPLY:
        observed = view["reference_observation"]
        trusted = observed["feedback"]
        intent = tool_intent(candidates[1], 2, digest(observed), trusted["sha256"] if trusted else None)
        gate.unknown = finding == "UNRESOLVED"
        return {"verdict": gate.admit(intent, observed, trusted, candidates), "intent": intent}
    if action == NO_EFFECT:
        verdict = "NO_EFFECT_REPORTED" if finding == "ROLLED_BACK_NO_EFFECT" else "NO_EFFECT_EVIDENCE_REQUIRED"
    else:
        verdict = "HUMAN_REVIEW_NO_RETRY"
    return {"verdict": verdict, "intent": None}


def run_cell(folder, manifest, cell, framework):
    folder.mkdir(exist_ok=False)
    record = case_record(manifest, cell)
    order_contract, ops_contract = record["candidates"]
    order = OrderPort(_plain(folder / "order.sqlite"), order_contract)
    ops = OpsPort(_plain(folder / "ops.sqlite"), ops_contract)
    case = cell["case"]
    gate = ControllerGate()

    with _plain(folder / "events.jsonl").open("xb") as journal:
        def emit(kind, origin, value):
            append(record, kind, origin, value)
            journal.write(canonical(record["events"][-1]) + b"\n")
            journal.flush()
            os.fsync(journal.fileno())

        emit("SESSION_STARTED", "controller", {"run_id": manifest["run_id"], **cell, "planned": FAULT["planned"]})
        before = locked_read(order.path, OrderPort, order_contract)
        first_view = observation(record, 1, None)
        first = AgentPolicy().propose(first_view)
        require(gate.admit(first, first_view, None, record["candidates"]) == "APPROVED", "ORDER_NOT_ADMITTED")
        emit("REFUND_INTENT", "controller", {"intent": first, "before": before})
        try:
            if case == "B":
                transaction = rollback_refund(order)
                require(transaction == ROLLED_BACK, "ROLLBACK_CLOSURE")
            else:
                order.write_once()
                transaction = COMMITTED
            closure = order_binding(record, transaction)
            emit("EXECUTOR_CLOSED", "executor", closure)
            # A single response is suppressed at the host boundary for every case.
            raise ResponseLost
        except ResponseLost:
            emit("TOOL_TIMEOUT", "tool", {"signal": SIGNAL, "fault": FAULT})
        try:
            snapshot = decision_snapshot(order, simulate_unavailable=case == "C")
        except DecisionAuthorityUnavailable:
            cut = order_binding(record, {"status": "UNAVAILABLE", "snapshot": None,
                                         "reason": "FIXTURE_AUTHORITY_UNAVAILABLE"})
        else:
            cut = order_binding(record, {"status": "READ", "snapshot": snapshot, "reason": None})
        emit("DECISION_READBACK", "authority", cut)
        view = decision_view(record, before, closure, cut)
        emit("AGENT_OBSERVATION", "agent", view)

        trace = None
        if framework is None:
            proposal = reference_proposal(view)
        else:
            action = ACTIONS[view["finding"]] if cell["policy"] == FOLLOW else APPLY
            trace = framework.propose(view, proposal_for(view, action))
            proposal = trace["tool_receipt"]["proposal"]
        emit("PROPOSAL", "agent", {"proposal": proposal, "framework": trace})
        decision = adjudicate(gate, proposal, view, record["candidates"])
        emit("CONTROLLER_VERDICT", "controller", decision)
        if decision["verdict"] == "APPROVED":
            ops.write_once()
        emit("SESSION_CLOSED", "controller", {"configuration_attempts": int(decision["verdict"] == "APPROVED"),
                                             "refund_attempts": 1, "retry_attempts": 0})


EVENT_ORDER = (
    ("SESSION_STARTED", "controller"), ("REFUND_INTENT", "controller"), ("EXECUTOR_CLOSED", "executor"),
    ("TOOL_TIMEOUT", "tool"), ("DECISION_READBACK", "authority"), ("AGENT_OBSERVATION", "agent"),
    ("PROPOSAL", "agent"), ("CONTROLLER_VERDICT", "controller"), ("SESSION_CLOSED", "controller"),
)


def verify_cell(folder, manifest, cell):
    record = case_record(manifest, cell)
    raw = _read(folder / "events.jsonl")
    events = [strict(line) for line in raw.splitlines()]
    require(len(events) == len(EVENT_ORDER), "EVENT_COUNT")
    for event, (kind, origin) in zip(events, EVENT_ORDER, strict=True):
        append(record, kind, origin, event["data"])
        require(record["events"][-1] == event, "EVENT_CHAIN")
    start, refund, closure, timeout, cut, observed, intent, verdict, end = [e["data"] for e in events]

    require(start == {"run_id": manifest["run_id"], **cell, "planned": True}, "CELL_BINDING")
    require(timeout == {"signal": SIGNAL, "fault": FAULT}, "TOOL_SIGNAL")
    candidates = record["candidates"]
    order_contract, ops_contract = candidates
    order = OrderPort(folder / "order.sqlite", order_contract, readonly=True)
    ops = OpsPort(folder / "ops.sqlite", ops_contract, readonly=True)
    before = initial(order)
    gate = ControllerGate()
    first_view = observation(record, 1, None)
    first = AgentPolicy().propose(first_view)
    require(refund == {"before": before, "intent": first}
            and gate.admit(first, first_view, None, candidates) == "APPROVED", "REFUND_INTENT")
    case = cell["case"]
    # Validate the executor fact separately from receipt count, especially the rollback row.
    require(canonical(closure) == canonical(order_binding(record, ROLLED_BACK if case == "B" else COMMITTED)),
            "EXECUTOR_CLOSURE")
    require((cut["status"] == "UNAVAILABLE") == (case == "C"), "DECISION_READBACK_REQUIRED")
    view = decision_view(record, before, closure, cut)
    require(canonical(view) == canonical(observed), "OBSERVATION_BINDING")
    action = APPLY if cell["policy"] == SEQUENCE else ACTIONS[view["finding"]]
    expected = proposal_for(view, action)
    require(intent["proposal"] == expected, "PROPOSAL_BINDING")
    framework = intent["framework"]
    if manifest["engine"] == "openjiuwen":
        timeout_jiuwen.verify_trace(framework, view, expected)
    else:
        require(framework is None, "REFERENCE_FRAMEWORK_TRACE")
    decision = adjudicate(gate, intent["proposal"], view, candidates)
    require(verdict == decision, "CONTROLLER_VERDICT")
    approved = int(decision["verdict"] == "APPROVED")
    require(end == {"configuration_attempts": approved, "refund_attempts": 1, "retry_attempts": 0},
            "EXECUTION_CAP")

    order_after = locked_read(order.path, OrderPort, order_contract)
    ops_after = locked_read(ops.path, OpsPort, ops_contract)
    if cut["status"] == "READ":
        require(canonical(cut["snapshot"]) == canonical(order_after), "DECISION_SNAPSHOT_MISMATCH")
    verified = []
    for port, contract, snapshot in ((order, order_contract, order_after), (ops, ops_contract, ops_after)):
        verify_snapshot(snapshot, contract["candidate"], contract["execution"]["operation_id"])
        if snapshot["receipts"]:
            require(readback(contract, initial(port), snapshot, record)["outcome"]["contract_outcome"] == SUCCESS,
                    "BUSINESS_EFFECT_MISMATCH")
        else:
            require(canonical(snapshot) == canonical(initial(port)), "BUSINESS_STATE_MISMATCH")
        verified.append(len(snapshot["receipts"]))
    finding, follow, sequence, follow_counts, sequence_counts = CASES[case]
    expected_verdict, counts = (sequence, sequence_counts) if cell["policy"] == SEQUENCE else (follow, follow_counts)
    require((view["finding"], decision["verdict"], tuple(verified)) == (finding, expected_verdict, counts),
            "CASE_EXPECTATION")
    return {
        **cell, "decision": view, "proposal": intent["proposal"], "framework": framework, "controller": decision,
        "operations": {c["candidate"]: c["execution"] for c in candidates},
        "after": {"phase": "AFTER_SESSION_CLOSED", "order": order_after, "ops": ops_after},
        "receipt_counts": {"order": verified[0], "ops": verified[1]}, "refund_attempts": 1, "retry_attempts": 0,
        "events_sha256": sha256(raw).hexdigest(),
    }


def cell_keys(engine):
    require(engine in {"reference", "openjiuwen"}, "ENGINE")
    policies = (FOLLOW, SEQUENCE) if engine == "openjiuwen" else (FOLLOW,)
    return [(case, policy) for policy in policies for case in CASES]


def result(output, manifest):
    require(manifest["schema"] == SCHEMA and manifest["source"] == runtime_source()
            and SESSION.fullmatch(manifest["run_id"]), "SUITE_OR_SOURCE_MISMATCH")
    engine = manifest["engine"]
    cells = manifest["cells"]
    require([(cell["case"], cell["policy"]) for cell in cells] == cell_keys(engine), "CASE_SET")
    sessions = [cell["session_id"] for cell in cells]
    require(all(SESSION.fullmatch(session) for session in sessions) and len(set(sessions)) == len(sessions),
            "DUPLICATE_OR_INVALID_SESSION")
    require({p.name for p in _plain(output / "cells").iterdir()} == {f"{c}-{p}" for c, p in cell_keys(engine)}, "CASE_DIRS")
    timeout_jiuwen.verify_environment(manifest["runtime"]["sdk"], engine)
    require(type(manifest["provider_requests"]) is int and manifest["provider_requests"] == 0, "PROVIDER_SCOPE")
    audit = None
    if engine == "openjiuwen":
        audit = strict(_read(output / "framework" / "audit.json"))
        require(set(audit) == {"provider_requests", "blocked_network_or_process_events", "blocked_local_ipv6_probes"}
                and type(audit["provider_requests"]) is int and audit["provider_requests"] == 0
                and audit["blocked_network_or_process_events"] == []
                and type(audit["blocked_local_ipv6_probes"]) is int and audit["blocked_local_ipv6_probes"] >= 0,
                "FRAMEWORK_OFFLINE_AUDIT")
    rows = [verify_cell(_plain(output / "cells" / f"{c['case']}-{c['policy']}"), manifest, c) for c in cells]
    body = {"schema": SCHEMA, "issuer": "NOT_ESTABLISHED", "run_id": manifest["run_id"], "engine": engine,
            "manifest_sha256": digest(manifest), "provider_requests": 0, "framework_offline_audit": audit,
            "task": TASK, "signal": SIGNAL,
            "sessions": len(rows), "refused_config_proposals": sum(
                row["proposal"]["action"] == APPLY and row["controller"]["verdict"] != "APPROVED" for row in rows
            ), "cases": rows}
    return body | {"report_sha256": digest(body)}


def run_suite(output, engine="reference"):
    output = scope(output)
    require(not output.exists(), "OUTPUT_EXISTS")
    keys = cell_keys(engine)
    sdk = timeout_jiuwen.environment() if engine == "openjiuwen" else None
    output.mkdir(parents=True, exist_ok=False)
    (output / "cells").mkdir()
    manifest = {
        "schema": SCHEMA, "run_id": uuid4().hex, "source": runtime_source(), "engine": engine,
        "provider_requests": 0,
        "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                    "platform": platform.platform(), "sdk": sdk},
        "cells": [{"case": case, "policy": policy, "session_id": uuid4().hex} for case, policy in keys],
    }
    write_json(output / "manifest.json", manifest)
    driver = timeout_jiuwen.driver(output / "framework") if sdk else nullcontext()
    with driver as framework:
        for cell in manifest["cells"]:
            run_cell(output / "cells" / f"{cell['case']}-{cell['policy']}", manifest, cell, framework)
    report = result(output, manifest)
    write_json(output / "report.json", report)
    return report


def verify_suite(output):
    output = scope(output)
    manifest = strict(_read(output / "manifest.json"))
    report = result(output, manifest)
    require(_read(output / "report.json") == canonical(report), "EXPORT_MISMATCH")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="execute fresh owned synthetic sessions")
    run.add_argument("output", type=Path)
    run.add_argument("--engine", choices=("reference", "openjiuwen"), default="reference")
    sub.add_parser("verify", help="read-only recheck of an existing run").add_argument("output", type=Path)
    demo = sub.add_parser("demo", help="render an existing verified run as standalone HTML")
    demo.add_argument("output", type=Path)
    demo.add_argument("--html", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "run":
            report = run_suite(args.output, args.engine)
        else:
            report = verify_suite(args.output)
            if args.command == "demo":
                from .timeout_demo import render

                target = scope(args.html)
                require(target.suffix == ".html" and not target.is_relative_to(scope(args.output)), "DEMO_OUTPUT_SCOPE")
                _write(target, render(report).encode("utf-8"))
        payload = {key: report[key] for key in ("run_id", "engine", "sessions", "provider_requests",
                                                "refused_config_proposals", "report_sha256")}
        print(canonical({"status": "SIMULATION_RUN" if args.command == "run" else "READ_ONLY_REPLAY", **payload}).decode())
        return 0
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError, AttributeError, RecursionError) as exc:
        print(canonical({"status": "REJECTED", "reason": str(exc)}).decode())
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
