"""Read a retained Reference Agent run without opening either target for writing."""
import sqlite3

from .competition_agent import MODE
from .competition_agent_session import append, sources
from .product_local_contracts import REQUEST, SESSION, canonical, digest, frozen
from .product_local_ports import OrderPort, OpsPort
from .product_local_session import safe_path

SCHEMA = "runproof-agent-investigation/v1"
READ_ERRORS = {"TARGET_ABSENT", "TARGET_UNREADABLE", "AUTHORITY_IDENTITY_MISMATCH",
               "AUTHORITY_OPERATION", "AUTHORITY_STATE"}


def summarize(record, readings):
    domains = []
    events = record["events"]
    for contract, port_type, reading in zip(record["candidates"], (OrderPort, OpsPort), readings, strict=True):
        operation = contract["effect"]["operation_id"]
        environment = contract["execution"]["environment_id"]
        if (reading["operation"], reading["environment"]) != (operation, environment):
            raise ValueError("READBACK_BINDING")
        intent = next((e["data"] for e in events if e["kind"] == "WRITE_INTENT"
                       and e["data"]["action_id"] == operation), None)
        before = intent.get("before") if intent else None
        port = port_type(None, contract, readonly=True)
        after = reading["snapshot"]
        if reading["error"] is not None:
            if reading["error"] not in READ_ERRORS or after is not None:
                raise ValueError("READBACK_ERROR")
            effect = "UNCONFIRMED"
        elif canonical(after) == canonical({port.key: port.updated(), "receipts": [port.receipt()]}):
            effect = "COMMITTED"
        elif canonical(after) == canonical({port.key: port.initial(), "receipts": []}):
            effect = "NO_EFFECT_OBSERVED"
        else:
            effect = "STATE_RECEIPT_MISMATCH"
        observed = any(e["kind"] == "UNKNOWN_OBSERVED" and e["data"]["action_id"] == operation for e in events)
        domains.append({"domain": contract["candidate"], "operation": operation, "effect": effect,
                        "write_intent": intent is not None, "before": before,
                        "gaps": ([reading["error"]] if reading["error"] else [])
                                + ([] if before is not None else ["NO_PERSISTED_BEFORE"])
                                + (["EFFECT_EVIDENCE_INCOMPLETE"] if effect == "STATE_RECEIPT_MISMATCH" else []),
                        "fault": {"planned": contract["candidate"] == "order", "triggered": observed,
                                  "observed": observed, "agent_exposed": False}})
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
                reading["snapshot"] = port_type(path, contract, readonly=True).read()
            else:
                reading["error"] = "TARGET_ABSENT"
        except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
            reading["error"] = str(exc) if str(exc) in READ_ERRORS else "TARGET_UNREADABLE"
        readings.append(reading)
    body = {"schema": SCHEMA, "issuer": "NOT_ESTABLISHED", "session": record, "readings": readings,
            "summary": summarize(record, readings)}
    return body | {"content_sha256": digest(body)}


def verify_report(report, actual, anchor):
    record = report["session"]
    ident = record["session_id"]
    if (report.get("issuer") != "NOT_ESTABLISHED" or record["source"] != sources()
            or record["mode"] != MODE or not SESSION.fullmatch(ident)
            or not SESSION.fullmatch(record["owner_id"]) or not REQUEST.fullmatch(record["request_id"])
            or record["provider_reservations"] != 0 or record["candidates"] != frozen(ident)
            or record["status"] not in {"STOPPED", "RUNNING", "RECONCILE_REQUIRED", "COMPLETED"}
            or not record["events"]):
        raise ValueError("INVESTIGATION_BINDING")
    chain = {"session_id": ident, "events": []}
    approved = {}
    writes = set()
    intent = None
    for event in record["events"]:
        data, kind = event["data"], event["kind"]
        append(chain, kind, event["origin"], data)
        if canonical(chain["events"][-1]) != canonical(event):
            raise ValueError("EVENT_CHAIN")
        if kind == "AGENT_INTENT":
            intent = data["intent"]
        if kind == "GATE_DECISION" and data["verdict"] == "APPROVED":
            contract = record["candidates"][data["step"] - 1]
            if (not isinstance(intent, dict) or intent["candidate_id"] != contract["candidate"] or intent["contract_sha256"] != contract["sha256"]
                    or intent["action_id"] != contract["effect"]["operation_id"]):
                raise ValueError("INTENT_BINDING")
            approved[intent["action_id"]] = contract["sha256"]
        if kind == "WRITE_INTENT":
            if data["action_id"] in writes or approved.get(data["action_id"]) != data["contract_sha256"]:
                raise ValueError("WRITE_BINDING")
            writes.add(data["action_id"])
        if kind in {"UNKNOWN_OBSERVED", "OPS_EFFECT"} and data["action_id"] not in writes:
            raise ValueError("TOOL_BINDING")
    if record["events"][0]["data"] != {"source_sha256": digest(record["source"]),
                                         "owner_id": record["owner_id"], "request_id": record["request_id"]}:
        raise ValueError("SOURCE_BINDING")
    last = record["events"][-1]
    if (record["status"] in {"STOPPED", "RECONCILE_REQUIRED"} and last["kind"] != "EXECUTION_STOPPED"
            or record["status"] == "COMPLETED" and last["kind"] != "WITNESS_FROZEN"):
        raise ValueError("STATUS_BINDING")
    if record["status"] == "COMPLETED":
        from .competition_agent_session import SCHEMA as witness_schema
        from .competition_agent_verify import verify
        verify(canonical({"schema": witness_schema, "issuer": "NOT_ESTABLISHED", "session": record}))
    body = {k: report[k] for k in ("schema", "issuer", "session", "readings", "summary")}
    if (report != body | {"content_sha256": digest(body)}
            or canonical(body["summary"]) != canonical(summarize(record, report["readings"]))):
        raise ValueError("INVESTIGATION_CONTENT")
    return {"status": "VERIFIED_ANCHORED" if anchor else "CONTENT_CHECKED_LOCAL", "sha256": actual,
            "issuer": report["issuer"], "session_id": ident, "assessment": body["summary"]}
