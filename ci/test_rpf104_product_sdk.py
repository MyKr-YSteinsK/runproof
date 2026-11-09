"""Data-only controls for product SDK admission and independent replay."""
from copy import deepcopy
import time
import unittest

from runtime.runproof_runtime.effectwitness import product_sdk_contracts as c, product_sdk_oracle as o
from runtime.runproof_runtime.effectwitness.product_sdk_host import Journal, Session
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import PINS, canonical, sha, strict

SOURCE = "a" * 40
RUN = "1234567"
OWNER = "1" * 32


def request(frozen, tools):
    messages = [{"role": "user", "content": c.PROMPT}]
    for domain, value in tools:
        call = c.call(frozen, domain)
        messages.extend([{"role": "assistant", "tool_calls": [call]},
                         {"role": "tool", "tool_call_id": call["id"], "content": canonical(value).decode()}])
    return canonical({"model": c.MODEL, "messages": messages,
                      "tools": [{"type": "function", "function": {"name": name}} for name in c.DOMAINS.values()]})


class Fixture:
    def __init__(self, case, persist=lambda raw: None):
        self.frozen = c.freeze(SOURCE, RUN, OWNER, case)
        self.written = set()
        self.prepared = set()
        self.raw = {}
        self.transfers = []
        self.exe = "e" * 64
        self.nonce = "c" * 64
        self.host = {"pid": 1, "host": "127.0.0.1", "port": 1234, "exe_sha256": self.exe}
        self.scope = sha(canonical(self.frozen))
        now = time.monotonic_ns()
        self.ready = {"scope_sha256": self.scope, "host": "127.0.0.1", "port": 1235, "pid": 2,
                      "exe_sha256": self.exe, "nonce": self.nonce, "ready_ns": now}
        self.session = Session(self.frozen, Journal(persist), self, self.authority, self.transfer, self.raw.__setitem__)
        self.session.journal.append("HOST_LISTEN", self.host)
        self.start = time.monotonic_ns()

    def prepare(self, domain, identity):
        assert identity == c.binding(self.frozen, domain) and domain not in self.prepared
        self.prepared.add(domain)

    def write_once(self, domain, identity):
        assert identity == c.binding(self.frozen, domain) and domain in self.prepared and domain not in self.written
        self.written.add(domain)

    def authority(self, domain):
        return {"binding": c.binding(self.frozen, domain), "authority": "SQLITE_RO_QUERY_ONLY", "pid": 4,
                "snapshot": o.snapshot(self.frozen, domain, domain in self.written)}

    def transfer(self, ticket, raw, entry):
        stamp = entry()["time_ns"]
        receipt = {"sha256": sha(raw), "bytes": len(raw), "nonce": self.nonce}
        self.transfers.append({"sender": {**receipt, "pid": 1, "ticket": ticket,
                                          "entry_ns": stamp, "return_ns": time.monotonic_ns()},
                               "receiver": {**receipt, "pid": 2, "number": ticket["request"]["number"],
                                            "scope_sha256": self.scope, "received_ns": time.monotonic_ns()}})

    def post(self):
        return self.session.handle("/v1/chat/completions", request(self.frozen, self.session.tools))

    def tool(self, domain):
        row = c.call(self.frozen, domain)
        return self.session.handle("/tool", canonical({"name": row["function"]["name"], "call_id": row["id"]}))

    def complete(self):
        normal = self.frozen["case"] == "NORMAL"
        assert self.post()[0] == 200
        assert self.tool("order")[0] == 200
        assert self.post()[0] == (200 if normal else 409)
        if normal:
            assert self.tool("ops")[0] == 200 and self.post()[0] == 200
        callbacks = [{"call_id": c.call(self.frozen, domain)["id"], "name": c.DOMAINS[domain], "value": value}
                     for domain, value in self.session.tools]
        terminal = ({"status": "COMPLETED", "output_sha256": sha(c.STOP.encode()), "sdk_reported_requests": 3,
                     "sdk_reported_tool_calls": 2, "usage_kind": "SYNTHETIC_LOCAL_MODEL_RESPONSE"} if normal
                    else {"status": "DENIED_AFTER_UNKNOWN", "http_status": 409, "usage_kind": "UNAVAILABLE"})
        sdk = {"pid": 3, "exe_sha256": self.exe, "callbacks": callbacks, "terminal": terminal,
               "packages": {name: {"version": version, "source_sha256": self.exe, "record_sha256": self.exe}
                            for name, version in PINS.items()}}
        done = {"pid": 3, "exit": 0, "exit_ns": time.monotonic_ns(), "stdout_sha256": sha(canonical(sdk) + b"\n")}
        self.session.journal.append("SDK_TERMINAL", done)
        return {"schema": o.SCHEMA, "frozen": self.frozen, "wal": self.session.journal.rows, "sdk": sdk,
                "environment": {"python": "3.12.1", "exe_sha256": self.exe, "pins": PINS,
                                "wheels": dict.fromkeys(PINS, self.exe)},
                "sdk_launch": {"pid": 3, "start_ns": self.start, "host": self.host, "exe_sha256": self.exe},
                "sdk_exit": done, "receiver_ready": self.ready, "transfers": self.transfers,
                "receiver_launch": {"pid": 2, "nonce": self.nonce, "exe_sha256": self.exe,
                                    "start_ns": self.ready["ready_ns"]},
                "receiver_exit": {"pid": 2, "exit": 0, "exit_ns": time.monotonic_ns(), "exe_sha256": self.exe}}


def reanchor(witness):
    prev = "0" * 64
    for index, row in enumerate(witness["wal"]):
        row.update(seq=index, prev=prev)
        row["sha256"] = sha(canonical({key: value for key, value in row.items() if key != "sha256"}))
        prev = row["sha256"]


