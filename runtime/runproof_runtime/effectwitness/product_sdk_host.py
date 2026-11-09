"""Single-writer Host barrier with append-only evidence and no effect replay."""
import os
import threading
import time
from contextlib import contextmanager

from .product_sdk_contracts import (DOMAINS, FORWARDS, POSTS, SUCCESS, binding, call, feedback, flags,
                                    reconciliation, response, select_ops, tool_value, validate_frozen, validate_readback,
                                    validate_request)
from .product_sdk_target import safe
from .sdk_presend_contracts import Denied, canonical, check, sha, strict, sync_dir

EFFECT_EVENTS = frozenset({"PROVIDER_RESERVE", "SEND_BEGIN", "SEND_ENTRY", "SEND_RETURN",
                           "WRITE_INTENT", "WRITE_COMMIT"})
MAX_WAL = 131072


class Journal:
    def __init__(self, persist):
        self.persist = persist
        self.rows = []
        self.latched = False
        self.poison = False

    def admit(self):
        check(not self.poison and not self.latched, "UNKNOWN_OR_UNCERTAIN")

    def append(self, kind, body):
        check(not self.poison and len(self.rows) < 80, "JOURNAL_CLOSED")
        if kind in EFFECT_EVENTS:
            self.admit()
        prev = self.rows[-1]["sha256"] if self.rows else "0" * 64
        content = {"seq": len(self.rows), "prev": prev, "kind": kind, "body": body, "time_ns": time.monotonic_ns()}
        row = {**content, "sha256": sha(canonical(content))}
        raw = canonical(row) + b"\n"
        try:
            self.persist(raw)
        except BaseException:
            self.poison = True
            raise
        self.rows.append(row)
        if kind == "UNKNOWN_OBSERVED":
            self.latched = True
        return row


@contextmanager
def new_journal(path):
    path = safe(path, absent=True)
    with path.open("xb") as stream:
        sync_dir(path.parent)
        size = 0

        def persist(raw):
            nonlocal size
            check(size + len(raw) <= MAX_WAL, "WAL_LIMIT")
            check(stream.write(raw) == len(raw), "WAL_SHORT_WRITE")
            stream.flush()
            os.fsync(stream.fileno())
            size += len(raw)

        yield Journal(persist)


