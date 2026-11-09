"""Owner, capsule, historical compatibility and durable test-only fixtures."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
from pathlib import Path
import sqlite3
import threading
import unittest
from unittest.mock import patch

from ci import rpf103_verify_archive
from ci.test_rpf104_product_sdk import Fixture, OWNER, RUN, SOURCE
from runtime.runproof_runtime.effectwitness import product_sdk_capsule as cap, product_sdk_contracts as c
from runtime.runproof_runtime.effectwitness import product_sdk_oracle as o, product_sdk_probe as probe
from runtime.runproof_runtime.effectwitness import product_sdk_target as t
from runtime.runproof_runtime.effectwitness.product_sdk_host import new_journal
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, sha, strict


class ControlTests(unittest.TestCase):
    def test_historical_archive_source_identity(self):
        result = rpf103_verify_archive.verify_archive(rpf103_verify_archive.ARCHIVE)
        self.assertEqual(result["cases"]["UNKNOWN"]["post_unknown_send_entries"], 0)

    def test_capsule_integrity_and_disclosure(self):
        cases = {case: canonical(Fixture(case).complete()) for case in ("NORMAL", "UNKNOWN")}
        files = {f"{case}.json": raw for case, raw in cases.items()}
        manifest = {"schema": cap.SCHEMA, "admission": probe.admission(SOURCE, RUN, OWNER),
                    "states": dict.fromkeys(cases, "VERIFIED"), "issuer": "NOT_ESTABLISHED",
                    "real_explorer": "NOT_RUN", "external_provider_requests": 0, "provider_kind": "SCRIPTED_LOCAL",
                    "members": {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in files.items()}}
        raw_manifest = canonical(manifest)
        raw = cap.pack({**files, "manifest.json": raw_manifest})
        result = cap.verify_zip(raw, SOURCE, RUN, OWNER, manifest_sha=sha(raw_manifest),
                                zip_sha=sha(raw), require_complete=True)
        self.assertEqual(result["status"], "VERIFIED")  # Synthetic schema control only.
        for args in (("b" * 40, RUN, OWNER), (SOURCE, "1234568", OWNER), (SOURCE, RUN, "2" * 32)):
            with self.assertRaisesRegex(ValueError, "MANIFEST_IDENTITY"):
                cap.verify_zip(raw, *args)
        for name in files:
            swapped = {**files, name: files["UNKNOWN.json" if name == "NORMAL.json" else "NORMAL.json"]}
            changed = {**manifest, "members": {n: {"sha256": sha(value), "bytes": len(value)}
                                               for n, value in swapped.items()}}
            with self.assertRaisesRegex(ValueError, "CASE_BINDING"):
                cap.verify_zip(cap.pack({**swapped, "manifest.json": canonical(changed)}), SOURCE, RUN, OWNER)
        with self.assertRaisesRegex(ValueError, "PUBLIC_SCOPE"):
            cap.safe_public(canonical({"authorization": "fictional"}))
        with self.assertRaisesRegex(ValueError, "PUBLIC_SCOPE"):
            cap.safe_public(canonical({"path": "/home/example/private"}))

    def test_incomplete_capsule_cannot_pass_complete_gate(self):
        diag = {"state": "NOT_RUN", "contract_present": False, "sdk_error": None,
                "sdk_exit": None, "sdk_posts": None, "business_writes": None, "receiver_bytes": None}
        raw = canonical({"NORMAL": diag, "UNKNOWN": diag})
        manifest = {"schema": cap.SCHEMA, "admission": probe.admission(SOURCE, RUN, OWNER),
                    "states": dict.fromkeys(("NORMAL", "UNKNOWN"), "NOT_RUN"),
                    "issuer": "NOT_ESTABLISHED", "provider_kind": "SCRIPTED_LOCAL",
                    "external_provider_requests": 0, "real_explorer": "NOT_RUN",
                    "members": {"diagnostic.json": {"sha256": sha(raw), "bytes": len(raw)}}}
        bundle = cap.pack({"manifest.json": canonical(manifest), "diagnostic.json": raw})
        self.assertEqual(cap.verify_zip(bundle, SOURCE, RUN, OWNER)["status"], "DIAGNOSTIC")
        with self.assertRaisesRegex(ValueError, "CAPSULE_COMPLETE"):
            cap.verify_zip(bundle, SOURCE, RUN, OWNER, require_complete=True)

    def test_authority_binding_before_write_and_wrong_owner(self):
        fixture = Fixture("NORMAL")
        fixture.post()
        authority = fixture.session.authority
        fixture.session.authority = lambda domain: {**authority(domain), "authority": "SDK_ASSERTION"}
        with self.assertRaisesRegex(ValueError, "AUTHORITY_IDENTITY"):
            fixture.tool("order")
        self.assertEqual(fixture.written, set())
        fixture = Fixture("NORMAL")
        fixture.post()
        with self.assertRaisesRegex(ValueError, "WRITE_SCOPE"):
            fixture.session.admit_write("order", {**c.binding(fixture.frozen, "order"), "owner": "0" * 32})

    def test_unknown_serializes_with_concurrent_reservation(self):
        fixture = Fixture("UNKNOWN")
        fixture.post()
        durable = threading.Event()
        release = threading.Event()
        def persist(raw):
            if strict(raw)["kind"] == "UNKNOWN_OBSERVED":
                durable.set()
                if not release.wait(2):
                    raise RuntimeError("fixture timeout")
        fixture.session.journal.persist = persist
        with ThreadPoolExecutor(2) as pool:
            tool = pool.submit(fixture.tool, "order")
            try:
                self.assertTrue(durable.wait(2))
                attempt = pool.submit(fixture.session.reserve, "ops", "EXPLORER", {"number": 2})
            finally:
                release.set()
            self.assertEqual(tool.result(timeout=3)[0], 200)
            with self.assertRaisesRegex(ValueError, "UNKNOWN_OR_UNCERTAIN"):
                attempt.result(timeout=3)
        self.assertEqual(fixture.session.forwarded, 1)

    def test_hosted_gate_rejects_local_or_wrong_binding(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "HOSTED_ADMISSION"):
                probe.hosted(SOURCE, RUN)
        admitted = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
                    "GITHUB_REPOSITORY": "MyKr-YSteinsK/runproof", "GITHUB_REF": "refs/heads/main",
                    "GITHUB_SHA": SOURCE, "GITHUB_RUN_ID": RUN, "GITHUB_RUN_ATTEMPT": "1",
                    "RPF104_APPROVED_SOURCE_SHA": SOURCE, "RPF104_APPROVED_RUN_ID": RUN}
        with patch.dict(os.environ, admitted, clear=True):
            probe.hosted(SOURCE, RUN)
        for key, value in (("GITHUB_RUN_ATTEMPT", "2"), ("RPF104_APPROVED_SOURCE_SHA", "0" * 40),
                           ("RPF104_APPROVED_RUN_ID", "9"), ("GITHUB_EVENT_NAME", "push")):
            with patch.dict(os.environ, {**admitted, key: value}, clear=True):
                with self.assertRaisesRegex(ValueError, "HOSTED_ADMISSION"):
                    probe.hosted(SOURCE, RUN)
        self.assertEqual(c.freeze(SOURCE, OWNER, OWNER, "NORMAL", origin="LOCAL")["origin"], "LOCAL")
        with self.assertRaises(ValueError):
            c.freeze(SOURCE, RUN, OWNER, "NORMAL", origin="LOCAL")

    @unittest.skipUnless(os.environ.get("RPF104_TEST_OWNER"), "FRESH_TEST_OWNER_REQUIRED")
    def test_temporary_sqlite_transactions_and_nonresumable_wal(self):
        owner = os.environ["RPF104_TEST_OWNER"]
        root = t.safe(probe.owner_scope(owner), directory=True)
        folder = t.safe(root / "NORMAL", directory=True, absent=True)
        folder.mkdir()
        frozen = c.freeze(SOURCE, "9" * 32, owner, "NORMAL", origin="LOCAL")
        target = t.Target(folder, frozen)
        for domain in ("order", "ops"):
            binding = c.binding(frozen, domain)
            with self.assertRaisesRegex(ValueError, "TARGET_IDENTITY"):
                target.prepare(domain, {**binding, "owner": "e" * 32})
            target.prepare(domain, binding)
            before = t.readback(folder, frozen, domain)
            self.assertEqual(before["snapshot"], o.snapshot(frozen, domain, False))
            with self.assertRaisesRegex(ValueError, "TARGET_IDENTITY"):
                target.write_once(domain, {**binding, "contract_sha256": "0" * 64})
            target.write_once(domain, binding)
            after = t.readback(folder, frozen, domain)
            self.assertEqual(after["snapshot"], o.snapshot(frozen, domain, True))
            wrong_environment = c.freeze(SOURCE, "8" * 32, owner, "NORMAL", origin="LOCAL")
            with self.assertRaisesRegex(ValueError, "AUTHORITY_ENVIRONMENT"):
                t.readback(folder, wrong_environment, domain)
            self.assertEqual(c.feedback(frozen, domain, before, after, c.flags(frozen["contracts"][domain]))
                             ["value"]["outcome"], c.SUCCESS)
            with self.assertRaisesRegex(ValueError, "TARGET_IDENTITY"):
                target.write_once(domain, binding)
            with self.assertRaisesRegex(ValueError, "PATH_OCCUPIED"):
                t.Target(folder, frozen).prepare(domain, binding)
        path = folder / "wal.jsonl"
        with new_journal(path) as journal:
            journal.append("CASE_OPEN", {})
            journal.append("UNKNOWN_OBSERVED", {})
        sealed = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "PATH_OCCUPIED"):
            with new_journal(path):
                self.fail("restart reopened an effect journal")
        self.assertEqual(path.read_bytes(), sealed)
        with self.assertRaisesRegex(ValueError, "WAL_TORN"):
            o.replay(sealed[:-1])

    def test_missing_or_tampered_authority_fails(self):
        frozen = c.freeze(SOURCE, RUN, OWNER, "NORMAL")
        fixture = Fixture("NORMAL")
        before = fixture.authority("order")
        after = deepcopy(before)
        after["snapshot"] = o.snapshot(frozen, "order", True)
        after["snapshot"]["receipts"] = []
        self.assertNotEqual(c.feedback(frozen, "order", before, after, c.flags(frozen["contracts"]["order"]))
                            ["value"]["outcome"], c.SUCCESS)
        with self.assertRaisesRegex(ValueError, "AUTHORITY_IDENTITY"):
            c.feedback(frozen, "order", before, {**after, "pid": False}, c.flags(frozen["contracts"]["order"]))
