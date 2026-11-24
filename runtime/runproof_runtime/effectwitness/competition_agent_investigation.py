"""Read a retained Reference Agent run without opening either target for writing."""
from datetime import datetime, timedelta
import re
import sqlite3

from .competition_agent import INVARIANTS, LIMITS, MODE, PROFILE
from .competition_agent_session import SCHEMA as WITNESS_SCHEMA, ControllerGate, append, observation, readback, sources
from .competition_agent_verify import verify, verify_snapshot
from .product_local_contracts import REQUEST, SESSION, SUCCESS, canonical, digest, frozen
from .product_local_ports import OrderPort, OpsPort
from .product_local_session import safe_path

SCHEMA = "runproof-agent-investigation/v2"
READ_ERRORS = {"TARGET_ABSENT", "TARGET_UNREADABLE", "AUTHORITY_IDENTITY_MISMATCH",
               "AUTHORITY_OPERATION", "AUTHORITY_STATE"}


def summarize(record, readings):
    domains = []
    events = record["events"]
    for contract, port_type, reading in zip(record["candidates"], (OrderPort, OpsPort), readings, strict=True):
        operation = contract["effect"]["operation_id"]
        environment = contract["execution"]["environment_id"]
        if (set(reading) != {"operation", "environment", "snapshot", "error"}
                or (reading["operation"], reading["environment"]) != (operation, environment)):
            raise ValueError("READBACK_BINDING")
        intent = next((e["data"] for e in events if e["kind"] == "WRITE_INTENT"
                       and e["data"]["action_id"] == operation), None)
        before = intent.get("before") if intent else None
        port = port_type(None, contract, readonly=True)
        after = reading["snapshot"]
        error = reading["error"]
        gaps = []
        if error is not None:
            if error not in READ_ERRORS or after is not None:
                raise ValueError("READBACK_ERROR")
            effect = "UNCONFIRMED"
            gaps.append(error)
        else:
            verify_snapshot(after, contract["candidate"], operation)
            if canonical(after) == canonical({port.key: port.updated(), "receipts": [port.receipt()]}):
                effect = "COMMITTED"
            elif canonical(after) == canonical({port.key: port.initial(), "receipts": []}):
                effect = "NO_EFFECT_OBSERVED"
            else:
                effect = "STATE_RECEIPT_MISMATCH"
                gaps.append("EFFECT_EVIDENCE_INCOMPLETE")
        if before is None:
            gaps.append("NO_PERSISTED_BEFORE")

        planned = contract["experiment"]["fault"] == "POST_COMMIT_RESPONSE_LOSS"
        observed = any(e["kind"] == "UNKNOWN_OBSERVED" and e["data"]["action_id"] == operation for e in events)
        # A durable intent opens the window for the write and the fault. A later receipt
        # can establish the effect, while the tool-boundary event supplies the fault evidence.
        if planned and intent is not None and not observed:
            observed = None
            gaps.append("FAULT_EVENT_NOT_PERSISTED")
        domains.append({"domain": contract["candidate"], "operation": operation, "effect": effect,
                        "write_intent": intent is not None, "before": before, "gaps": gaps,
                        "fault": {"planned": planned, "triggered": observed, "observed": observed,
                                  "agent_exposed": False}})
    return {"domains": domains, "recorded_status": record["status"],
            "next": "VERIFY_ORIGINAL_WITNESS" if record["status"] == "COMPLETED" else "MANUAL_REVIEW_NO_REPLAY",
            "task_completion": "REQUIRES_SUCCESS_WITNESS" if record["status"] == "COMPLETED" else "NOT_ESTABLISHED"}


def investigate(owner, record):
    readings = []
    for contract, port_type in zip(record["candidates"], (OrderPort, OpsPort), strict=True):
        reading = {"operation": contract["effect"]["operation_id"],
                   "environment": contract["execution"]["environment_id"], "snapshot": None, "error": None}
        try:
            path = safe_path(owner / record["session_id"] / (contract["candidate"] + ".sqlite"))
            if path.is_file():
                snapshot = port_type(path, contract, readonly=True).read()
                verify_snapshot(snapshot, contract["candidate"], reading["operation"])
                reading["snapshot"] = snapshot
            else:
                reading["error"] = "TARGET_ABSENT"
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
            reading["error"] = str(exc) if str(exc) in READ_ERRORS else "TARGET_UNREADABLE"
        readings.append(reading)
    body = {"schema": SCHEMA, "issuer": "NOT_ESTABLISHED", "session": record, "readings": readings,
            "summary": summarize(record, readings)}
    return body | {"content_sha256": digest(body)}


