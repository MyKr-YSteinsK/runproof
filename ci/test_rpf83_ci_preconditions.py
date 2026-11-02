"""Stdlib-only RPF-60 harness admission tests, never its nine business methods.

Fresh synthetic directories are retained under ci-results/rpf83-*. No legacy
owner is opened. The harness is imported without calling unittest discovery.
"""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

from runtime.tests import test_effectwitness_lab_cross_domain as harness

ROOT = Path(__file__).resolve().parents[1]


class CiPreconditionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = os.environ.get("GITHUB_RUN_ID", "local")
        attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
        if not (run == "local" or (run.isascii() and run.isdecimal())):
            raise ValueError("RPF83_FIXTURE_RUN_ID")
        if not (attempt.isascii() and attempt.isdecimal()):
            raise ValueError("RPF83_FIXTURE_RUN_ATTEMPT")
        cls.fixture = ROOT / "ci-results" / f"rpf83-preconditions-{run}-{attempt}-{uuid.uuid4().hex}"
        if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
               for p in (cls.fixture, *cls.fixture.parents)):
            raise ValueError("RPF83_FIXTURE_REPARSE")
        cls.fixture.mkdir(parents=True, exist_ok=False)

    def setUp(self):
        self.run_id = str(uuid.uuid4().int)
        self.checkout = self.fixture / uuid.uuid4().hex / "checkout"
        self.checkout.mkdir(parents=True, exist_ok=False)
        root_patch = patch.object(harness.c, "ROOT", self.checkout)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.owner = self.checkout / "ci-results" / f"rpf83-r60-{self.run_id}-1"
        self.env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "PATH")
                    if key in os.environ}
        self.env.update(GITHUB_ACTIONS="true", GITHUB_WORKSPACE=str(self.checkout),
                        GITHUB_RUN_ID=self.run_id, GITHUB_RUN_ATTEMPT="1",
                        RPF82_TEST_ROOT=str(self.owner))
        self.assertFalse(os.path.lexists(self.owner))
        self.assertFalse(any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                             for p in (self.owner, *self.owner.parents)))

    def test_missing_env_fails_before_directory_creation(self):
        self.env.pop("RPF82_TEST_ROOT")
        with patch.dict(os.environ, self.env, clear=True):
            with self.assertRaises(KeyError):
                harness.setUpModule()
        self.assertFalse(os.path.lexists(self.owner))

    def test_fresh_ci_owner_is_created_once_and_propagated(self):
        original = harness.c.WORK
        with patch.dict(os.environ, self.env, clear=True):
            try:
                harness.setUpModule()
                self.assertEqual(harness.c.WORK, self.owner)
                self.assertTrue((self.owner / "rpf60-tests").is_dir())
                self.assertEqual(harness._test_owner(str(self.owner)), self.owner)
                with self.assertRaisesRegex(ValueError, "TEST_OWNER_OCCUPIED"):
                    harness.setUpModule()
            finally:
                harness.tearDownModule()
        self.assertEqual(harness.c.WORK, original)

    def test_preoccupied_root_is_not_reused(self):
        self.owner.mkdir(parents=True, exist_ok=False)
        marker = self.owner / "synthetic-marker.txt"
        marker.write_bytes(b"RPF83 synthetic fixture")
        with patch.dict(os.environ, self.env, clear=True):
            with self.assertRaisesRegex(ValueError, "TEST_OWNER_OCCUPIED"):
                harness.setUpModule()
        self.assertEqual(marker.read_bytes(), b"RPF83 synthetic fixture")
        self.assertFalse((self.owner / "rpf60-tests").exists())

    def test_escape_and_unauthorized_owner_fail_lexically(self):
        with patch.dict(os.environ, self.env, clear=True):
            for path in ("relative-owner", str(self.checkout / "ci-results"),
                         str(self.checkout / "ci-results" / ".." / "escape"),
                         str(self.checkout / ".local" / "rpf83-not-authorized"),
                         str(self.checkout.parent / "outside")):
                with self.subTest(case=Path(path).name):
                    with self.assertRaisesRegex(ValueError, "TEST_OWNER_SCOPE"):
                        harness._test_owner(path)
        self.assertFalse(os.path.lexists(self.owner))

    def test_ci_identity_mismatch_is_rejected(self):
        for key, value in (("GITHUB_WORKSPACE", str(self.checkout.parent)),
                           ("GITHUB_RUN_ID", "other"),
                           ("GITHUB_RUN_ATTEMPT", "2")):
            with self.subTest(field=key):
                with patch.dict(os.environ, dict(self.env, **{key: value}), clear=True):
                    with self.assertRaisesRegex(ValueError, "TEST_OWNER_CI_IDENTITY"):
                        harness._test_owner(str(self.owner))
        self.assertFalse(os.path.lexists(self.owner))

    def test_actual_symlink_or_junction_is_rejected(self):
        target = self.checkout / "ci-results" / f"rpf83-link-target-{self.run_id}"
        self.assertFalse(os.path.lexists(target))
        target.mkdir(parents=True, exist_ok=False)
        try:
            self.owner.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                raise
            # CPython stdlib fallback needs no shell or process creation.
            import _winapi
            _winapi.CreateJunction(str(target), str(self.owner))
        self.assertTrue(self.owner.is_symlink()
                        or getattr(self.owner, "is_junction", lambda: False)())
        with patch.dict(os.environ, self.env, clear=True):
            with self.assertRaisesRegex(ValueError, "TEST_OWNER_REPARSE"):
                harness._test_owner(str(self.owner))
        self.assertFalse((target / "rpf60-tests").exists())


if __name__ == "__main__":
    unittest.main()
