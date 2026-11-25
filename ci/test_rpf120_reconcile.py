"""Synthetic offline controls for the archived coverage diagnostic."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from ci import rpf120_reconcile as audit

DUAL = "test_effectwitness_pge_dual.DualTests.test_synthetic"
R72 = "test_effectwitness_pge_r72.BudgetTests.test_synthetic"
NATIVE = "test_effectwitness_pge_r73.FactoryContractTests.test_synthetic"
PORTABLE = "test_portable.FixtureTests."


def raw(document):
    return json.dumps(document, sort_keys=True).encode("utf-8")


def fixture():
    identity = {"run_id": "7", "attempt": "1", "commit": "a" * 40}
    authority = {"release_eligible": False, "release_executed": False, "deployment_authorized": False}
    router_counts = {"PASS": 1, "SKIP": 1, "UNAVAILABLE": 3}
    rpf87_counts = {"PASS": 2, "SKIP": 1, "UNAVAILABLE": 2}
    rpf89_counts = {"PASS": 3, "SKIP": 1, "UNAVAILABLE": 1}
    routes = {route: {} for route in audit.ROUTES}
    routes.update(PORTABLE={"PASS": 1, "SKIP": 1}, DEDICATED_RUNNER={"UNAVAILABLE": 2},
                  WINDOWS_NATIVE={"UNAVAILABLE": 1})
    handoff = identity | authority | {"schema": audit.SCHEMAS["handoff"], "evidence_kind": "SYNTHETIC_OFFLINE_TEST",
        "router_ledger_sha256": "b" * 64, "evidence_manifest_sha256": "c" * 64, "router_exit": 1,
        "counts": router_counts, "routes": routes, "unavailable_required_count": 3,
        "portable_status": "PASS", "all_required_status": "UNAVAILABLE",
        "diagnostic_continuation": "CONTINUE_DIAGNOSTIC_ONLY",
        "source_validation": {"modules": 4, "required_methods": 5, "matrix_lf_sha256": "d" * 64}}
    rows = []
    for ident, route, status, promoted in (
        (PORTABLE + "test_skip", "PORTABLE", "SKIP", False),
        (PORTABLE + "test_pass", "PORTABLE", "PASS", False),
        (DUAL, "DEDICATED_RUNNER", "UNAVAILABLE", True),
        (R72, "DEDICATED_RUNNER", "UNAVAILABLE", False),
        (NATIVE, "WINDOWS_NATIVE", "UNAVAILABLE", False),
    ):
        rows.append({"id": ident, "route": route, "required": True, "original_actual": status,
                     "effective_actual": "PASS" if promoted else status,
                     "source_lane": audit.RPF86 if promoted else audit.ORIGINAL})
    admit_a = {"router_id": DUAL, "full_id": "runtime.tests." + DUAL, "actual": "PASS", "source_lane": audit.RPF86,
               "native_receipt_sha256": "1" * 64, "journal_sha256": "2" * 64,
               "independent_receipt_sha256": "3" * 64, "manifest_sha256": "4" * 64}
    admit_b = {"router_id": R72, "full_id": "runtime.tests." + R72, "source_lane": audit.RPF88,
               "native_receipt_sha256": "5" * 64, "journal_sha256": "6" * 64,
               "verification_receipt_sha256": "7" * 64, "checkpoint_sha256": "8" * 64}
    earlier = identity | authority | {"schema": audit.SCHEMAS["rpf87"], "evidence_kind": "LOCAL_SYNTHETIC_CONTROL_ONLY",
        "original_router": {"ledger_sha256": "b" * 64, "evidence_manifest_sha256": "c" * 64, "counts": router_counts,
                            "unavailable": 3, "dedicated_unavailable": 2, "enforce_exit": 1},
        "evidence_anchors": {"router_ledger": "b" * 64, "native_receipt": "1" * 64, "native_journal": "2" * 64,
                             "independent_receipt": "3" * 64, "physical_manifest": "4" * 64},
        "effective_required": {"required": 5, "methods": rows, "counts": rpf87_counts},
        "not_admitted": None, "admitted_dedicated": [admit_a],
        "unavailable_remaining": 2, "dedicated_unavailable_remaining": 1}
    later_rows = deepcopy(rows)
    later_rows[3].update(effective_actual="PASS", source_lane=audit.RPF88)
    later = {k: v for k, v in identity.items() if k != "attempt"} | authority | {
        "run_attempt": "1", "schema": audit.SCHEMAS["rpf89"], "github_job": "canonical-release-gate",
        "evidence_kind": "LOCAL_SYNTHETIC_CONTROL_ONLY", "old_admitted": [deepcopy(admit_a)],
        "new_admitted": [admit_b], "not_admitted": None, "upstream_rpf87_counts": rpf87_counts.copy(),
        "effective_required": {"required": 5, "methods": later_rows, "counts": rpf89_counts},
        "unavailable_remaining": 1, "dedicated_unavailable_remaining": 0,
        "evidence_anchors": {"native_receipt": "5" * 64, "native_journal": "6" * 64,
                             "verify_receipt": "7" * 64, "checkpoint": "8" * 64}}
    router = identity | authority | {"schema": audit.SCHEMAS["rpf90"], "evidence_kind": "LOCAL_SYNTHETIC_CONTROL_ONLY",
        "ledger_sha256": "b" * 64, "counts": router_counts.copy(), "routes": deepcopy(routes),
        "coverage_promoted": False, "validation_status": "VALIDATED_NO_PORTABLE_ERROR"}
    return {"handoff": handoff, "rpf87": earlier, "rpf89": later, "rpf90": router}


def encode(documents):
    # Recompute the ordinary byte links so controls reach the semantic checks they target.
    digest = sha256(raw(documents["handoff"])).hexdigest()
    earlier = documents["rpf87"]
    earlier["original_router"]["status_sha256"] = digest
    earlier["evidence_anchors"]["handoff_status"] = digest
    documents["rpf89"]["evidence_anchors"]["r87"] = sha256(raw(earlier)).hexdigest()
    return {role: raw(document) for role, document in documents.items()}


class ReconciliationTests(unittest.TestCase):
    def reject(self, documents, code):
        with self.assertRaisesRegex(audit.Invalid, code):
            audit.reconcile(encode(documents), synthetic=True)

    def test_valid_reconciliation_keeps_skips_and_blocked_gate(self):
        verified = audit.reconcile(encode(fixture()), synthetic=True)
        self.assertEqual(verified["reconciliation_status"], "VALID")
        self.assertEqual(verified["coverage_gate"], "BLOCKED_BY_REQUIRED_COVERAGE")
        self.assertFalse(verified["coverage_promoted"])
        self.assertEqual(verified["release_authority"], "NONE")
        stages = verified["stages"]
        self.assertEqual([stages[name]["counts"]["UNAVAILABLE"] for name in ("router", "rpf87", "rpf89")], [3, 2, 1])
        self.assertTrue(all(stage["counts"]["SKIP"] == 1 for stage in stages.values()))
        self.assertEqual(verified["admitted_rpf87"], [DUAL])
        self.assertEqual(verified["admitted_rpf89"], [R72])
        self.assertEqual(verified["remaining"], {"count": 1, "method_ids": [NATIVE],
                                               "by_route": {"WINDOWS_NATIVE": 1},
                                               "by_module": {"test_effectwitness_pge_r73": 1}})
        by_id = {row["id"]: row for row in verified["methods"]}
        self.assertEqual(by_id[R72]["rpf87_actual"], "UNAVAILABLE")
        self.assertEqual(by_id[R72]["rpf89_source_lane"], audit.RPF88)
        self.assertEqual(by_id[DUAL]["rpf89_source_lane"], audit.RPF86)

    def test_mixed_run_attempt_and_checkout_are_rejected(self):
        for field, value in (("run_id", "8"), ("run_attempt", "2"), ("commit", "b" * 40)):
            with self.subTest(field=field):
                documents = fixture()
                documents["rpf89"][field] = value
                self.reject(documents, "MIXED_RUN")

    def test_duplicate_missing_and_replaced_methods_are_rejected(self):
        documents = fixture()
        documents["rpf87"]["effective_required"]["methods"][1]["id"] = PORTABLE + "test_skip"
        self.reject(documents, "DUPLICATE_METHOD")
        documents = fixture()
        documents["rpf89"]["effective_required"]["methods"].pop()
        self.reject(documents, "METHOD_COUNT")
        documents = fixture()
        documents["rpf89"]["effective_required"]["methods"][-1]["id"] = NATIVE + "_replacement"
        self.reject(documents, "METHOD_SET_MISMATCH")

    def test_admission_identity_uniqueness_and_proof_are_checked(self):
        documents = fixture()
        documents["rpf89"]["new_admitted"][0]["full_id"] = "runtime.tests." + DUAL
        self.reject(documents, "ADMISSION_IDENTITY")
        documents = fixture()
        old_admissions = documents["rpf87"]["admitted_dedicated"]
        old_admissions.append(deepcopy(old_admissions[0]))
        documents["rpf89"]["old_admitted"] = deepcopy(old_admissions)
        self.reject(documents, "DUPLICATE_ADMISSION")
        documents = fixture()
        documents["rpf89"]["new_admitted"][0]["native_receipt_sha256"] = "f" * 64
        self.reject(documents, "ADMISSION_ANCHOR")
        documents = fixture()
        documents["rpf89"]["old_admitted"][0]["manifest_sha256"] = "0" * 64
        self.reject(documents, "OLD_ADMISSIONS")

    def test_unadmitted_promotion_and_changed_original_are_rejected(self):
        documents = fixture()
        documents["rpf89"]["effective_required"]["methods"][-1].update(effective_actual="PASS")
        self.reject(documents, "ADMISSION_TRANSITION")
        documents = fixture()
        documents["rpf89"]["effective_required"]["methods"][0].update(original_actual="PASS")
        self.reject(documents, "ORIGINAL_METHOD_MISMATCH")

    def test_tampered_counts_and_router_observation_are_rejected(self):
        documents = fixture()
        documents["rpf89"]["effective_required"]["counts"]["UNAVAILABLE"] = 2
        self.reject(documents, "EFFECTIVE_COUNTS")
        documents = fixture()
        documents["handoff"]["routes"]["WINDOWS_NATIVE"] = {"UNAVAILABLE": True}
        self.reject(documents, "ORIGINAL_COUNTS")
        documents = fixture()
        documents["rpf90"]["ledger_sha256"] = "0" * 64
        self.reject(documents, "ROUTER_HANDOFF_MISMATCH")

    def test_byte_links_and_explicit_fixture_provenance(self):
        inputs = encode(fixture())
        with self.assertRaisesRegex(audit.Invalid, "EVIDENCE_KIND"):
            audit.reconcile(inputs)
        with self.assertRaisesRegex(audit.Invalid, "HANDOFF_ANCHOR"):
            audit.reconcile(inputs | {"handoff": inputs["handoff"] + b"\n"}, synthetic=True)
        with self.assertRaisesRegex(audit.Invalid, "UPSTREAM_ANCHOR"):
            audit.reconcile(inputs | {"rpf87": inputs["rpf87"] + b"\n"}, synthetic=True)

    def test_cli_is_deterministic_and_reads_without_modifying_files(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            inputs = encode(fixture())
            command = [sys.executable, "-B", "-m", "ci.rpf120_reconcile", "--synthetic"]
            for role, data in inputs.items():
                path = root / (role + ".json")
                path.write_bytes(data)
                command.extend(["--" + role, str(path)])
            before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
            first = subprocess.run(command, check=True, capture_output=True)
            second = subprocess.run(command, check=True, capture_output=True)
            self.assertEqual((first.stdout, first.stderr), (second.stdout, b""))
            self.assertEqual(json.loads(first.stdout)["coverage_gate"], "BLOCKED_BY_REQUIRED_COVERAGE")
            self.assertEqual({p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}, before)
            bad = fixture()
            bad["rpf89"]["run_attempt"] = "2"
            for role, data in encode(bad).items():
                (root / (role + ".json")).write_bytes(data)
            failed = subprocess.run(command, capture_output=True)
            self.assertEqual(failed.returncode, 2)
            self.assertEqual(failed.stdout, b"")
            self.assertIn(b"rpf89:MIXED_RUN", failed.stderr)


if __name__ == "__main__":
    unittest.main()