def _check_stop(stops, expected_stop, status):
    if expected_stop:
        origin, reason, terminal_status = expected_stop
        if stops and stops[0]["origin"] == origin and stops[0]["data"] == {"reason": reason}:
            status, stops = terminal_status, stops[1:]
        elif origin == "oracle":
            # An unconfirmed round is persisted together with its stop event.
            raise ValueError("STOP_BINDING")
    if not stops:
        return status
    if len(stops) != 1 or stops[0]["origin"] != "controller":
        raise ValueError("STOP_BINDING")
    data = stops[0]["data"]
    if data == {"reason": "READBACK_REQUIRED_NO_REPLAY"}:
        # The fallback emit can persist a prior decision or attempted freeze whose save failed.
        return "RECONCILE_REQUIRED"
    if (status == "RUNNING" and set(data) == {"reason", "previous", "at", "source"}
            and (data["reason"], data["previous"], data["source"])
            == ("INTERRUPTED_NO_REPLAY", "RUNNING", "writer-open")):
        try:
            if datetime.fromisoformat(data["at"]).utcoffset() == timedelta(0):
                return "RECONCILE_REQUIRED"
        except (TypeError, ValueError):
            pass
    raise ValueError("STOP_BINDING")


def _check_round(row, contract, record, before, authority):
    domain = contract["candidate"]
    verify_snapshot(row["after"], domain, contract["effect"]["operation_id"])
    if canonical(row["before"]) != canonical(before):
        raise ValueError("ROUND_BEFORE_BINDING")
    if authority["after_sha256"] != digest(row["after"]):
        raise ValueError("AUTHORITY_BINDING")
    expected = readback(contract, before, row["after"], record)
    if canonical(row) != canonical(expected):
        raise ValueError("ROUND_BINDING")
    return expected


