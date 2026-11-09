"""Bounded RPF-101 conformance. One physical suite per checkout owner."""
from contextlib import nullcontext
import os
import subprocess
import threading
import time
import unittest

from runtime.runproof_runtime.effectwitness import provider_receipt_verify as oracle
from runtime.runproof_runtime.effectwitness.provider_barrier import (
    CASES, DOMAINS, PAYLOAD, ROLES, ROOT, Denied, Host, canonical, digest, exclusive, read_wal, safe,
)
from runtime.runproof_runtime.effectwitness.provider_transport import (
    connected_receiver, executable_identity, launch_isolated, read_json, receiver,
)

REQUEST = digest(PAYLOAD)


def denied(fn):
    try:
        fn()
    except Denied:
        return
    raise AssertionError("UNEXPECTED_ADMISSION")


def after_unknown(host, old=None):
    for domain in DOMAINS:
        for role in ROLES:
            denied(lambda: host.reserve(domain, role, REQUEST))
    if old is not None:
        denied(lambda: host.send(old, PAYLOAD))


def recovery_child(case):
    with Host(case).open() as host:
        _, _, ticket, _, _ = host.state()
        if case == "ready-restart":
            host.send(ticket, PAYLOAD)
        else:
            after_unknown(host, ticket)
        exclusive(host.root / "recovery.json", canonical({
            "case": case, "pid": os.getpid(), "exe_sha256": executable_identity(),
            "decision": "SENT" if case == "ready-restart" else "DENIED",
        }))


def recover(case, folder):
    start = time.monotonic_ns()
    process = launch_isolated(folder,
        "from ci.test_rpf101_provider_barrier import recovery_child; recovery_child(sys.argv[1])", [case])
    try:
        code = process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        process.kill()
        code = process.wait(timeout=5)
    result = {"pid": process.pid, "exe_sha256": executable_identity(), "exit": code,
              "start_ns": start, "exit_ns": time.monotonic_ns()}
    exclusive(folder / "recovery-launch.json", canonical(result))
    assert code == 0
    receipt = read_json(folder / "recovery.json")
    assert receipt["pid"] == process.pid and receipt["pid"] != os.getpid()
    assert receipt["exe_sha256"] == result["exe_sha256"] and receipt["case"] == case
    assert receipt["decision"] == ("SENT" if case == "ready-restart" else "DENIED")
    if case == "ready-restart":
        sender = read_json(folder / "sender-receipt.json")
        assert sender["pid"] == process.pid and start <= sender["entry_ns"] <= result["exit_ns"]


def race(case, ready):
    held, attempted, proceed = (threading.Event() for _ in range(3))
    first = "SEND_BEGIN" if case == "send-first" else "UNKNOWN_OBSERVED"
    errors = []

    class ScheduledHost(Host):
        def append(self, kind, body, rows):
            super().append(kind, body, rows)
            if kind == first:
                held.set()
                if not proceed.wait(3):
                    raise AssertionError("RACE_TIMEOUT")

    def worker(fn, second=False):
        try:
            if second:
                attempted.set()
            fn()
        except Exception as exc:
            errors.append(exc)

    with ScheduledHost(case, create=True, receiver=ready).open() as host:
        ticket = host.reserve("order", "TARGET", REQUEST)
        send = lambda: host.send(ticket, PAYLOAD)
        unknown = lambda: host.observe_unknown("ops")
        lead, lag = (send, unknown) if case == "send-first" else (unknown, lambda: denied(send))
        a = threading.Thread(target=worker, args=(lead,))
        b = threading.Thread(target=worker, args=(lag, True))
        a.start()
        try:
            assert held.wait(4)
            b.start()
            assert attempted.wait(2)
        finally:
            proceed.set()
            a.join(5)
            if b.ident is not None:
                b.join(5)
        assert not (a.is_alive() or b.is_alive() or errors), errors
        after_unknown(host, ticket)


