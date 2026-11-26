"""Portable controls for the RPF-124 runner. No original methods are executed."""
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import rpf124_r72r2 as tool


class Rpf124ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {
            name: (tool.REPO / name).read_bytes().replace(b"\r\n", b"\n")
            for name in tool.source_paths()
        }

    def test_pinned_source_and_matrix(self):
        observed = tool.source_identity(self.files)
        self.assertEqual(observed["files"], 76)
        self.assertEqual(observed["capsule_sha256"], tool.CAPSULE_SHA)

    def test_source_drift_rejected(self):
        for name, reason in (
            (tool.TEST, "FROZEN_TEST_SHA"),
            (tool.MATRIX, "FROZEN_MATRIX_SHA"),
            ("runtime/runproof_runtime/effectwitness/pge_r68_budget.py", "FROZEN_SOURCE_CAPSULE_SHA"),
        ):
            with self.subTest(name=name):
                changed = {**self.files, name: self.files[name] + b"\n"}
                with self.assertRaisesRegex(tool.Refused, reason):
                    tool.source_identity(changed)

    def test_existing_or_outside_output_is_rejected(self):
        candidate = tool.REPO / tool.TASK_ROOT / "a-new-run"
        with patch.object(tool, "plain", return_value=None):
            self.assertEqual(tool.task_directory(candidate, tool.REPO, fresh=True), candidate)
        with patch.object(tool, "plain", return_value=object()):
            with self.assertRaisesRegex(tool.Refused, "OUTPUT_EXISTS"):
                tool.task_directory(candidate, tool.REPO, fresh=True)
        with self.assertRaisesRegex(tool.Refused, "OUTPUT_SCOPE"):
            tool.task_directory(tool.REPO / ".local" / "old-run", tool.REPO, fresh=True)

    @staticmethod
    def observation(binding):
        row = {"binding": binding, "id": tool.IDS[0], "status": "PASS", "denied": [], "test_count": 1,
               "pid": 1234, "owner": "rpf72r2-0123456789abcdef", "database": None, "sqlite_connections": {}}
        log = tool.MARKER + tool.canonical(row) + b"\n"
        receipt = {"binding": binding, "argv": tool.child_argv(binding, 0), "id": tool.IDS[0],
                   "exit": 0, "timed_out": False, "pid": row["pid"], "log_sha256": tool.sha(log)}
        return log, receipt

    def test_modified_log_rejected(self):
        binding = "a" * 64
        log, receipt = self.observation(binding)
        self.assertEqual(tool.original_observation(log, receipt, binding, 0)["status"], "PASS")
        with self.assertRaisesRegex(tool.Refused, "LOG_DIGEST_MISMATCH"):
            tool.original_observation(b"changed\n" + log, receipt, binding, 0)

    def test_swapped_record_rejected_even_with_matching_log_digest(self):
        binding = "a" * 64
        log, receipt = self.observation(binding)
        other = "b" * 64
        with self.assertRaisesRegex(tool.Refused, "PROCESS_RUN_BINDING"):
            tool.original_observation(log, receipt, other, 0)
        changed_receipt = {**receipt, "binding": other, "argv": tool.child_argv(other, 0)}
        with self.assertRaisesRegex(tool.Refused, "ORIGINAL_RECEIPT_BINDING"):
            tool.original_observation(log, changed_receipt, other, 0)

    def test_failed_process_is_not_a_verified_assertion(self):
        binding = "a" * 64
        log, receipt = self.observation(binding)
        with self.assertRaisesRegex(tool.Refused, "ORIGINAL_PROCESS_FAILED"):
            tool.original_observation(log, {**receipt, "exit": 1}, binding, 0)

    def test_owner_id_cannot_select_another_directory(self):
        with self.assertRaisesRegex(tool.Refused, "OWNER_ID"):
            tool.owned_paths("../rpf72r2-0123456789abcdef", 2)
        wal, database = tool.owned_paths("rpf72r2-0123456789abcdef", 2)
        self.assertEqual(wal.name, "wal.jsonl")
        self.assertEqual(database.parent, wal.parent / Path("runs/rpf72r2-0123456789abcdef-2/business"))
