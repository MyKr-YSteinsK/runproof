"""Pinned import-only and audit controls. No model, Host or Receiver execution."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from unittest.mock import patch

from ci.rpf102_rev3_capsule import ensure_directory
from runtime.runproof_runtime.effectwitness import sdk_presend_client as client
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import PINS, REPO, Denied, canonical, strict
from runtime.runproof_runtime.effectwitness.sdk_presend_diagnostic import MAX_BYTES, validate_sdk_error
from runtime.runproof_runtime.effectwitness.sdk_presend_probe import launch

ROOT = REPO / ".local" / "rpf-102-rev6-import"
CLIENT = client.__name__


def denial_controls(site_arg):
    folder = Path.cwd()
    site = Path(site_arg)
    client.guard(None, folder, site)

    def denied(operation, code, target):
        try:
            operation()
        except PermissionError as exc:
            row = client.error_report(exc, "SDK_IMPORT")
            assert (row["origin"], row["audit_code"], row["target"]) == ("AUDIT_HOOK", code, target)
        else:
            raise AssertionError("EXPECTED_DENIAL_MISSING")

    outside = folder.parent / "outside.txt"
    denied(outside.read_bytes, "OPEN_READ_ROOT_DENIED", "OUTSIDE_ROOTS")
    denied(lambda: outside.write_bytes(b"forbidden"), "OPEN_WRITE_ROOT_DENIED", "OUTSIDE_ROOTS")
    denied((folder / ".env").read_bytes, "OPEN_DOTENV_DENIED", "DOTENV")
    denied(lambda: sys.audit("socket.connect", None, ("203.0.113.1", 443)), "SOCKET_CONNECT_DENIED", "NETWORK")
    denied(lambda: sys.audit("socket.connect", None, ("127.0.0.1", 443)), "SOCKET_CONNECT_DENIED", "NETWORK")
    denied(lambda: sys.audit("socket.getaddrinfo", "example.invalid", 443, 0, 0, 0), "DNS_DENIED", "NETWORK")
    denied(lambda: sys.audit("subprocess.Popen", sys.executable, [], None, None), "SUBPROCESS_DENIED", "PROCESS")
    link = folder / "escape"
    linked = link.is_symlink()
    if linked:
        denied(link.read_bytes, "OPEN_READ_ROOT_DENIED", "OUTSIDE_ROOTS")
        denied(lambda: link.write_bytes(b"forbidden"), "OPEN_WRITE_ROOT_DENIED", "OUTSIDE_ROOTS")
        denied((folder / ".env.link").read_bytes, "OPEN_DOTENV_DENIED", "DOTENV")

    error = client.error_report(PermissionError("synthetic library failure"), "SDK_IMPORT")
    assert error["origin"] == "EXCEPTION" and error["audit_code"] is None and error["target"] is None
    for raw in (b"[]", b"{}", b'{"port":1,"token":1,"case":"NORMAL","site":"","folder":""}'):
        output = io.StringIO()
        with patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw))), redirect_stdout(output):
            assert client.main() == 1
        row = validate_sdk_error(strict(output.getvalue().encode()))
        assert row["stage"] == "CONFIG" and row["origin"] == "EXCEPTION"
    print(canonical({"status": "DENIAL_CONTROLS_PASS", "symlink": "PASS" if linked else "UNAVAILABLE"}).decode())
    return 0


class ImportAuditTests(unittest.TestCase):
    def run_control(self, module, call, args, folder):
        with launch(folder, module, call, args, stdout=subprocess.PIPE) as process:
            try:
                output, _ = process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                self.fail("IMPORT_ONLY_TIMEOUT")
        self.assertTrue(0 < len(output) <= MAX_BYTES, "IMPORT_ONLY_OUTPUT_BOUND")
        try:
            row = strict(output)
        except (ValueError, TypeError):
            self.fail("IMPORT_ONLY_OUTPUT_INVALID")
        return process.returncode, row

    def setUp(self):
        ensure_directory(ROOT.parent)
        ensure_directory(ROOT)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.case = Path(self.temp.name)
        self.folder = self.case / "cwd"
        self.folder.mkdir()

    def test_access_denials_and_error_origin(self):
        outside = self.case / "outside.txt"
        outside.write_bytes(b"sentinel")
        site = self.case / "site"
        site.mkdir()
        (self.folder / ".env").write_bytes(b"fictional")
        try:
            (self.folder / "escape").symlink_to(outside)
            (self.folder / ".env.link").symlink_to(self.folder / "inside")
        except (OSError, NotImplementedError):
            if os.name != "nt":
                raise
        (self.folder / "inside").write_bytes(b"sentinel")
        code, row = self.run_control("ci.test_rpf102_rev6_sdk_import", "denial_controls",
                                     [str(site)], self.folder)
        self.assertEqual(code, 0)
        self.assertEqual(set(row), {"status", "symlink"})
        self.assertEqual(row["status"], "DENIAL_CONTROLS_PASS")
        self.assertEqual(row["symlink"], "PASS" if (self.folder / "escape").is_symlink() else "UNAVAILABLE")
        print("RPF102_SYMLINK_CONTROL=" + row["symlink"])
        self.assertEqual(outside.read_bytes(), b"sentinel")

    def test_public_error_rejects_raw_paths_and_unrecognized_codes(self):
        report = client.error_report(client.AuditDenied("OPEN_READ_ROOT_DENIED", "OUTSIDE_ROOTS"), "SDK_IMPORT")
        for key, value in (("target", "/unapproved/raw"), ("audit_code", "RAW_CODE"),
                           ("stage", "arbitrary"), ("detail", "arbitrary"), ("origin", "arbitrary")):
            with self.assertRaises(Denied):
                validate_sdk_error({**report, key: value})

    @unittest.skipUnless(os.environ.get("RPF102_IMPORT_ONLY") == "1", "PINNED_HOSTED_VENV_REQUIRED")
    def test_pinned_sdk_import_only(self):
        site = Path(sysconfig.get_path("purelib")).resolve()
        self.assertNotEqual(sys.prefix, sys.base_prefix)
        self.assertTrue(site.is_relative_to(ROOT))
        code, row = self.run_control(CLIENT, "import_control", [str(site)], self.folder)
        if code != 0:
            try:
                validate_sdk_error(row)
                if not isinstance(row, dict) or "origin" not in row:
                    raise Denied("IMPORT_ONLY_DIAGNOSTIC_REQUIRED")
            except (Denied, TypeError, KeyError):
                self.fail("IMPORT_ONLY_DIAGNOSTIC_INVALID")
            self.fail("SDK_IMPORT_ONLY_NO_PHYSICAL " + canonical(row).decode())
        self.assertTrue(type(row) is dict and set(row) == {"status", "stage", "packages"})
        self.assertTrue(row["status"] == "IMPORT_ONLY_PASS" and row["stage"] == "SDK_INIT")
        self.assertTrue(type(row["packages"]) is dict and set(row["packages"]) == set(PINS))
        for name, version in PINS.items():
            package = row["packages"][name]
            self.assertTrue(type(package) is dict and set(package) == {"version", "source_sha256", "record_sha256"})
            self.assertTrue(package["version"] == version)
            for key in ("source_sha256", "record_sha256"):
                self.assertTrue(type(package[key]) is str and re.fullmatch(r"[a-f0-9]{64}", package[key]))
        print("SDK_IMPORT_ONLY_NO_PHYSICAL " + canonical(row).decode())


def prior_suite(names):
    from ci import test_rpf102_rev3_capsule as capsule_tests, test_rpf102_sdk_presend as sdk_tests
    from runtime.runproof_runtime.effectwitness import sdk_presend_contracts as contracts

    def run():
        return int(not unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromNames(names)).wasSuccessful())

    if names == ["ci.test_rpf102_rev3_capsule.FreshCheckoutBootstrapTests"]:
        with patch.object(capsule_tests, "REV5_TEST_ROOT", ROOT):
            return run()
    ensure_directory(ROOT.parent)
    ensure_directory(ROOT)
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        root = Path(tmp) / "sdk-tests"
        with (patch.object(contracts, "ROOT", root), patch.object(sdk_tests, "ROOT", root),
              patch.object(capsule_tests, "REV5_TEST_ROOT", Path(tmp) / "capsule-tests")):
            return run()


if __name__ == "__main__":
    raise SystemExit(prior_suite(sys.argv[1:]))
