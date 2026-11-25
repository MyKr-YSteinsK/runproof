"""One-use task authorization with a durable, replayable Provider budget."""
import os
import re
from pathlib import Path

from . import rpf119_protocol as protocol
from .policy_evaluation import AUTHORITY, _plain
from .product_local_contracts import SESSION, canonical, digest, strict
from .product_local_session import file_sha

SCHEMA = "rpf119-provider-journal/v1"
PHASES = {"SEND_ENTRY", "POST_WRITTEN", "HTTP_RESPONSE", "TERMINAL"}
ERRORS = {"TIMEOUT", "TRANSPORT_ERROR", "CANCELLED", "BODY_UNAVAILABLE"}
COMPONENTS = ("requests", "input", "output", "usd_nanodollars")
ZERO = dict.fromkeys(COMPONENTS, 0)
MAX_EVENTS = 2 + 2 * protocol.LIMITS["sessions"] + 5 * protocol.LIMITS["requests"]


def read(path, cap=65536):
    with _plain(path).open("rb") as handle:
        raw = handle.read(cap + 1)
    if len(raw) > cap:
        raise ValueError("RPF119_RECORD_SIZE")
    value = strict(raw)
    if raw != canonical(value):
        raise ValueError("RPF119_RECORD_CANONICAL")
    return value


def write(path, value):
    with _plain(path).open("xb") as handle:
        handle.write(canonical(value))
        handle.flush()
        os.fsync(handle.fileno())
    if os.name != "nt":
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def selection(manifest, case, policy):
    return {"manifest_sha256": digest(manifest), "case": case, "policy": policy,
            "owner_nonce": manifest["owners"][case][policy]}


def request_id(manifest, case, policy):
    return "rpf119-" + digest(selection(manifest, case, policy))