def formal():
    safe(ROOT)
    ROOT.parent.mkdir(exist_ok=True)
    safe(ROOT)
    ROOT.mkdir(parents=False, exist_ok=False)
    exclusive(ROOT / "formal.json", canonical({"cases": list(CASES), "max_cases": 12,
                                                "max_application_sends": 8, "max_children": 2}))
    results = {}
    physical = {"ready-restart", "unknown-restart", "send-first", "unknown-first"}
    for case in CASES:
        with receiver(case) if case in physical else nullcontext() as ready:
            if case in ("send-first", "unknown-first"):
                race(case, ready)
            else:
                fault = case.split("-")[0] if case.endswith("-failure") else None
                with Host(case, create=True, receiver=ready, fault=fault).open() as host:
                    ticket = host.reserve("order", "TARGET", REQUEST) if case in physical else None
                    if case == "ready-restart":
                        denied(lambda: host.send({**ticket, "id": "forged"}, PAYLOAD))
                        def wrong_receiver():
                            with connected_receiver(case, {**ready, "nonce": "0" * 64}):
                                raise AssertionError("FORGED_RECEIVER_ADMITTED")
                        denied(wrong_receiver)
                        with unittest.TestCase().assertRaises(OSError):
                            with Host(case).open():
                                raise AssertionError("WRITER_LOCK_ADMITTED")
                    if case in ("unknown-empty", "unknown-restart"):
                        host.observe_unknown("order")
                        after_unknown(host, ticket)
                    if fault:
                        with unittest.TestCase().assertRaisesRegex(OSError, "SIMULATED_"):
                            host.observe_unknown("order")
                        after_unknown(host)
                if case in ("ready-restart", "unknown-restart"):
                    recover(case, ROOT / "sessions" / case)
                if fault:
                    def reopen():
                        with Host(case).open():
                            raise AssertionError("POISON_CLEARED")
                    denied(reopen)
                if case == "torn":
                    wal = safe(ROOT / "sessions" / case / "wal.jsonl")
                    with wal.open("ab") as handle:
                        handle.write(b'{"torn":')
                        handle.flush()
                        os.fsync(handle.fileno())
                    def reopen_torn():
                        with Host(case).open():
                            raise AssertionError("TORN_WAL_ACCEPTED")
                    denied(reopen_torn)
        if case.endswith("-failure") or case == "torn":
            with unittest.TestCase().assertRaisesRegex(ValueError, "PERSISTENCE_UNCERTAIN"):
                oracle.read_case(case)
            results[case] = {"status": "PERSISTENCE_UNCERTAIN", "send_entries": 0,
                             "receiver": "NOT_STARTED"}
        else:
            results[case] = oracle.verify_evidence(case, oracle.read_case(case))
    exclusive(ROOT / "formal-result.json", canonical(results))
    return results


def rechain(rows):
    previous = "0" * 64
    encoded = []
    for i, row in enumerate(rows):
        base = {"seq": i, "prev": previous, "kind": row["kind"], "body": row["body"]}
        previous = oracle.sha(oracle.dump(base))
        encoded.append(oracle.dump({**base, "sha256": previous}))
    return b"\n".join(encoded) + b"\n"


def attack_tests(test):
    case = "unknown-restart"
    members = oracle.read_case(case)
    rows = [oracle.decode(line) for line in members["wal"].splitlines()]
    for kind in ("RESERVE", "SEND_BEGIN"):
        altered = {**members, "wal": rechain([*rows, {"kind": kind, "body": rows[1]["body"]}])}
        anchor = oracle.sha(oracle.dump({key: oracle.sha(value) for key, value in altered.items()}))
        with test.assertRaisesRegex(ValueError, "POST_UNKNOWN_"):
            oracle.verify_evidence(case, altered, anchor)
    case = "ready-restart"
    members = oracle.read_case(case)
    with test.assertRaisesRegex(ValueError, "ANCHOR_MISMATCH"):
        oracle.verify_evidence(case, members, "0" * 64)
    for key, data in (
        ("raw", b""), ("receipt", oracle.read_case("unknown-first")["receipt"]),
        ("ready", oracle.dump({**oracle.decode(members["ready"]), "nonce": "0" * 64})),
        ("launch", oracle.dump({**oracle.decode(members["launch"]), "pid": 1})),
        ("ready", b'{"pid":1,"pid":2}'),
        ("sender", oracle.dump({**oracle.decode(members["sender"]), "receiver_nonce": "0" * 64})),
    ):
        with test.assertRaises(ValueError):
            oracle.verify_evidence(case, {**members, key: data})
    rows = [oracle.decode(line) for line in members["wal"].splitlines()]
    rows[0]["body"]["source"]["provider_barrier.py"] = "0" * 64
    with test.assertRaisesRegex(ValueError, "READY_IDENTITY"):
        oracle.verify_evidence(case, {**members, "wal": rechain(rows)})


class Conformance(unittest.TestCase):
    def test_01_strict_evidence_controls(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_KEY"):
            oracle.decode(b'{"seq":1,"seq":2}')
        with self.assertRaisesRegex(ValueError, "OWNER_SCOPE"):
            safe(ROOT / ".." / "outside")

    def test_02_formal_loopback_and_recovery(self):
        results = formal()
        self.assertEqual(len(results), 8)
        self.assertEqual(sum(row["send_entries"] for row in results.values()), 2)
        self.assertTrue(results["send-first"]["pre_unknown_in_flight"])
        for case in ("unknown-restart", "unknown-first"):
            self.assertEqual(results[case]["received_bytes"], 0)
            self.assertTrue(results[case]["unknown"])
        attack_tests(self)