class Session:
    def __init__(self, frozen, journal, target, authority, transfer, store):
        self.frozen = validate_frozen(frozen)
        self.case = frozen["case"]
        self.journal = journal
        self.target, self.authority, self.transfer, self.store = target, authority, transfer, store
        self.lock = threading.RLock()
        self.posts = 0
        self.forwarded = 0
        self.tools = []
        self.verified = {}
        self.pending = None
        self.failure = None
        journal.append("CASE_OPEN", {"contract_sha256": sha(canonical(self.frozen))})

    def reserve(self, domain, role, request):
        with self.lock:
            self.journal.admit()
            check(domain in DOMAINS and role == "TARGET" and self.forwarded < FORWARDS[self.case]
                  and request["number"] == self.posts == self.forwarded + 1, "RESERVATION_SCOPE")
            self.forwarded += 1
            ticket = {"request": request, "domain": domain, "role": role,
                      "case_sha256": self.journal.rows[0]["body"]["contract_sha256"]}
            self.journal.append("PROVIDER_RESERVE", ticket)
            return ticket

    def admit_write(self, domain, identity):
        with self.lock:
            self.journal.admit()
            check(domain == self.pending and identity == binding(self.frozen, domain)
                  and domain not in self.verified and self.posts == self.forwarded == len(self.tools) + 1,
                  "WRITE_SCOPE")
            if domain == "ops":
                check(select_ops(self.frozen, self.verified.get("order"), latched=self.journal.latched)
                      == "SELECT_OPS", "OPS_FEEDBACK")

    def check_unknown_denials(self, identity):
        checks = []
        for domain in DOMAINS:
            for role in ("TARGET", "EXPLORER"):
                checks.append((f"reserve_{domain}_{role}",
                               lambda d=domain, r=role: self.reserve(d, r, {"number": self.posts})))
        for name, domain, claimed in (("retry_order", "order", identity), ("cross_domain_write", "ops", identity),
                                      ("forged_owner", "order", {**identity, "owner": "f" * 32}),
                                      ("forged_contract", "order", {**identity, "contract_sha256": "f" * 64})):
            checks.append((name, lambda d=domain, b=claimed: self.admit_write(d, b)))
        for name, action in checks:
            try:
                action()
            except Denied as exc:
                check(str(exc) == "UNKNOWN_OR_UNCERTAIN", "UNKNOWN_WRONG_DENIAL")
            else:
                raise Denied("UNKNOWN_ADMITTED")
            self.journal.append("NEGATIVE_DENIAL", {"attempt": name})

    def do_tool(self, raw):
        domain = self.pending
        check(domain in self.frozen["contracts"], "NO_PENDING_TOOL")
        expected = call(self.frozen, domain)
        check(strict(raw) == {"name": expected["function"]["name"], "call_id": expected["id"]}, "CALL_SCOPE")
        identity = binding(self.frozen, domain)
        self.admit_write(domain, identity)
        self.journal.append("TOOL_ACCEPTED", identity)
        self.target.prepare(domain, identity)
        before = validate_readback(self.frozen, domain, self.authority(domain))
        check(before["snapshot"]["receipts"] == [], "AUTHORITY_BEFORE")
        self.journal.append("AUTHORITY_BEFORE", before)
        self.journal.append("WRITE_INTENT", identity)
        self.target.write_once(domain, identity)
        self.journal.append("WRITE_COMMIT", identity)
        lost = self.case == "UNKNOWN"
        if lost:
            self.journal.append("UNKNOWN_OBSERVED", identity)
        try:
            after = self.authority(domain)
            fault = flags(self.frozen["contracts"][domain], triggered=lost, observed=lost)
            verified = feedback(self.frozen, domain, before, after, fault)
        except Exception:
            if lost:
                self.journal.append("READ_ONLY_RECONCILIATION", {"binding": identity, "outcome": "UNAVAILABLE"})
            raise
        self.journal.append("AUTHORITY_AFTER", after)
        if lost:
            outcome = reconciliation(self.frozen, before, after, verified)
            self.journal.append("READ_ONLY_RECONCILIATION", {"binding": identity, "outcome": outcome})
        check(verified["value"]["outcome"] == SUCCESS, "AUTHORITY_EFFECT")
        self.journal.append("VERIFIED_FEEDBACK", verified)
        if lost:
            self.check_unknown_denials(identity)
        self.verified[domain] = verified
        self.pending = None
        value = tool_value(domain, None if lost else verified)
        self.tools.append((domain, value))
        self.journal.append("TOOL_RETURN_TO_SDK", {"domain": domain, "value": value})
        return 200, value

    def do_post(self, raw):
        check(self.posts < POSTS[self.case] and self.pending is None, "POST_BUDGET_OR_ORDER")
        request = validate_request(self.frozen, raw, self.tools)
        check(request["number"] == self.posts + 1, "POST_ORDER")
        self.store(f"sdk-post-{request['number']}.raw", raw)
        self.posts += 1
        self.journal.append("SDK_POST_RECEIVED", request)
        if self.journal.latched:
            check(self.case == "UNKNOWN" and self.posts == 2, "UNKNOWN_POST")
            self.journal.append("DENY", {"number": self.posts, "reason": "UNKNOWN_DURABLE",
                                         "sdk_echoed_unknown": True})
            return 409, {"error": {"message": "UNKNOWN_DURABLE", "type": "local_admission_denied",
                                   "code": "UNKNOWN_DURABLE"}}
        domain = "order" if self.posts == 1 else "ops"
        if self.posts == 2:
            decision = select_ops(self.frozen, self.verified.get("order"), latched=self.journal.latched)
            check(decision == "SELECT_OPS", "OPS_FEEDBACK")
            self.journal.append("POLICY_DECISION", {"decision": decision,
                                                   "feedback_sha256": self.verified["order"]["sha256"],
                                                   "policy": self.frozen["policy"]})
        ticket = self.reserve(domain, "TARGET", request)
        self.journal.append("SEND_BEGIN", ticket)
        self.transfer(ticket, raw, lambda: self.journal.append("SEND_ENTRY", ticket))
        self.journal.append("SEND_RETURN", ticket)
        scripted = response(self.frozen, self.posts)
        self.journal.append("SCRIPTED_RESPONSE", {"number": self.posts, "sha256": sha(canonical(scripted))})
        if self.posts < 3:
            self.pending = domain
        return 200, scripted

    def handle(self, path, raw):
        with self.lock:
            check(not self.journal.poison, "HOST_POISON")
            try:
                if path == "/tool":
                    return self.do_tool(raw)
                check(path == "/v1/chat/completions", "ROUTE")
                return self.do_post(raw)
            except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
                self.journal.poison = True
                raise
            except Exception:
                self.journal.poison = True
                raise Denied("HOST_OPERATION_FAILED") from None
            except BaseException:
                self.journal.poison = True
                raise
