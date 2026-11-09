"""Exclusive append-only owner ledger. Recovery is read-only."""
from copy import deepcopy
import os
import threading

from . import pge_r106_contracts as c
from .product_sdk_target import read, safe
from .sdk_presend_contracts import canonical, check, strict, sync_dir

WAL = "ledger.jsonl"
MAX_BYTES = 131072
MAX_ROWS = 32


def initial(frozen):
    return {"frozen": frozen, "phase": "NEW", "latched": False, "seen": [], "remaining": dict(c.LIMIT),
            "feedback_sha256": None, "candidate": None, "intent_sha256": None,
            "revision": 0, "tip": "0" * 64}


def view(state):
    return deepcopy({key: state[key] for key in ("phase", "latched", "seen", "remaining", "feedback_sha256",
                                                  "revision", "tip")}) | {"run_sha256": c.digest(state["frozen"])}


def transition(state, row):
    out = deepcopy(state)
    phase = state["phase"]
    kind, body = row["kind"], row["body"]
    frozen = state["frozen"]
    name = state["candidate"]
    contract = frozen["catalog"].get(name)
    if kind == "RUN_OPEN":
        check(phase == "NEW" and canonical(body) == canonical(frozen), "OPEN_BINDING")
        out["phase"] = "READY"
    elif kind == "CLAIMED":
        c.exact(body, "proposal", "decision", "remaining")
        offered, decision = body["proposal"], body["decision"]
        expected = c.gate(frozen, view(state), offered)
        check(expected["status"] == "ACCEPT" and canonical(decision) == canonical(expected), "CLAIM_CAS")
        remaining = {key: state["remaining"][key] - expected["requested_debit"][key] for key in c.LIMIT}
        check(canonical(remaining) == canonical(body["remaining"]), "CLAIM_BUDGET")
        out.update(phase="CLAIMED", candidate=offered["candidate_id"], remaining=remaining,
                   seen=[*state["seen"], offered["proposal_id"]], intent_sha256=None)
    elif kind in ("AUTHORITY_BEFORE", "AUTHORITY_AFTER"):
        expected = "CLAIMED" if kind == "AUTHORITY_BEFORE" else ("UNKNOWN" if state["latched"] else "COMMITTED")
        check(phase == expected and contract is not None and body.get("binding") == c.binding(contract),
              "AUTHORITY_PHASE")
        out["phase"] = "PREPARED" if kind == "AUTHORITY_BEFORE" else "READ_BACK"
    elif kind in ("WRITE_INTENT", "WRITE_COMMIT", "UNKNOWN"):
        expected = {"WRITE_INTENT": "PREPARED", "WRITE_COMMIT": "INTENT", "UNKNOWN": "COMMITTED"}[kind]
        check(phase == expected and not state["latched"] and contract is not None
              and canonical(body) == canonical(c.binding(contract)), "EFFECT_PHASE")
        if kind == "WRITE_INTENT":
            out.update(phase="INTENT", intent_sha256=row["sha256"])
        elif kind == "WRITE_COMMIT":
            out["phase"] = "COMMITTED"
        else:
            check(contract["experiment"]["fault"] == c.FAULT, "FAULT_NOT_PLANNED")
            out.update(phase="UNKNOWN", latched=True)
    elif kind == "VERIFIED":
        c.exact(body, "verdict", "feedback_sha256")
        verdict = body["verdict"]
        check(phase == "READ_BACK" and verdict.get("binding") == c.binding(contract)
              and verdict.get("outcome") == c.SUCCESS and verdict.get("intent_sha256") == state["intent_sha256"]
              and body["feedback_sha256"] == c.digest(verdict)
              and (state["latched"] is (name != c.SEED)), "FEEDBACK_PIN")
        out.update(phase="RECONCILED" if state["latched"] else "VERIFIED", feedback_sha256=body["feedback_sha256"])
    elif kind == "STOPPED":
        if phase == "RECONCILED":
            check(body == {"reason": "UNKNOWN_TERMINAL"}, "STOP_REASON")
        else:
            c.exact(body, "reason", "proposal", "decision")
            expected = c.gate(frozen, view(state), body["proposal"])
            check(body["reason"] == expected["reason"] == "EXPLICIT_STOP"
                  and canonical(body["decision"]) == canonical(expected), "STOP_CAS")
        out["phase"] = "STOPPED"
    else:
        raise ValueError("EVENT_KIND")
    out.update(revision=row["revision"], tip=row["sha256"])
    return out


def replay(raw):
    check(0 < len(raw) <= MAX_BYTES and raw.endswith(b"\n"), "WAL_TORN")
    rows = []
    state = None
    for line in raw.split(b"\n")[:-1]:
        row = c.exact(strict(line), "revision", "prev", "kind", "body", "sha256")
        data = {key: value for key, value in row.items() if key != "sha256"}
        check(type(row["revision"]) is int and row["revision"] == len(rows) + 1
              and row["prev"] == (rows[-1]["sha256"] if rows else "0" * 64)
              and row["sha256"] == c.digest(data) and canonical(row) == line, "WAL_CHAIN")
        if not rows:
            check(row["kind"] == "RUN_OPEN", "WAL_OPEN")
            state = initial(c.validate_frozen(row["body"]))
        state = transition(state, row)
        rows.append(row)
    check(1 <= len(rows) <= MAX_ROWS, "WAL_ROWS")
    return state, rows


class Ledger:
    def __init__(self, owner, frozen, before_append=None):
        self.path = safe(owner / WAL, absent=True)
        self.lock = threading.RLock()
        self.state = initial(frozen)
        self.poison = False
        self.closed = False
        self.before_append = before_append
        self.stream = self.path.open("xb")
        try:
            sync_dir(owner)
            self.append("RUN_OPEN", frozen)
        except BaseException:
            self.close()
            raise

    def close(self):
        with self.lock:
            if not self.closed:
                self.closed = True
                self.stream.close()

    def snapshot(self):
        with self.lock:
            current = view(self.state)
            if self.poison or self.closed:
                current.update(phase="UNCERTAIN", latched=True)
            return current

    def confirm(self):
        with self.lock:
            try:
                state, _ = self.persisted()
                check(canonical(state) == canonical(self.state), "DURABLE_REVISION_CHANGED")
            except BaseException:
                self.poison = True
                raise

    def append(self, kind, body):
        with self.lock:
            check(not self.poison and not self.closed and self.state["revision"] < MAX_ROWS, "WAL_CLOSED")
            if self.state["revision"]:
                self.confirm()
            data = {"revision": self.state["revision"] + 1, "prev": self.state["tip"], "kind": kind, "body": body}
            row = {**data, "sha256": c.digest(data)}
            next_state = transition(self.state, row)
            raw = canonical(row) + b"\n"
            try:
                if self.before_append:
                    self.before_append(kind)
                check(self.stream.tell() + len(raw) <= MAX_BYTES and self.stream.write(raw) == len(raw), "WAL_WRITE")
                self.stream.flush()
                os.fsync(self.stream.fileno())
            except BaseException:
                self.poison = True
                raise
            self.state = next_state
            return row["sha256"]

    def persisted(self):
        with self.lock:
            return replay(read(self.path, MAX_BYTES))
