"""SYNTHETIC_TEST_ONLY controls for capsule contents and manual admission."""
from contextlib import redirect_stderr, redirect_stdout
import io
import os
import re
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

from ci import rpf102_rev3_capsule as capsule
from ci.test_rpf102_sdk_presend import chain, synthetic
from runtime.runproof_runtime.effectwitness import sdk_presend_probe as probe
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import (
    BUDGET, CASES, PINS, ROOT, Denied, canonical, sha, strict,
)
from runtime.runproof_runtime.effectwitness.sdk_presend_diagnostic import CONTEXT, REPORT, collect, context

SOURCE = "a" * 40
RUN = 12345678
OWNER = "1" * 32
WORKFLOW = ROOT.parents[1] / ".github" / "workflows" / "rpf-102-sdk-manual-conformance.yml"
REPO = ROOT.parents[1]
REV5_TEST_ROOT = REPO / ".local" / "rpf-102-rev5-bootstrap"
DIAGNOSTIC = "runtime.runproof_runtime.effectwitness.sdk_presend_diagnostic"


def collect_fixture(folder, case, **facts):
    # Reuse the real classifier with bounded I/O redirected to the rev-3 test root.
    with patch(DIAGNOSTIC + ".bounded", capsule.read), patch(
            DIAGNOSTIC + ".safe", lambda path: capsule.checked_path(path, missing=True)):
        return collect(folder, case, **facts)


