from __future__ import annotations

import copy
import hashlib
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

from runtime.runproof_runtime.effectwitness.contracts import ROOT, canonical, owned_path
from runtime.runproof_runtime.effectwitness.effect_oracle import digest, evaluate_order_effect
from runtime.runproof_runtime.effectwitness.target_contracts import TargetContracts
from runtime.runproof_runtime.effectwitness.violation_lab import (
    DEFECT_PROFILE, NORMAL_PROFILE, _make_trial, _witness_evidence, _control_document, execute_trial,
)
from runtime.runproof_runtime.effectwitness.violation_witness import (
    SCHEMA_VERSION, WitnessRejected, issue, verify_bytes, verify_content,
)
from runtime.runproof_runtime.models import RuntimeFailure


LOCAL = ROOT / ".local" / "rpf-50"


def _refresh_document(evidence: dict) -> dict:
    return {"schema_version": SCHEMA_VERSION, "evidence": evidence,
            "content_sha256": digest(evidence)}


class ViolationWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        LOCAL.mkdir(parents=True, exist_ok=True)
        (LOCAL / "runs").mkdir(exist_ok=True)
        cls.control = execute_trial(_make_trial(NORMAL_PROFILE, "rpf50-test-control-" + uuid.uuid4().hex,
                                                "2026-10-18T00:00:00.000000Z"))
        cls.defect = execute_trial(_make_trial(DEFECT_PROFILE, "rpf50-test-defect-" + uuid.uuid4().hex,
                                               "2026-10-18T00:00:00.000000Z"))
        control_raw = _control_document(cls.control)
        cls.evidence = _witness_evidence(cls.defect, cls.control, hashlib.sha256(control_raw).hexdigest())
        cls.witness_raw = issue(cls.evidence)
        cls.anchor = hashlib.sha256(cls.witness_raw).hexdigest()

    def test_task_owned_storage_keeps_rpf48_logical_owner(self):
        contracts = TargetContracts.from_document(self.defect["contracts"])
        self.assertEqual(contracts.experiment["owner"], "rpf-48")
        self.assertEqual(self.defect["storage_task"], "rpf-50")
        with self.assertRaises(RuntimeFailure):
            owned_path(ROOT.parent / "outside-runproof" / "x", task="rpf-50")
        wrong = copy.deepcopy(self.defect["contracts"])
        wrong["experiment"]["owner"] = "rpf-50"
        with self.assertRaises(Exception):
            TargetContracts.from_document(wrong)

    def test_normal_control_uses_existing_refund_and_satisfies_oracle(self):
        self.assertEqual(self.control["effect_result"]["contract_outcome"], "CONTRACT_SATISFIED_IN_RUN")
        self.assertEqual(self.control["effect_result"]["violated_rules"], [])
        self.assertEqual(self.control["authority_before"]["data"]["receipts"], [])
        self.assertEqual(len(self.control["authority_after"]["data"]["receipts"]), 1)
        self.assertEqual(self.control["authority_after"]["data"]["order"]["refunded_minor"], 2500)
        self.assertEqual(self.control["cleanup"]["status"], "RESET_AND_REMOVED")

    def test_defect_is_committed_and_independently_read_as_violation(self):
        after = self.defect["authority_after"]["data"]
        self.assertEqual(self.defect["effect_result"]["contract_outcome"], "VIOLATION_CONFIRMED")
        self.assertEqual(self.defect["effect_result"]["violated_rules"], ["EXACTLY_ONE_FULL_REFUND_STATE"])
        self.assertEqual(after["order"]["refunded_minor"], 1250)
        self.assertEqual(after["order"]["status"], "REFUNDED")
        self.assertEqual(len(after["receipts"]), 1)
        self.assertEqual(after["receipts"][0]["amount_minor"], 2500)
        self.assertEqual(self.defect["host_steps"], 7)
        self.assertEqual(self.defect["cleanup"]["status"], "RESET_AND_REMOVED")
        self.assertNotEqual(self.control["run"]["run_id"], self.defect["run"]["run_id"])
        self.assertNotEqual(self.control["run"]["environment_id"], self.defect["run"]["environment_id"])

    def test_anchor_and_missing_anchor_statuses(self):
        verified = verify_bytes(self.witness_raw, self.anchor)
        self.assertEqual((verified["status"], verified["verdict"], verified["exit_code"]),
                         ("VERIFIED_ANCHORED", "VIOLATION_CONFIRMED", 0))
        unanchored = verify_bytes(self.witness_raw)
        self.assertEqual((unanchored["status"], unanchored["verdict"], unanchored["exit_code"]),
                         ("UNANCHORED_INCONCLUSIVE", "NOT_PROVEN", 2))
        with self.assertRaisesRegex(WitnessRejected, "EXTERNAL_ANCHOR_MISMATCH"):
            verify_bytes(self.witness_raw, "0" * 64)

    def test_rehashed_false_agent_failure_is_rejected(self):
        bad = copy.deepcopy(self.evidence)
        bad["dimensions"]["agent_fail"] = "FAIL"
        with self.assertRaisesRegex(WitnessRejected, "DIMENSION_VALUES"):
            verify_content(_refresh_document(bad))

    def test_rehashed_wrong_receipt_and_authority_owner_are_rejected(self):
        bad_receipt = copy.deepcopy(self.evidence)
        bad_receipt["authority_after"]["data"]["receipts"][0]["amount_minor"] = 1250
        bad_receipt["authority_after"]["sha256"] = digest(bad_receipt["authority_after"]["data"])
        with self.assertRaisesRegex(WitnessRejected, "AUTHORITY_RECEIPT_MISMATCH"):
            verify_content(_refresh_document(bad_receipt))

        bad_owner = copy.deepcopy(self.evidence)
        bad_owner["authority_after"]["data"]["environment"]["owner"] = "rpf-50"
        bad_owner["authority_after"]["sha256"] = digest(bad_owner["authority_after"]["data"])
        with self.assertRaisesRegex(WitnessRejected, "AUTHORITY_ENVIRONMENT_MISMATCH"):
            verify_content(_refresh_document(bad_owner))

    def test_rehashed_deleted_event_and_missing_before_are_rejected(self):
        bad_events = copy.deepcopy(self.evidence)
        del bad_events["events"][3]
        with self.assertRaisesRegex(WitnessRejected, "EVENT_COUNT"):
            verify_content(_refresh_document(bad_events))

        bad_before = copy.deepcopy(self.evidence)
        bad_before["authority_before"] = None
        with self.assertRaisesRegex(WitnessRejected, "AUTHORITY_SNAPSHOT_FIELDS"):
            verify_content(_refresh_document(bad_before))

    def test_rehashed_missing_after_duplicate_receipt_and_failed_cleanup_are_rejected(self):
        missing_after = copy.deepcopy(self.evidence)
        missing_after["authority_after"] = None
        with self.assertRaisesRegex(WitnessRejected, "AUTHORITY_SNAPSHOT_FIELDS"):
            verify_content(_refresh_document(missing_after))

        duplicate_receipt = copy.deepcopy(self.evidence)
        receipt = duplicate_receipt["authority_after"]["data"]["receipts"][0]
        duplicate_receipt["authority_after"]["data"]["receipts"].append(copy.deepcopy(receipt))
        duplicate_receipt["authority_after"]["sha256"] = digest(
            duplicate_receipt["authority_after"]["data"])
        with self.assertRaisesRegex(WitnessRejected, "AUTHORITY_RECEIPT_COUNT"):
            verify_content(_refresh_document(duplicate_receipt))

        failed_cleanup = copy.deepcopy(self.evidence)
        failed_cleanup["cleanup"]["database_removed"] = False
        with self.assertRaisesRegex(WitnessRejected, "CLEANUP_RESULT"):
            verify_content(_refresh_document(failed_cleanup))

    def test_rehashed_run_effect_profile_and_event_forgery_are_rejected(self):
        bad_run = copy.deepcopy(self.evidence)
        bad_run["run"]["order_id"] = "order-forged"
        with self.assertRaisesRegex(WitnessRejected, "RUN_IDENTITY_MISMATCH"):
            verify_content(_refresh_document(bad_run))

        old_run_identity = copy.deepcopy(self.evidence)
        old_run_identity["run"]["run_id"] = self.control["run"]["run_id"]
        with self.assertRaisesRegex(WitnessRejected, "RUN_IDENTITY_MISMATCH"):
            verify_content(_refresh_document(old_run_identity))

        bad_effect = copy.deepcopy(self.evidence)
        contracts = bad_effect["contracts"]
        contracts["effect"]["amount_minor"] = 1250
        contracts["experiment"]["effect_digest"] = digest(contracts["effect"])
        contracts["sha256"] = {key: digest(contracts[key])
                                for key in ("execution", "effect", "experiment")}
        with self.assertRaisesRegex(WitnessRejected, "CONTRACT_REJECTED"):
            verify_content(_refresh_document(bad_effect))

        bad_profile = copy.deepcopy(self.evidence)
        bad_profile["service_profile"]["registered_before_run"] = False
        with self.assertRaisesRegex(WitnessRejected, "PROFILE_IDENTITY"):
            verify_content(_refresh_document(bad_profile))

        uncommitted = copy.deepcopy(self.evidence)
        uncommitted["defect_commit"]["commit_confirmed"] = False
        with self.assertRaisesRegex(WitnessRejected, "DEFECT_COMMIT_FACTS"):
            verify_content(_refresh_document(uncommitted))

        false_activation = copy.deepcopy(self.evidence)
        false_activation["dimensions"]["defect_activation"] = "NOT_ACTIVATED"
        with self.assertRaisesRegex(WitnessRejected, "DIMENSION_VALUES"):
            verify_content(_refresh_document(false_activation))

        false_research_claim = copy.deepcopy(self.evidence)
        false_research_claim["dimensions"]["research_attribution"] = "CAUSAL"
        with self.assertRaisesRegex(WitnessRejected, "DIMENSION_VALUES"):
            verify_content(_refresh_document(false_research_claim))

        bad_event = copy.deepcopy(self.evidence)
        bad_event["events"][3]["facts"]["refunded_minor"] = 2500
        bad_event["events"][3]["facts_sha256"] = digest(bad_event["events"][3]["facts"])
        with self.assertRaisesRegex(WitnessRejected, "EVENT_ORDER_OR_FACTS"):
            verify_content(_refresh_document(bad_event))

    def test_rehash_does_not_replace_external_anchor(self):
        bad = copy.deepcopy(self.evidence)
        bad["dimensions"]["agent_exposure"] = "OBSERVED"
        raw = canonical(_refresh_document(bad))
        with self.assertRaisesRegex(WitnessRejected, "EXTERNAL_ANCHOR_MISMATCH"):
            verify_bytes(raw, self.anchor)

    def test_offline_verifier_imports_without_database_network_or_sdk_modules(self):
        code = r'''import importlib.abc, sys
blocked = ("sqlite3", "socket", "ssl", "urllib", "http", "openai", "pydantic", "pydantic_ai")
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
            raise AssertionError("blocked import: " + fullname)
        if fullname.endswith(".orders") or fullname.endswith(".violation_lab"):
            raise AssertionError("execution module imported: " + fullname)
sys.meta_path.insert(0, Block())
from runtime.runproof_runtime.effectwitness.violation_witness import verify_bytes
print("OFFLINE_IMPORT_OK")
'''
        env = dict(os.environ)
        temp = LOCAL / "tmp"
        cache = LOCAL / "pycache"
        temp.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        env.update({"TEMP": str(temp), "TMP": str(temp), "TMPDIR": str(temp),
                    "PYTHONPYCACHEPREFIX": str(cache), "PYTHONDONTWRITEBYTECODE": "1"})
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OFFLINE_IMPORT_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