class ProductSDKTests(unittest.TestCase):
    def test_normal_requires_verified_non_fault_feedback(self):
        fixture = Fixture("NORMAL")
        witness = fixture.complete()
        result = o.verify_case(witness)
        self.assertEqual((result["business_writes"], result["tool_callbacks"], result["forwards"]), (2, 2, 3))
        self.assertEqual(fixture.written, {"order", "ops"})
        verified = deepcopy(fixture.session.verified["order"])
        for key, value in (("fault", dict.fromkeys(("planned", "observed", "triggered", "agent_exposed"), True)),
                           ("binding", c.binding(fixture.frozen, "ops"))):
            bad = {**verified["value"], key: value}
            self.assertEqual(c.select_ops(fixture.frozen, {"value": bad, "sha256": sha(canonical(bad))},
                                          latched=False), "MUST_STOP")
        self.assertEqual(c.select_ops(fixture.frozen, verified, latched=True), "MUST_STOP")
        self.assertEqual(c.select_ops(fixture.frozen, None, latched=False), "MUST_STOP")

    def test_unknown_reconciles_then_denies_globally(self):
        fixture = Fixture("UNKNOWN")
        result = o.verify_case(fixture.complete())
        self.assertEqual((result["business_writes"], result["sdk_posts"], result["forwards"]), (1, 2, 1))
        self.assertEqual(fixture.written, {"order"})
        self.assertTrue(all(result["effects"]["order"]["fault"].values()))
        self.assertEqual([result[k] for k in ("post_unknown_reserves", "post_unknown_sends", "post_unknown_writes")],
                         [0, 0, 0])

    def test_raw_bytes_and_receipt_tamper(self):
        fixture = Fixture("NORMAL")
        witness = fixture.complete()
        posts = list(fixture.raw.values())
        finals = {key: fixture.authority(key) for key in fixture.written}
        o.verify_case(witness, sdk_posts=posts, receiver_raw=posts, final_snapshots=finals)
        with self.assertRaisesRegex(ValueError, "RECEIVER_BYTES"):
            o.verify_case(witness, sdk_posts=posts, receiver_raw=[posts[0] + b"x", *posts[1:]],
                          final_snapshots=finals)
        for change in ("receipt", "missing_readback", "source", "sdk"):
            bad = deepcopy(witness)
            if change == "receipt":
                row = next(r for r in bad["wal"] if r["kind"] == "AUTHORITY_AFTER")
                row["body"]["snapshot"]["receipts"][0]["operation_id"] = "forged"
            elif change == "missing_readback":
                bad["wal"].pop(next(i for i, r in enumerate(bad["wal"]) if r["kind"] == "AUTHORITY_AFTER"))
            elif change == "source":
                bad["frozen"]["source_git_sha"] = "b" * 40
            else:
                bad["sdk"]["terminal"]["status"] = "FORGED"
            reanchor(bad)
            with self.assertRaises(ValueError):
                o.verify_case(bad)

    def test_unknown_reanchored_side_effects_rejected(self):
        witness = Fixture("UNKNOWN").complete()
        for kind in ("PROVIDER_RESERVE", "WRITE_INTENT", "WRITE_COMMIT", "SEND_BEGIN", "SEND_ENTRY"):
            bad = deepcopy(witness)
            bad["wal"].append({**bad["wal"][-1], "kind": kind})
            reanchor(bad)
            with self.assertRaisesRegex(ValueError, "POST_UNKNOWN_EFFECT"):
                o.verify_case(bad)

    def test_failed_persistence_does_not_enable_effects(self):
        for failure in ("WRITE_INTENT", "UNKNOWN_OBSERVED"):
            def persist(raw):
                if strict(raw)["kind"] == failure:
                    raise OSError("injected durable write failure")
            fixture = Fixture("UNKNOWN", persist=persist)
            fixture.post()
            with self.assertRaises(OSError):
                fixture.tool("order")
            self.assertEqual(fixture.written, set() if failure == "WRITE_INTENT" else {"order"})
            self.assertTrue(fixture.session.journal.poison)
            with self.assertRaisesRegex(ValueError, "HOST_POISON"):
                fixture.post()
            self.assertEqual(len(fixture.transfers), 1)

    def test_unavailable_readback_keeps_unknown_latched(self):
        fixture = Fixture("UNKNOWN")
        fixture.post()
        authority = fixture.session.authority
        def read(domain):
            if domain in fixture.written:
                raise OSError("fixture authority unavailable")
            return authority(domain)
        fixture.session.authority = read
        with self.assertRaises(OSError):
            fixture.tool("order")
        self.assertTrue(fixture.session.journal.latched)
        self.assertEqual(fixture.session.journal.rows[-1]["body"]["outcome"], "UNAVAILABLE")
        self.assertFalse(fixture.session.tools)
        with self.assertRaisesRegex(ValueError, "UNKNOWN_OR_UNCERTAIN"):
            fixture.session.reserve("ops", "TARGET", {"number": 2})

    def test_wrong_or_duplicate_call_fails_before_extra_write(self):
        fixture = Fixture("NORMAL")
        fixture.post()
        with self.assertRaisesRegex(ValueError, "CALL_SCOPE"):
            fixture.session.handle("/tool", canonical({"name": "change_config", "call_id": "wrong"}))
        self.assertEqual(fixture.written, set())
        fixture = Fixture("NORMAL")
        fixture.post()
        fixture.tool("order")
        with self.assertRaises(ValueError):
            fixture.tool("order")
        self.assertEqual(fixture.written, {"order"})
