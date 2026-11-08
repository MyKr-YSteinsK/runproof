import unittest
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from integrations.jiuwenswarm import recorded_sources as sources
from runtime.runproof_runtime.effectwitness.witness_verify import VerificationRejected, verify_bytes

class SourceTests(unittest.TestCase):
    def test_pinned_sources(self):
        self.assertEqual(sources.inspect("rpf46-summary")["verification_status"], "HASH_AND_COMMIT_VERIFIED")
        for source in ("rpf43-order-sample", "rpf44-ops-sample"):
            self.assertEqual(sources.witness(source)["verification_status"], "VERIFIED_ANCHORED")
    def test_invalid_paths_and_wrong_anchor_rejected(self):
        for source in ("../../file", "file:///secret", "rpf46-summary"):
            with self.assertRaises(sources.SourceError): sources.witness(source)
        with self.assertRaises(VerificationRejected): verify_bytes(b"{}", "0" * 64)
        with self.assertRaises(VerificationRejected): verify_bytes(b'{"a":1,"a":2}')

    def test_missing_source_fails_closed(self):
        owner = Path(sys.executable).resolve().parents[2]
        with TemporaryDirectory(dir=owner) as root, patch.object(sources, "ROOT", Path(root)):
            with self.assertRaisesRegex(sources.SourceError, "SOURCE_UNAVAILABLE"):
                sources.verified_sources()
