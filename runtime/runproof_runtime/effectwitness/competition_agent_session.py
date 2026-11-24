"""Durable single-session controller for the offline Agent."""
from datetime import datetime, timezone
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sqlite3
from uuid import uuid4

from .competition_agent import AgentPolicy, INVARIANTS, LIMITS, MODE, PROFILE, TOOLS, attestation_matches, tool_intent
from .product_local_contracts import REQUEST, SUCCESS, canonical, digest, fault_flags, feedback, frozen, outcome, source_identity, strict
from .product_local_ports import OpsPort, OrderPort
from .product_local_session import Conflict, Product, ResponseLost, safe_path

SCHEMA = "runproof-competition-agent-witness/v2"
SOURCES = ("competition_agent.py", "competition_agent_session.py", "competition_agent_gateway.py",
           "competition_agent_verify.py", "competition_agent_investigation.py")


def sources():
    folder = Path(__file__).parent
    files = [folder / name for name in SOURCES] + [folder.parent / "models.py"]
    return source_identity() | {p.name: sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in files}


def append(record, kind, origin, data):
    events = record["events"]
    item = {"seq": len(events) + 1, "kind": kind, "origin": origin, "data": data,
            "session_id": record["session_id"], "parent_sha256": events[-1]["sha256"] if events else None}
    events.append(item | {"sha256": digest(item)})


def observation(record, step, trusted):
    return {"step": step, "session_id": record["session_id"], "candidates": record["candidates"],
            "source_sha256": digest(record["source"]), "tool_allowlist": list(TOOLS.values()),
            "available": ["order", "ops"] if step == 1 else ["ops"], "feedback": trusted,
            "remaining_writes": 3 - step, "provider_reservations": 0}


def readback(contract, before, after, record):
    domain = contract["candidate"]
    result = outcome(contract, before, after)
    flags = fault_flags(domain) | {"agent_exposed": False}
    value = feedback(contract, result, flags, before, after) | {
        "session_id": record["session_id"], "source_sha256": digest(record["source"]),
    }
    return {"domain": domain, "tool_status": "UNKNOWN_OUTCOME" if domain == "order" else "RETURNED",
            "before": before, "after": after, "fault": flags, "outcome": result,
            "feedback": {"value": value, "sha256": digest(value)}}


class ControllerGate:
    def __init__(self):
        self.spent = set()
        self.unknown = False

    def admit(self, proposal, observed, trusted, candidates):
        step = observed["step"]
        if type(step) is not int or step not in (1, 2):
            return "INTENT_REJECTED"
        domain = "order" if step == 1 else "ops"
        candidate = candidates[step - 1]
        if self.unknown:
            return "UNKNOWN_PENDING"
        if isinstance(proposal, dict) and proposal.get("candidate_id") in self.spent:
            return "DUPLICATE_WRITE"
        if step == 2 and (self.spent != {"order"} or not attestation_matches(
                trusted, candidates[0], observed["session_id"], observed["source_sha256"])):
            return "VERIFIED_FEEDBACK_REQUIRED"
        if step == 2 and canonical(observed.get("feedback")) != canonical(trusted):
            return "FEEDBACK_INPUT_BINDING"
        expected = tool_intent(candidate, step, digest(observed), trusted["sha256"] if trusted else None)
        if (not isinstance(proposal, dict) or canonical(proposal) != canonical(expected)
                or expected["tool"] not in observed["tool_allowlist"] or domain not in observed["available"]
                or candidate["execution"]["target"] != "OWNED_SQLITE"):
            return "INTENT_REJECTED"
        self.spent.add(domain)
        return "APPROVED"