def _check_trace(record):
    """Check a durable prefix with pure contracts and the in-memory admission rule."""
    events = record["events"]
    chain = {"session_id": record["session_id"], "events": []}
    for item in events:
        if type(item["data"]) is not dict:
            raise ValueError("EVENT_DATA")
        append(chain, item["kind"], item["origin"], item["data"])
        if canonical(chain["events"][-1]) != canonical(item):
            raise ValueError("EVENT_CHAIN")
    stop_index = len(events)
    while stop_index and events[stop_index - 1]["kind"] == "EXECUTION_STOPPED":
        stop_index -= 1
    if not stop_index:
        raise ValueError("EVENT_ORDER")
    cursor = iter(events[:stop_index])

    def take(kind, origin):
        item = next(cursor)
        if item["kind"] != kind:
            raise ValueError("EVENT_ORDER")
        if item["origin"] != origin:
            raise ValueError("EVENT_ORIGIN")
        return item["data"]

    if take("CONTRACTS_FROZEN", "controller") != {
        "source_sha256": digest(record["source"]), "owner_id": record["owner_id"],
        "request_id": record["request_id"],
    }:
        raise ValueError("SOURCE_BINDING")
    gate = ControllerGate()
    trusted = None
    persisted_rounds = 0
    expected_stop = None
    status = "RUNNING"
    try:
        for step, contract in enumerate(record["candidates"], 1):
            domain = contract["candidate"]
            operation = contract["effect"]["operation_id"]
            replan = take("AGENT_REPLAN", "agent") if step == 2 else None
            if replan is not None and set(replan) != {"input_feedback_sha256"}:
                raise ValueError("FEEDBACK_INPUT_BINDING")
            observed = take("AGENT_OBSERVATION", "agent")
            view = observed.get("feedback") if step == 2 else None
            if canonical(observed) != canonical(observation(record, step, view)):
                raise ValueError("OBSERVATION_BINDING")
            view_sha = view.get("sha256") if isinstance(view, dict) else None
            if replan is not None and canonical(replan) != canonical({"input_feedback_sha256": view_sha}):
                raise ValueError("FEEDBACK_INPUT_BINDING")

            intent = take("AGENT_INTENT", "agent")
            if set(intent) != {"intent"}:
                raise ValueError("INTENT_BINDING")
            proposal = intent["intent"]
            decision = take("GATE_DECISION", "controller")
            if set(decision) != {"verdict", "step"} or type(decision["step"]) is not int or decision["step"] != step:
                raise ValueError("GATE_DECISION_BINDING")
            approved = decision["verdict"] == "APPROVED"
            verdict = gate.admit(proposal, observed, trusted, record["candidates"]) if proposal is not None else "MUST_STOP"
            if decision["verdict"] != verdict:
                if approved and verdict == "FEEDBACK_INPUT_BINDING":
                    raise ValueError(verdict)
                raise ValueError("APPROVED_INTENT_CONTRACT" if approved else "GATE_DECISION_BINDING")
            if verdict != "APPROVED":
                expected_stop = ("controller", verdict, "STOPPED")
                break

            write = take("WRITE_INTENT", "controller")
            if (set(write) != {"action_id", "contract_sha256", "before"}
                    or (write["action_id"], write["contract_sha256"]) != (operation, contract["sha256"])):
                raise ValueError("WRITE_BINDING")
            before = write["before"]
            verify_snapshot(before, domain, operation)
            kind, tool_status = ("UNKNOWN_OBSERVED", "UNKNOWN_OUTCOME") if step == 1 else ("OPS_EFFECT", "RETURNED")
            if take(kind, "tool") != {"action_id": operation, "status": tool_status}:
                raise ValueError("TOOL_BINDING")
            authority = take("AUTHORITY_READBACK", "authority")
            if (set(authority) != {"domain", "after_sha256"} or authority["domain"] != domain
                    or not re.fullmatch(r"[a-f0-9]{64}", authority["after_sha256"])):
                raise ValueError("AUTHORITY_BINDING")
            if step > len(record["rounds"]):
                # Readback is saved first. The next save carries the round and its outcome.
                break
            row = _check_round(record["rounds"][step - 1], contract, record, before, authority)
            if row["outcome"]["contract_outcome"] != SUCCESS:
                persisted_rounds += 1
                expected_stop = ("oracle", "EFFECT_UNCONFIRMED", "RECONCILE_REQUIRED")
                break
            attestation = take("VERIFIED_FEEDBACK", "oracle")
            if set(attestation) != {"value", "sha256"} or digest(attestation["value"]) != attestation["sha256"]:
                raise ValueError("FEEDBACK_DIGEST")
            trusted = row["feedback"]
            if canonical(attestation) != canonical(trusted):
                raise ValueError("FEEDBACK_BINDING")
            persisted_rounds += 1
        else:
            if canonical(take("WITNESS_FROZEN", "controller")) != canonical({"rounds": persisted_rounds}):
                raise ValueError("WITNESS_BINDING")
            status = "COMPLETED"
    except StopIteration:
        pass
    if next(cursor, None) is not None:
        raise ValueError("EVENT_ORDER")
    if persisted_rounds != len(record["rounds"]):
        raise ValueError("ROUND_PERSISTENCE")
    if record["status"] != _check_stop(events[stop_index:], expected_stop, status):
        raise ValueError("STATUS_BINDING")


def verify_report(report, actual, anchor):
    body = {key: report[key] for key in ("schema", "issuer", "session", "readings", "summary")}
    if report != body | {"content_sha256": digest(body)}:
        raise ValueError("INVESTIGATION_DIGEST")
    record = body["session"]
    ident = record["session_id"]
    if record["source"] != sources():
        raise ValueError("INVESTIGATION_SOURCE_MISMATCH")
    if (body["issuer"] != "NOT_ESTABLISHED" or record["mode"] != MODE or record["profile"] != PROFILE
            or not SESSION.fullmatch(ident) or not SESSION.fullmatch(record["owner_id"])
            or not REQUEST.fullmatch(record["request_id"])
            or canonical(record["limits"]) != canonical(LIMITS)
            or record["invariants"] != list(INVARIANTS)
            or type(record["provider_reservations"]) is not int or record["provider_reservations"] != 0
            or canonical(record["candidates"]) != canonical(frozen(ident))
            or type(record["events"]) is not list or not record["events"] or type(record["rounds"]) is not list):
        raise ValueError("INVESTIGATION_BINDING")
    _check_trace(record)
    if record["status"] == "COMPLETED":
        verify(canonical({"schema": WITNESS_SCHEMA, "issuer": "NOT_ESTABLISHED", "session": record}))
    if canonical(body["summary"]) != canonical(summarize(record, body["readings"])):
        raise ValueError("INVESTIGATION_SUMMARY")
    return {"status": "VERIFIED_ANCHORED" if anchor else "CONTENT_CHECKED_LOCAL", "sha256": actual,
            "issuer": report["issuer"], "session_id": ident, "assessment": body["summary"]}
