"""In-memory rejection controls for the archived public projection."""
import json
import unittest

from ci import rpf103_verify_archive as archive
from runtime.runproof_runtime.effectwitness.sdk_presend_contracts import canonical, sha


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = archive.unpack(archive.ARCHIVE.read_bytes())

    def reanchor(self, changes=None, **identity):
        files = {**self.original, **(changes or {})}
        manifest = json.loads(files["manifest.json"])
        manifest.update(identity)
        for name, raw in (changes or {}).items():
            entry = manifest["files"][name]
            entry.update(bytes=len(raw), sha256=sha(raw))
            if not entry["nonce_projected"]:
                entry["original_sha256"] = entry["sha256"]
        files["manifest.json"] = canonical(manifest)
        return files, sha(files["manifest.json"])

    def test_published_zip(self):
        result = archive.verify_archive(archive.ARCHIVE)
        self.assertEqual((result["indexed_members"], result["zip_members"], result["nonce_projected_members"]),
                         (32, 33, 10))
        self.assertEqual(result["cases"]["NORMAL"]["received_bytes"], 1092)
        case = result["cases"]["UNKNOWN"]
        self.assertEqual((case["received_bytes"], case["unknown_seq"], case["post_unknown_reserves"],
                          case["post_unknown_send_entries"]), (421, 8, 0, 0))

    def test_one_byte_changed(self):
        name = "NORMAL/sdk-post-1.raw"
        raw = self.original[name]
        with self.assertRaisesRegex(ValueError, "CAPSULE_MEMBER_HASH"):
            archive.verify_members({**self.original, name: bytes([raw[0] ^ 1]) + raw[1:]})

    def test_missing_or_extra_member(self):
        files = dict(self.original)
        del files["UNKNOWN/receiver-1.raw"]
        for value in (files, {**self.original, "unexpected": b"data"}):
            with self.assertRaisesRegex(ValueError, "CAPSULE_EXTRA"):
                archive.verify_members(value)

    def test_reanchored_owner_substitution(self):
        files, anchor = self.reanchor(owner="1" * 32)
        with self.assertRaisesRegex(ValueError, "CAPSULE_IDENTITY"):
            archive.verify_members(files, manifest_anchor=anchor)

    def test_reanchored_run_and_source_substitution(self):
        for identity in ({"github_run_id": archive.RUN_ID + 1}, {"source_git_sha": "2" * 40}):
            files, anchor = self.reanchor(**identity)
            with self.assertRaisesRegex(ValueError, "CAPSULE_IDENTITY"):
                archive.verify_members(files, manifest_anchor=anchor)

    def test_reanchored_post_unknown_reservation_and_send(self):
        name = "UNKNOWN/wal.jsonl"
        original = self.original[name]
        rows = [json.loads(line) for line in original.splitlines()]
        for kind in ("PROVIDER_RESERVE", "SEND_ENTRY"):
            body = next(row["body"] for row in rows if row["kind"] == kind)
            row = {"seq": len(rows), "prev": rows[-1]["sha256"], "kind": kind, "body": body}
            raw = original + canonical({**row, "sha256": sha(canonical(row))}) + b"\n"
            files, anchor = self.reanchor({name: raw})
            with self.assertRaisesRegex(ValueError, f"POST_UNKNOWN_{kind}"):
                archive.verify_members(files, manifest_anchor=anchor)

    def test_reanchored_duplicated_receiver(self):
        files, anchor = self.reanchor({"NORMAL/receiver-2.json": self.original["NORMAL/receiver-1.json"]})
        with self.assertRaisesRegex(ValueError, "RECEIVER_BYTES"):
            archive.verify_members(files, manifest_anchor=anchor)

    def test_reanchored_private_field(self):
        name = "NORMAL/sdk-launch.json"
        raw = canonical({**json.loads(self.original[name]), "authorization": "fictional"})
        files, anchor = self.reanchor({name: raw})
        with self.assertRaisesRegex(ValueError, "PRIVATE_FIELD"):
            archive.verify_members(files, manifest_anchor=anchor)