class AgentProduct(Product):
    def __init__(self, owner, *, policy=None, feedback_view=None):
        super().__init__(owner)
        self.source = sources()
        self.policy = policy or AgentPolicy()
        self.feedback_view = feedback_view or (lambda value: value)

    family = "reference-agent"
    mode = MODE

    def interrupted(self, record):
        previous = record["status"]
        record["status"] = "RECONCILE_REQUIRED"
        append(record, "EXECUTION_STOPPED", "controller", {"reason": "INTERRUPTED_NO_REPLAY",
               "previous": previous, "at": datetime.now(timezone.utc).isoformat(), "source": "writer-open"})

    def capability(self):
        result = super().capability()
        version = SCHEMA
        if self.readonly and result["latest"]:
            record, witness = self.lookup("id", result["latest"])
            version = strict(witness)["schema"] if witness else ("Historical source" if record["source"] != self.source else SCHEMA)
        return result | {"mode": MODE, "remaining": int(result["remaining"] > 0 and result["latest"] is None),
                         "owner": self.owner.name, "readonly": self.readonly, "version": version,
                         "profile": PROFILE, "tools": list(TOOLS.values())}

    def investigate(self, record):
        from .competition_agent_investigation import investigate
        return investigate(self.owner, record)

    def emit(self, record, kind, origin, data):
        append(record, kind, origin, data)
        self.save(record)

    def create(self, body):
        if (type(body) is not dict or set(body) not in ({"mode", "request_id"}, {"mode", "request_id", "owner_id"}) or body["mode"] != MODE
                or not isinstance(body["request_id"], str) or not REQUEST.fullmatch(body["request_id"])):
            raise ValueError("INVALID_REQUEST")
        with self.guard:
            if not self.writable:
                raise Conflict("READ_ONLY_OWNER")
            if "owner_id" in body and body["owner_id"] != self.capability()["instance"]:
                raise Conflict("OWNER_CHANGED")
            existing, _ = self.lookup("request", body["request_id"])
            if existing:
                return existing
            if not self.capability()["remaining"]:
                raise Conflict("SESSION_NOT_ADMITTED")
            ident = uuid4().hex
            record = {"session_id": ident, "mode": MODE, "profile": PROFILE, "status": "RUNNING",
                      "source": self.source, "limits": LIMITS, "provider_reservations": 0,
                      "candidates": frozen(ident), "rounds": [], "events": [], "invariants": list(INVARIANTS)}
            record.update(owner_id=self.capability()["instance"], request_id=body["request_id"])
            append(record, "CONTRACTS_FROZEN", "controller", {
                "source_sha256": digest(self.source), "owner_id": record["owner_id"], "request_id": record["request_id"]})
            self.reserve(record, body["request_id"])
            try:
                self.run_agent(record)
            except (OSError, sqlite3.Error, ValueError, TypeError):
                record["status"] = "RECONCILE_REQUIRED"
                self.emit(record, "EXECUTION_STOPPED", "controller", {"reason": "READBACK_REQUIRED_NO_REPLAY"})
            return record

    def run_agent(self, record):
        folder = safe_path(self.owner / record["session_id"])
        folder.mkdir(exist_ok=False)
        gate = ControllerGate()
        trusted = None
        for step, contract in enumerate(record["candidates"], 1):
            domain = contract["candidate"]
            view = self.feedback_view(deepcopy(trusted)) if step == 2 else None
            observed = observation(record, step, view)
            if step == 2:
                self.emit(record, "AGENT_REPLAN", "agent", {"input_feedback_sha256": view.get("sha256") if isinstance(view, dict) else None})
            self.emit(record, "AGENT_OBSERVATION", "agent", observed)
            proposed = self.policy.propose(deepcopy(observed))
            self.emit(record, "AGENT_INTENT", "agent", {"intent": proposed})
            verdict = gate.admit(proposed, observed, trusted, record["candidates"]) if proposed is not None else "MUST_STOP"
            self.emit(record, "GATE_DECISION", "controller", {"verdict": verdict, "step": step})
            if verdict != "APPROVED":
                record["status"] = "STOPPED"
                self.emit(record, "EXECUTION_STOPPED", "controller", {"reason": verdict})
                return
            port = (OrderPort if domain == "order" else OpsPort)(safe_path(folder / (domain + ".sqlite")), contract)
            before = port.read()
            self.emit(record, "WRITE_INTENT", "controller", {"action_id": proposed["action_id"], "contract_sha256": contract["sha256"], "before": before})
            try:
                port.write_once()
                if domain == "order":
                    raise ResponseLost  # Suppress this committed local tool return at the host boundary.
            except ResponseLost:
                gate.unknown = True
                self.emit(record, "UNKNOWN_OBSERVED", "tool", {"action_id": proposed["action_id"], "status": "UNKNOWN_OUTCOME"})
            else:
                self.emit(record, "OPS_EFFECT", "tool", {"action_id": proposed["action_id"], "status": "RETURNED"})
            row = readback(contract, before, port.read(), record)
            self.emit(record, "AUTHORITY_READBACK", "authority", {"domain": domain, "after_sha256": digest(row["after"])})
            record["rounds"].append(row)
            if row["outcome"]["contract_outcome"] != SUCCESS:
                record["status"] = "RECONCILE_REQUIRED"
                self.emit(record, "EXECUTION_STOPPED", "oracle", {"reason": "EFFECT_UNCONFIRMED"})
                return
            trusted = row["feedback"]
            self.emit(record, "VERIFIED_FEEDBACK", "oracle", trusted)
            gate.unknown = False
        record["status"] = "COMPLETED"
        append(record, "WITNESS_FROZEN", "controller", {"rounds": len(record["rounds"])})
        self.save(record, canonical({"schema": SCHEMA, "issuer": "NOT_ESTABLISHED", "session": record}))