class CapsuleTests(unittest.TestCase):
    def setUp(self):
        capsule.ensure_directory(REV5_TEST_ROOT.parent)
        capsule.ensure_directory(REV5_TEST_ROOT)
        self.site = REV5_TEST_ROOT / uuid4().hex
        self.site.mkdir()
        self.addCleanup(shutil.rmtree, self.site)
        self.owner = self.site / OWNER
        self.owner.mkdir()
        self.output = self.site / "published"
        capsule.create(self.owner / capsule.LEDGER, canonical(capsule.ledger(OWNER, SOURCE, RUN)))
        capsule.create(self.owner / "environment.json", canonical({
            "python": "3.12.16", "exe_sha256": "2" * 64, "packages": PINS,
        }))
        capsule.create(self.owner / "formal.json", canonical(capsule.FORMAL))

    def seed(self, case):
        owner, files, events = synthetic(case)
        self.assertEqual(owner, OWNER)
        if case == "NORMAL":
            # Bind fictional SDK usage to the existing synthetic terminal/exit receipts.
            row = strict(files["sdk-output.json"])
            row["terminal"]["sdk_reported_usage"] = {"input_tokens": 20, "output_tokens": 6}
            files["sdk-output.json"] = canonical(row)
            digest = sha(files["sdk-output.json"])
            files["sdk-exit.json"] = canonical({**strict(files["sdk-exit.json"]), "stdout_sha256": digest})
            events[-1][1]["sha256"] = digest
            files["wal.jsonl"] = chain(events)
        folder = self.owner / case
        folder.mkdir()
        capsule.create(folder / CONTEXT, canonical(context(folder, case)))
        for name, raw in files.items():
            capsule.create(folder / name, raw)
        outcome = "NORMAL_VERIFIED" if case == "NORMAL" else "UNKNOWN_EXPECTED_DENIAL"
        diagnostic = collect_fixture(folder, case, phase="TERMINAL", attempted=True, outcome=outcome)
        capsule.create(folder / REPORT, canonical(diagnostic))
        return folder, files, events

    def build(self):
        return capsule.build(self.owner, self.output, SOURCE, RUN)

    def rewrite_member(self, folder, name, raw):
        member = folder / name
        member.write_bytes(raw)
        manifest_path = folder / capsule.MANIFEST
        manifest = strict(manifest_path.read_bytes())
        manifest["files"][name].update(sha256=sha(raw), original_sha256=sha(raw), bytes=len(raw))
        manifest_path.write_bytes(canonical(manifest))

    def test_complete_original_payloads_verify_from_separate_extraction(self):
        originals = {case: self.seed(case)[1] for case in CASES}
        result = self.build()
        self.assertEqual(result["cases"], dict.fromkeys(CASES, "VERIFIED"))
        extracted = self.site / "isolated-extraction"
        shutil.copytree(self.output, extracted)
        reopened = capsule.inspect(extracted, SOURCE, RUN, result["capsule_sha256"])
        self.assertEqual(reopened, result)
        index = strict((extracted / capsule.MANIFEST).read_bytes())["files"]
        for case in CASES:
            self.assertEqual(result["oracle"][case]["send_entries"], BUDGET[case])
            self.assertEqual(result["oracle"][case]["post_unknown_send_entries"], 0)
            for name, raw in originals[case].items():
                actual = (extracted / case / name).read_bytes()
                self.assertEqual(index[f"{case}/{name}"]["original_sha256"], sha(raw))
                if capsule.nonce_member(name):
                    self.assertNotIn(b"3" * 64, actual)
                    self.assertNotEqual(actual, raw)
                else:
                    self.assertEqual(actual, raw)
        with self.assertRaises(FileExistsError):
            self.build()
        with self.assertRaisesRegex(Denied, "CAPSULE_ANCHOR"):
            capsule.inspect(extracted, SOURCE, RUN, "0" * 64)

    def test_failed_process_keeps_validated_diagnostic_and_require_complete_fails(self):
        folder = self.owner / "NORMAL"
        folder.mkdir()
        capsule.create(folder / CONTEXT, canonical(context(folder, "NORMAL")))
        capsule.create(folder / "sdk-launch.json", canonical({"pid": 113}))
        stdout = b'{"status":"SDK_ERROR","stage":"SDK_IMPORT","error_type":"ImportError"}'
        capsule.create(folder / "sdk-output.json", stdout)
        capsule.create(folder / "sdk-exit.json", canonical({"pid": 113, "exit": 7, "stdout_sha256": sha(stdout)}))
        diagnostic = collect_fixture(folder, "NORMAL", phase="SDK", attempted=True)
        capsule.create(folder / REPORT, canonical(diagnostic))
        self.assertEqual(diagnostic["sdk_exit"], 7)
        self.assertIsNone(diagnostic["received_bytes"])
        result = self.build()
        self.assertEqual(result["cases"], {"NORMAL": "FAILURE_DIAGNOSTIC", "UNKNOWN": "NOT_RUN"})
        self.assertEqual({p.name for p in (self.output / "NORMAL").iterdir()}, {REPORT})
        argv = ["capsule", "verify", "--folder", str(self.output), "--owner", OWNER,
                "--expected-sha", SOURCE, "--run-id", str(RUN)]
        with patch("sys.argv", argv), redirect_stdout(io.StringIO()):
            self.assertEqual(capsule.main(), 0)
            argv.append("--require-complete")
            self.assertEqual(capsule.main(), 1)

    def test_unsafe_partial_case_downgrades_without_recreating_bytes(self):
        folder, _, _ = self.seed("NORMAL")
        (folder / "receiver-2.raw").unlink()
        self.assertEqual(self.build()["cases"], {"NORMAL": "FAILURE_DIAGNOSTIC", "UNKNOWN": "NOT_RUN"})
        self.assertFalse((folder / "receiver-2.raw").exists())
        self.assertFalse((self.output / "NORMAL" / "sdk-post-1.raw").exists())

    def test_missing_diagnostic_cannot_publish_any_case_evidence(self):
        folder, _, _ = self.seed("NORMAL")
        (folder / REPORT).unlink()
        self.assertEqual(self.build()["cases"], {"NORMAL": "UNAVAILABLE", "UNKNOWN": "NOT_RUN"})
        self.assertFalse((self.output / "NORMAL").exists())

    def test_unknown_requires_safe_normal_and_unexpected_owner_file_downgrades(self):
        self.seed("UNKNOWN")
        capsule.create(self.owner / "unapproved.txt", b"private")
        result = self.build()
        self.assertEqual(result["cases"], {"NORMAL": "NOT_RUN", "UNKNOWN": "FAILURE_DIAGNOSTIC"})
        self.assertEqual(result["oracle"], {})
        self.assertFalse((self.output / "unapproved.txt").exists())

    def test_reanchored_post_unknown_reserve_and_swapped_receiver_rejected(self):
        self.seed("NORMAL")
        _, _, events = self.seed("UNKNOWN")
        self.build()
        path = "UNKNOWN/receiver-1.json"
        raw = (self.output / path).read_bytes()
        # Change the public receipt and re-anchor its digest in the manifest.
        bad = canonical({**strict(raw), "case": "NORMAL"})
        (self.output / path).write_bytes(bad)
        manifest_path = self.output / capsule.MANIFEST
        manifest = strict(manifest_path.read_bytes())
        prior = manifest["files"][path].copy()
        manifest["files"][path].update(sha256=sha(bad), bytes=len(bad))
        manifest_path.write_bytes(canonical(manifest))
        with self.assertRaisesRegex(Denied, "RECEIVER_BYTES"):
            capsule.inspect(self.output, SOURCE, RUN)
        (self.output / path).write_bytes(raw)
        manifest["files"][path] = prior
        manifest_path.write_bytes(canonical(manifest))
        self.rewrite_member(self.output, "UNKNOWN/wal.jsonl", chain([*events, ("PROVIDER_RESERVE", {})]))
        with self.assertRaisesRegex(ValueError, "POST_UNKNOWN_PROVIDER_RESERVE"):
            capsule.inspect(self.output, SOURCE, RUN)

    def test_reanchored_raw_rejects_truncation_duplicates_and_secret_like_fields(self):
        _, original, _ = self.seed("NORMAL")
        self.build()
        name = "NORMAL/sdk-post-1.raw"
        original_raw = original["sdk-post-1.raw"]
        bad = strict(original_raw)
        bad["tools"][0]["function"]["description"] = "Bearer sk-fictitious-example"
        for raw in (original_raw[:-1], b'{"model":"a","model":"b"}', canonical(bad)):
            self.rewrite_member(self.output, name, raw)
            with self.assertRaises(ValueError):
                capsule.inspect(self.output, SOURCE, RUN)

    def test_source_ref_run_traversal_and_extra_member_rejected(self):
        self.seed("NORMAL")
        with self.assertRaisesRegex(Denied, "CAPSULE_ADMISSION_BINDING"):
            capsule.build(self.owner, self.output, "b" * 40, RUN)
        self.build()
        for source, run in (("b" * 40, RUN), (SOURCE, RUN + 1)):
            with self.assertRaisesRegex(Denied, "CAPSULE_SOURCE"):
                capsule.inspect(self.output, source, run)
        manifest_path = self.output / capsule.MANIFEST
        manifest = strict(manifest_path.read_bytes())
        manifest["files"]["../escaped"] = manifest["files"][capsule.LEDGER]
        manifest_path.write_bytes(canonical(manifest))
        with self.assertRaisesRegex(Denied, "CAPSULE_INDEX"):
            capsule.inspect(self.output, SOURCE, RUN)
        del manifest["files"]["../escaped"]
        manifest_path.write_bytes(canonical(manifest))
        capsule.create(self.output / "extra", b"private")
        with self.assertRaisesRegex(Denied, "CAPSULE_EXTRA"):
            capsule.inspect(self.output, SOURCE, RUN)

    def test_hardlinked_receipt_is_never_read_or_exported_as_full(self):
        folder, _, _ = self.seed("NORMAL")
        target = folder / "receiver-1.raw"
        external = self.site / "untrusted"
        target.rename(external)
        os.link(external, target)
        self.assertEqual(self.build()["cases"]["NORMAL"], "FAILURE_DIAGNOSTIC")
        self.assertTrue(external.exists())

    def test_manual_only_workflow_preserves_failure_and_pins_run(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        trigger = workflow.split("\non:\n")[1].split("\npermissions:")[0]
        self.assertEqual(re.findall(r"^  (\w+):", trigger, re.M), ["workflow_dispatch"])
        self.assertIn("\npermissions:\n  contents: read\n", workflow)
        self.assertIn('test "$APPROVED_SOURCE_SHA" = "$GITHUB_SHA"', workflow)
        self.assertIn('test "$APPROVED_RUN_ID" = "$GITHUB_RUN_ID"', workflow)
        self.assertIn('test "$GITHUB_RUN_ATTEMPT" = 1', workflow)
        self.assertIn("deployment: false", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertLess(workflow.index("Preflight and bind new owner"), workflow.index("-m pip --isolated"))
        self.assertIn("if: always() && steps.preflight.outputs.owner != ''", workflow)
        self.assertEqual(workflow.count("if: always() && steps.capsule.outputs.ready == 'true'"), 2)
        self.assertLess(workflow.index("capsule verify --folder"), workflow.index("actions/upload-artifact"))
        self.assertIn("capsule verify --require-complete", workflow)

    def test_offline_fresh_checkout_smoke_precedes_existing_suite(self):
        workflow = (REPO / ".github" / "workflows" / "rpf-102-sdk-presend.yml").read_text(encoding="utf-8")
        smoke = "Fresh-checkout owner bootstrap smoke"
        suite = "ci.test_rpf102_sdk_presend ci.test_rpf102_rev3_capsule"
        trigger = workflow.split("\npermissions:")[0]
        self.assertIn("\non:\n  push:\n", trigger)
        self.assertNotIn("workflow_dispatch", trigger)
        self.assertLess(workflow.index(smoke), workflow.index(suite))
        self.assertIn(
            "ci.test_rpf102_rev3_capsule.FreshCheckoutBootstrapTests",
            workflow[workflow.index(smoke):workflow.index(suite)],
        )
        self.assertNotIn("pip install", workflow[workflow.index(smoke):workflow.index(suite)])

    def test_probe_stops_before_unknown_when_normal_capsule_is_unavailable(self):
        owner = self.site / "probe-fixture"
        owner.mkdir()
        with (
            patch.object(probe, "preflight", return_value={"status": "SDK_ADMITTED", "formal_occupied": False}),
            patch.object(probe, "safe", lambda path: capsule.checked_path(path, missing=True)),
            patch.object(probe, "exclusive", capsule.create),
            patch.object(probe, "run_case") as run_case,
            patch.object(probe, "inspect_case", return_value={}),
            patch.object(probe, "collect", return_value={}),
            patch("builtins.print"),
        ):
            def reject(folder, case):
                self.assertEqual(case, "NORMAL")
                self.assertTrue((folder / REPORT).is_file())
                raise Denied("CAPSULE_CASE_UNAVAILABLE")

            with self.assertRaisesRegex(Denied, "CAPSULE_CASE_UNAVAILABLE"):
                probe.run(owner, accept_case=reject)
        self.assertEqual(run_case.call_count, 1)
        self.assertFalse((owner / "UNKNOWN").exists())


class FreshCheckoutBootstrapTests(unittest.TestCase):
    def test_admit_cli_bootstraps_missing_local_parent(self):
        local = REPO / ".local"
        if not local.exists() and not local.is_symlink():
            # The hosted smoke runs this branch before any test creates .local.
            root = REV5_TEST_ROOT
            keep_owner = True
        else:
            # Repeated local/full-suite execution uses a fresh nested checkout shape,
            # still confined below this run's unique rev-5 test directory.
            capsule.ensure_directory(local)
            capsule.ensure_directory(REV5_TEST_ROOT)
            task = REV5_TEST_ROOT / uuid4().hex
            task.mkdir()
            self.addCleanup(shutil.rmtree, task)
            checkout = task / "checkout"
            checkout.mkdir()
            root = checkout / ".local" / "rpf-102-rev5-bootstrap"
            keep_owner = False

        self.assertFalse(root.parent.exists())
        owner = uuid4().hex
        stderr = io.StringIO()
        with patch.object(capsule, "ROOT", root), patch(
            "sys.argv", ["rpf102_rev3_capsule", "admit", "--owner", owner,
                         "--expected-sha", SOURCE, "--run-id", str(RUN)]
        ), redirect_stderr(stderr):
            result = capsule.main()
        self.assertEqual(result, 0, stderr.getvalue())
        owner_dir = capsule.checked_path(root / owner, directory=True)
        expected = canonical(capsule.ledger(owner, SOURCE, RUN))
        self.assertEqual(capsule.read(owner_dir / capsule.LEDGER), expected)
        self.assertTrue(root.parent.is_dir())
        self.assertFalse(root.parent.is_symlink())
        if keep_owner:
            self.assertEqual(owner_dir.parent, REV5_TEST_ROOT)
        print("RPF102_FRESH_CHECKOUT_OWNER_BOOTSTRAP_PASS; SDK_PHYSICAL_NOT_RUN")


class OwnerAdmissionTests(unittest.TestCase):
    def setUp(self):
        capsule.ensure_directory(REV5_TEST_ROOT.parent)
        capsule.ensure_directory(REV5_TEST_ROOT)
        self.site = REV5_TEST_ROOT / uuid4().hex
        self.site.mkdir()
        self.addCleanup(shutil.rmtree, self.site)

    def admit(self, root, owner=OWNER):
        stderr = io.StringIO()
        with patch.object(capsule, "ROOT", root), patch(
            "sys.argv", ["rpf102_rev3_capsule", "admit", "--owner", owner,
                         "--expected-sha", SOURCE, "--run-id", str(RUN)]
        ), redirect_stderr(stderr):
            result = capsule.main()
        return result, stderr.getvalue()

    def test_safe_existing_root_accepts_distinct_owner_but_duplicate_is_immutable(self):
        root = self.site / "rpf-102-sdk-presend"
        first, _ = self.admit(root, OWNER)
        first_ledger = capsule.read(root / OWNER / capsule.LEDGER)
        second_owner = "2" * 32
        second, _ = self.admit(root, second_owner)
        second_ledger = capsule.read(root / second_owner / capsule.LEDGER)
        duplicate, _ = self.admit(root, OWNER)
        self.assertEqual((first, second, duplicate), (0, 0, 3))
        self.assertEqual(capsule.read(root / OWNER / capsule.LEDGER), first_ledger)
        self.assertEqual(second_ledger, canonical(capsule.ledger(second_owner, SOURCE, RUN)))

    def test_occupied_owner_and_existing_ledger_are_never_overwritten(self):
        root = self.site / "rpf-102-sdk-presend"
        root.mkdir()
        occupied = root / OWNER
        occupied.mkdir()
        ledger = occupied / capsule.LEDGER
        sentinel = b"preserve-existing-ledger\n"
        ledger.write_bytes(sentinel)
        empty_owner = root / ("2" * 32)
        empty_owner.mkdir()
        existing, _ = self.admit(root, OWNER)
        empty, _ = self.admit(root, "2" * 32)
        self.assertEqual((existing, empty), (3, 3))
        self.assertEqual(ledger.read_bytes(), sentinel)
        self.assertFalse((empty_owner / capsule.LEDGER).exists())

    def test_regular_file_parent_fails_closed_without_replacement(self):
        parent = self.site / "not-a-directory"
        sentinel = b"parent-file-is-preserved"
        parent.write_bytes(sentinel)
        result, stderr = self.admit(parent / "rpf-102-sdk-presend")
        self.assertEqual(result, 3)
        self.assertIn("CAPSULE_UNAVAILABLE", stderr)
        self.assertIn("CAPSULE_FAILURE_CLASS=CAPSULE_DIRECTORY", stderr)
        self.assertNotIn(str(parent), stderr)
        self.assertEqual(parent.read_bytes(), sentinel)

    def test_reparse_parent_fails_closed_without_writing_through_target(self):
        target = self.site / "real-parent"
        target.mkdir()
        link = self.site / "reparse-parent"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"SYMLINK_UNAVAILABLE:{type(exc).__name__}")
        result, stderr = self.admit(link / "rpf-102-sdk-presend")
        self.assertEqual(result, 3)
        self.assertIn("CAPSULE_FAILURE_CLASS=CAPSULE_LINK", stderr)
        self.assertEqual(list(target.iterdir()), [])

    def test_reparse_root_fails_closed_without_writing_through_target(self):
        target = self.site / "real-root"
        target.mkdir()
        link = self.site / "reparse-root"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"SYMLINK_UNAVAILABLE:{type(exc).__name__}")
        result, stderr = self.admit(link)
        self.assertEqual(result, 3)
        self.assertIn("CAPSULE_FAILURE_CLASS=CAPSULE_LINK", stderr)
        self.assertEqual(list(target.iterdir()), [])

    def test_nonwritable_parent_fails_closed_when_posix_permissions_are_enforced(self):
        if os.name != "posix" or os.geteuid() == 0:
            self.skipTest("FILESYSTEM_PERMISSION_CONTROL_UNAVAILABLE")
        parent = self.site / "read-only-parent"
        parent.mkdir()
        os.chmod(parent, 0o555)
        try:
            result, _ = self.admit(parent / "rpf-102-sdk-presend")
            self.assertEqual(result, 3)
            self.assertFalse((parent / "rpf-102-sdk-presend").exists())
        finally:
            os.chmod(parent, 0o755)
