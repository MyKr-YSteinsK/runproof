"""Byte-identical preservation and repacking controls."""
from io import BytesIO
import unittest
from zipfile import ZipFile

from ci.rpf108_verify_archive import ARCHIVE, verify_archive


class ArchiveTests(unittest.TestCase):
    def test_exact_original_and_distinct_effects(self):
        row = verify_archive(ARCHIVE.read_bytes())
        self.assertEqual(row["real_explorer"], "NOT_RUN")
        self.assertEqual(row["issuer"], "NOT_ESTABLISHED")
        self.assertEqual(row["external_provider_requests"], 0)
        self.assertEqual([r["authority"]["effect"] for r in row["cases"]], [
            {"effect_count": 1, "release": "release-v2", "revision": 1},
            {"refunded_minor": 2500, "revision": 1, "status": "REFUNDED"}])
        for case in row["cases"]:
            self.assertEqual(case["post_unknown_inbound_model_post"], 1)
            self.assertEqual(case["post_unknown_model_reservations"], 0)

    def test_repacked_metadata_and_unexpected_member_reject(self):
        original = ARCHIVE.read_bytes()
        with ZipFile(BytesIO(original)) as archive:
            inner = archive.read("public.zip")
        for name in ("public.zip", "../public.zip", "other.zip"):
            stream = BytesIO()
            with ZipFile(stream, "w") as archive:
                archive.writestr(name, inner)
            with self.assertRaisesRegex(ValueError, "ACTIONS_ARCHIVE_IDENTITY"):
                verify_archive(stream.getvalue())
        with self.assertRaisesRegex(ValueError, "ACTIONS_ARCHIVE_IDENTITY"):
            verify_archive(original[:-1] + bytes([original[-1] ^ 1]))
