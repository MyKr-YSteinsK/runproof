"""Durable boundary negative controls with task-owned SQLite fixtures."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from threading import Barrier
import unittest

from runtime.runproof_runtime.effectwitness import pge_r106_contracts as inner
from runtime.runproof_runtime.effectwitness import pge_r108_contracts as c, pge_r108_candidate as candidate
from runtime.runproof_runtime.effectwitness.pge_r108_controller_adapter import Adapter, fresh, readback
from runtime.runproof_runtime.effectwitness.pge_r108_provider_boundary import Boundary
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, sha, strict

SQLITE = os.environ.get("RPF108_LOCAL_SQLITE") == "1"
SOURCE = os.environ.get("RPF108_SOURCE_SHA", c.BASE)


@contextmanager
def setup(fault=None):
    adapter = Adapter(fresh(), SOURCE)
    edge = None
    try:
        edge = Boundary(adapter, adapter.apply(inner.SEED), fault=fault)
        yield adapter, edge, c.request(edge.contract)
    finally:
        if edge is not None:
            edge.close()
        adapter.ledger.close()


def response(request):
    return candidate.fixture_response(sha(request), inner.OPS, "fixture-dynamic")


def callback(selected):
    return canonical({"tool_call_id": selected["tool_call_id"], "name": c.TOOL,
                      "arguments": {"candidate_id": selected["candidate_id"]}})


class CandidateTests(unittest.TestCase):
    def test_dynamic_response_and_negative_shapes(self):
        request = b"fixture"
        raw = response(request)
        selected = candidate.parse(raw, sha(request), 1)
        self.assertEqual(candidate.callback(callback(selected), selected), inner.OPS)
        row = strict(raw)
        bad = [row | {"finish_reason": "refusal"}, row | {"finish_reason": "error"}, row | {"calls": []},
               row | {"calls": row["calls"] * 2}, row | {"usage": {"input_tokens": 0}},
               row | {"classification": "PROVIDER_OBSERVED"}, row | {"simulated_request_id": "sim-other"},
               row | {"calls": [row["calls"][0] | {"arguments": "{invalid"}]},
               row | {"calls": [row["calls"][0] | {"arguments": '{"candidate_id":"over-budget"}'}]}]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(ValueError):
                candidate.parse(canonical(item), sha(request), 1)
        with self.assertRaisesRegex(ValueError, "RESPONSE_TIMEOUT"):
            candidate.parse(raw, sha(request), c.DEADLINE_MS + 1)
        with self.assertRaisesRegex(ValueError, "CALLBACK_BINDING"):
            candidate.callback(callback(selected | {"tool_call_id": "foreign"}), selected)
        with self.assertRaisesRegex(ValueError, "CALLBACK_BINDING"):
            candidate.callback(canonical(strict(callback(selected)) | {"oracle": "PASS"}), selected)


@unittest.skipUnless(SQLITE, "Requires authorized RPF-108 fixture root")
class BoundaryTests(unittest.TestCase):
    def test_simultaneous_reserve_is_single_use(self):
        with setup() as (adapter, edge, request):
            barrier = Barrier(2)

            def reserve(_):
                barrier.wait(timeout=5)
                return edge.reserve(request)

            with ThreadPoolExecutor(max_workers=2) as threads:
                permits = list(filter(None, threads.map(reserve, range(2))))
            self.assertEqual(len(permits), 1)
            with self.assertRaisesRegex(ValueError, "SEND_PERMIT"):
                edge.simulate(object(), response(request), 1)
            edge.simulate(permits[0], response(request), 1)
            with self.assertRaisesRegex(ValueError, "SEND_PERMIT"):
                edge.simulate(permits[0], response(request), 1)
            self.assertEqual([r["kind"] for r in edge.journal.events].count("PROVIDER_RESERVE"), 1)
            self.assertEqual(adapter.ledger.snapshot()["remaining"], inner.COST)

    def test_stale_cross_owner_or_absent_feedback_denied(self):
        for field, value in (("revision", 0), ("feedback_sha256", None), ("scope", {"owner": "foreign"})):
            with self.subTest(field=field), setup() as (adapter, edge, request):
                self.assertIsNone(edge.reserve(canonical(strict(request) | {field: value})))
                self.assertIsNone(edge.reserve(request))
                self.assertEqual(adapter.ledger.snapshot()["remaining"], inner.COST)
                self.assertNotIn("PROVIDER_RESERVE", [r["kind"] for r in edge.journal.events])

    def test_presend_windows_and_exclusive_reopen(self):
        for stage in ("BEFORE_RESERVE", "AFTER_RESERVE", "AFTER_SEND_INTENT", "AFTER_SIMULATED_ENTRY"):
            with self.subTest(stage=stage), setup(stage) as (adapter, edge, request):
                permit = edge.reserve(request)
                if stage in ("BEFORE_RESERVE", "AFTER_RESERVE"):
                    self.assertIsNone(permit)
                else:
                    with self.assertRaisesRegex(OSError, stage):
                        edge.simulate(permit, response(request), 1)
                self.assertIsNone(edge.reserve(request))
                self.assertEqual(adapter.ledger.snapshot()["remaining"], inner.COST)
                wal = adapter.ledger.path.read_bytes()
                with self.assertRaisesRegex(ValueError, "PATH_OCCUPIED"):
                    Adapter(adapter.owner, SOURCE)
                self.assertEqual(adapter.ledger.path.read_bytes(), wal)
                self.assertNotIn("SIMULATED_RESPONSE", [r["kind"] for r in edge.journal.events])

    def test_commit_windows_cannot_reconcile_into_new_permission(self):
        for stage in ("WRITE_INTENT", "AFTER_SQLITE_COMMIT", "UNKNOWN", "BEFORE_OUTER_UNKNOWN"):
            with self.subTest(stage=stage), setup() as (adapter, edge, request):
                if stage == "BEFORE_OUTER_UNKNOWN":
                    edge.fault = stage
                else:
                    adapter.fault = stage
                selected = edge.simulate(edge.reserve(request), response(request), 1)
                with self.assertRaisesRegex(OSError, stage):
                    edge.apply_callback(callback(selected))
                fact = readback(adapter.owner, adapter.frozen["catalog"][inner.OPS])
                self.assertEqual(len(fact["snapshot"]["receipts"]), int(stage != "WRITE_INTENT"))
                before = adapter.ledger.path.read_bytes()
                self.assertIsNone(edge.reserve(request))
                self.assertEqual(before, adapter.ledger.path.read_bytes())
                with self.assertRaisesRegex(ValueError, "CALLBACK_PHASE"):
                    edge.apply_callback(callback(selected))