class Journal:
    def __init__(self, root, manifest):
        self.root = _plain(Path(root).absolute())
        self.manifest = manifest
        self.folder = self.root / "provider-journal"
        self.grant = self.root.parent / "rpf119-rev2-grant.json"
        self.claim_marker = self.root.parent / "rpf119-rev2-claimed.json"
        self.identity = {"schema": SCHEMA, "task": manifest["approval"]["revision"],
                         "run_id": manifest["run_id"], "manifest_sha256": digest(manifest),
                         "mode": manifest["transport"]}
        self.started = False

    def _provision(self):
        # Used by the task's one-time preparation and by isolated local tests.
        # Sending and verify never create a grant, a journal, or another run.
        if self.claim_marker.exists():
            raise ValueError("TASK_ALREADY_CLAIMED")
        write(self.grant, self.identity)
        self.folder.mkdir(exist_ok=False)
        write(self.folder / "0001.json", self._event([], "OPEN", self.identity | {"held": ZERO}))

    @staticmethod
    def _event(rows, kind, data):
        event = {"seq": len(rows) + 1, "kind": kind, "data": data,
                 "parent_sha256": rows[-1]["sha256"] if rows else None}
        return event | {"sha256": digest(event)}

    def snapshot(self):
        if canonical(read(self.grant)) != canonical(self.identity):
            raise ValueError("GRANT_IDENTITY")
        entries = sorted(path.name for path in _plain(self.folder).iterdir())
        if not entries or len(entries) > MAX_EVENTS or entries != [f"{i:04}.json" for i in range(1, len(entries) + 1)]:
            raise ValueError("JOURNAL_FILE_SET")
        rows = [read(self.folder / name) for name in entries]
        state = self._replay(rows)
        if state["claimed"] and canonical(read(self.claim_marker)) != canonical(self.identity):
            raise ValueError("CLAIM_IDENTITY")
        return rows, state

    def claim(self):
        rows, state = self.snapshot()
        if self.started or len(rows) != 1 or state["claimed"] or self.claim_marker.exists():
            raise ValueError("TASK_ALREADY_CLAIMED")
        write(self.claim_marker, self.identity)
        self._append("CLAIM", self.identity)
        self.started = True

    def _append(self, kind, data):
        if kind != "CLAIM" and not self.started:
            raise ValueError("REOPEN_READONLY")
        if canonical(read(self.claim_marker)) != canonical(self.identity):
            raise ValueError("CLAIM_IDENTITY")
        rows, _ = self.snapshot()
        entry = self._event(rows, kind, data)
        self._replay(rows + [entry])
        write(self.folder / f"{entry['seq']:04}.json", entry)

    def begin(self, case):
        self._append("CASE_BEGIN", selection(self.manifest, case, "DEEPSEEK"))

    def reserve(self, case, observed, order_proof):
        inputs, raw, hold = protocol.request(observed, self.manifest["currency"])
        _, state = self.snapshot()
        held = {key: state["held"][key] + hold[key] for key in COMPONENTS}
        data = {"case": case, "request": request_id(self.manifest, case, "DEEPSEEK"),
                "session": observed["session_id"], "step": observed["step"],
                "inputs": inputs, "request_sha256": file_sha(raw), "hold": hold, "held_total": held,
                "order_proof": order_proof}
        self._append("RESERVED", data)
        return raw, digest(data)

    def phase(self, ticket, kind, data):
        self._append(kind, {"ticket_sha256": ticket, "evidence": data})

    def end(self, row):
        self._append("CASE_END", row)

    def _replay(self, rows):
        held = ZERO.copy()
        claimed, blocked = False, False
        cases, attempts, checked = {}, [], []
        current = None
        response_ids = set()
        for entry in rows:
            kind, data = entry["kind"], entry["data"]
            if canonical(entry) != canonical(self._event(checked, kind, data)):
                raise ValueError("JOURNAL_CHAIN")
            if not checked:
                if kind != "OPEN" or canonical(data) != canonical(self.identity | {"held": ZERO}):
                    raise ValueError("JOURNAL_OPEN")
            elif kind == "CLAIM":
                if len(checked) != 1 or data != self.identity:
                    raise ValueError("JOURNAL_CLAIM")
                claimed = True
            elif not claimed:
                raise ValueError("JOURNAL_CLAIM")
            elif kind == "CASE_BEGIN":
                scope = self.manifest["scope"]
                if (blocked or current is not None or len(cases) >= len(scope)
                        or canonical(data) != canonical(selection(self.manifest, scope[len(cases)], "DEEPSEEK"))):
                    raise ValueError("CASE_ORDER_OR_ABORT")
                current = data["case"]
                cases[current] = {"attempts": [], "end": None}
            elif kind == "RESERVED":
                if blocked or current is None:
                    raise ValueError("RESERVATION_AFTER_STOP")
                actual = cases[current]["attempts"]
                held = self._check_reservation(data, current, actual, held)
                attempt = {"reservation": data, "ticket_sha256": digest(data), "send_entry": False,
                           "post_written": False, "http_response": None, "terminal": None}
                actual.append(attempt)
                attempts.append(attempt)
            elif kind in PHASES:
                if current is None or not cases[current]["attempts"] or blocked:
                    raise ValueError("SEND_PHASE_AFTER_STOP")
                attempt = cases[current]["attempts"][-1]
                self._phase(attempt, kind, data)
                terminal = attempt["terminal"]
                if terminal is not None:
                    reply = terminal["reply"]
                    identity = reply.get("response_id_sha256") if reply else None
                    if identity is not None and identity in response_ids:
                        raise ValueError("RESPONSE_ID_REUSED")
                    if identity is not None:
                        response_ids.add(identity)
                    blocked = terminal["parsed"]["outcome"] != "DECISION"
            elif kind == "CASE_END":
                if (current is None or set(data) != {"case", "result_sha256", "safe_to_continue"}
                        or data["case"] != current or not protocol.HASH.fullmatch(data["result_sha256"])
                        or type(data["safe_to_continue"]) is not bool or blocked and data["safe_to_continue"]
                        or any(a["terminal"] is None for a in cases[current]["attempts"])):
                    raise ValueError("CASE_END")
                cases[current]["end"] = data
                current = None
                blocked = blocked or not data["safe_to_continue"]
            else:
                raise ValueError("JOURNAL_EVENT")
            checked.append(entry)
        return {"held": held, "cases": cases, "attempts": attempts, "blocked": blocked,
                "claimed": claimed, "active_case": current}

    def _check_reservation(self, data, case, attempts, prior):
        observed = data["inputs"]["observation"]
        inputs, raw, hold = protocol.request(observed, self.manifest["currency"])
        step = len(attempts) + 1
        session = observed["session_id"]
        proof = data["order_proof"]
        if (step > protocol.LIMITS["per_session"] or (case == AUTHORITY and step != 1)
                or not SESSION.fullmatch(session) or type(observed["step"]) is not int or observed["step"] != step
                or (step == 1 and proof is not None)
                or (step == 2 and (attempts[0]["terminal"] is None
                    or attempts[0]["reservation"]["session"] != session or type(proof) is not dict
                    or set(proof) != {"authority_feedback_sha256", "order_snapshot_sha256"}
                    or any(not protocol.HASH.fullmatch(value) for value in proof.values())))):
            raise ValueError("RESERVATION_STEP_OR_AUTHORITY")
        held = {key: prior[key] + hold[key] for key in COMPONENTS}
        expected = {"case": case, "request": request_id(self.manifest, case, "DEEPSEEK"),
                    "session": session, "step": step, "inputs": inputs, "request_sha256": file_sha(raw),
                    "hold": hold, "held_total": held, "order_proof": proof}
        if canonical(expected) != canonical(data):
            raise ValueError("RESERVATION_BINDING")
        if any(held[key] > protocol.LIMITS[key] for key in COMPONENTS):
            raise ValueError("TASK_BUDGET_EXHAUSTED")
        return held

    @staticmethod
    def _phase(attempt, kind, data):
        if attempt["terminal"] is not None or set(data) != {"ticket_sha256", "evidence"} or data["ticket_sha256"] != attempt["ticket_sha256"]:
            raise ValueError("TICKET_CONSUMED_OR_MISMATCH")
        value = data["evidence"]
        if kind == "SEND_ENTRY" and not attempt["send_entry"] and value == {}:
            attempt["send_entry"] = True
        elif kind == "POST_WRITTEN" and attempt["send_entry"] and not attempt["post_written"] and value == {}:
            attempt["post_written"] = True
        elif kind == "HTTP_RESPONSE" and attempt["post_written"] and attempt["http_response"] is None:
            if (set(value) != {"status", "header_request_id_sha256"} or type(value["status"]) is not int
                    or not 100 <= value["status"] <= 599 or value["header_request_id_sha256"] is not None
                    and not protocol.HASH.fullmatch(value["header_request_id_sha256"])):
                raise ValueError("HTTP_RESPONSE_RECEIPT")
            attempt["http_response"] = value
        elif kind == "TERMINAL" and attempt["send_entry"]:
            if canonical(value) != canonical(terminal(attempt, value["reply"], value["failure"])):
                raise ValueError("TERMINAL_REPLAY")
            attempt["terminal"] = value
        else:
            raise ValueError("SEND_PHASE_ORDER")


def terminal(attempt, reply, failure=None):
    if reply is None and failure in ERRORS:
        outcome = {"TIMEOUT": "INCONCLUSIVE", "TRANSPORT_ERROR": "INCONCLUSIVE",
                   "BODY_UNAVAILABLE": "INCONCLUSIVE", "CANCELLED": "CANCELLED"}[failure]
        parsed = protocol._stop(outcome, failure)
    elif type(reply) is dict and failure is None and attempt["http_response"] is not None:
        held = attempt["reservation"]
        parsed = protocol.interpret(reply, attempt["http_response"]["status"], held["inputs"]["observation"], held["hold"])
    else:
        raise ValueError("TERMINAL_OUTCOME")
    return {"reply": reply, "failure": failure, "parsed": parsed}
