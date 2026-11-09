"""Positive and in-memory negative controls for both ZIP layers and public replay."""
from copy import deepcopy
from io import BytesIO
import unittest
import warnings
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from ci import rpf105_verify_archive as archive
from ci.rpf103_verify_archive import scan
from runtime.runproof_runtime.effectwitness import product_sdk_capsule as capsule
from runtime.runproof_runtime.effectwitness.product_sdk_oracle import verify_case
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, sha, strict


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = archive.ARCHIVE.read_bytes()
        cls.inner = archive.outer_payload(cls.raw)
        with ZipFile(BytesIO(cls.inner)) as container:
            cls.files = {name: container.read(name) for name in container.namelist()}

    def test_original_actions_zip(self):
        result = archive.verify_archive()
        self.assertEqual(result["manifest_sha256"], archive.MANIFEST_SHA)
        self.assertEqual(result["cases"]["NORMAL"]["business_writes"], 2)
        self.assertEqual(result["cases"]["UNKNOWN"]["business_writes"], 1)
        self.assertEqual(result["cases"]["UNKNOWN"]["post_unknown"], dict.fromkeys(archive.AFTER_UNKNOWN, 0))

    def test_outer_identity_and_unsafe_member(self):
        with self.assertRaisesRegex(ValueError, "ACTIONS_ANCHOR"):
            archive.verify_bytes(self.raw[:-1] + bytes([self.raw[-1] ^ 1]))
        for names in (("../public.zip",), ("public.zip", "extra"), ("PUBLIC.ZIP",), ("public.zip", "public.zip")):
            output = BytesIO()
            with warnings.catch_warnings(), ZipFile(output, "w", ZIP_DEFLATED) as container:
                warnings.filterwarnings("ignore", message="Duplicate name:", category=UserWarning)
                for name in names:
                    container.writestr(name, b"fixture")
            with self.assertRaisesRegex(ValueError, "ACTIONS_MEMBERS"):
                archive.outer_payload(output.getvalue())

    def test_outer_crc_and_bounds(self):
        bad = bytearray(self.raw)
        index = bad.index(b"PK\x01\x02")
        bad[index + 16] ^= 1
        with self.assertRaises(BadZipFile):
            archive.outer_payload(bytes(bad))
        with self.assertRaisesRegex(ValueError, "ACTIONS_SIZE"):
            archive.outer_payload(self.raw + bytes(16385))

    def test_inner_hash_members_and_owner(self):
        with self.assertRaisesRegex(ValueError, "ZIP_BOUND"):
            capsule.verify_zip(self.inner[:-1], archive.SOURCE, archive.RUN, archive.OWNER,
                               zip_sha=archive.INNER_SHA)
        with self.assertRaisesRegex(ValueError, "CAPSULE_COMPLETE"):
            capsule.verify_zip(capsule.pack({k: v for k, v in self.files.items() if k != "UNKNOWN.json"}),
                               archive.SOURCE, archive.RUN, archive.OWNER, require_complete=True)
        with self.assertRaisesRegex(ValueError, "MANIFEST_IDENTITY"):
            capsule.verify_zip(self.inner, archive.SOURCE, archive.RUN, "f" * 32)

    def test_reanchored_unknown_effect_is_rejected(self):
        case = strict(self.files["UNKNOWN.json"])
        last = case["wal"][-1]
        for kind in sorted(archive.AFTER_UNKNOWN):
            forged = deepcopy(case)
            row = {"seq": len(case["wal"]), "prev": last["sha256"], "kind": kind,
                   "time_ns": last["time_ns"], "body": {}}
            forged["wal"].append({**row, "sha256": sha(canonical(row))})
            with self.assertRaisesRegex(ValueError, "POST_UNKNOWN_EFFECT"):
                verify_case(forged)

    def test_unlisted_event_and_receiver_replacement(self):
        case = strict(self.files["NORMAL.json"])
        last = case["wal"][-1]
        row = {"seq": len(case["wal"]), "prev": last["sha256"], "kind": "UNLISTED",
               "time_ns": last["time_ns"], "body": {}}
        with self.assertRaisesRegex(ValueError, "TERMINAL_BINDING"):
            verify_case({**case, "wal": [*case["wal"], {**row, "sha256": sha(canonical(row))}]})
        case["transfers"][1]["receiver"] = case["transfers"][0]["receiver"]
        with self.assertRaisesRegex(ValueError, "TRANSFER_BINDING"):
            verify_case(case)

    def test_privacy_patterns_and_fields(self):
        for row in ({"token": "fictional"}, {"a": "/home/fictional/private"},
                    {"a": "Bearer fictional"}, {"a": "C:\\Users\\fictional"}):
            with self.assertRaisesRegex(ValueError, "PUBLIC_SCOPE"):
                capsule.safe_public(canonical(row))
        with self.assertRaisesRegex(ValueError, "PRIVATE_FIELD"):
            scan({"access_token": "fictional"})
