"""Pure published replay / synthetic negatives. No Target or Explorer execution."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import bridge_probe as bridge


class BridgeProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = {domain: (bridge.ROOT / ref["path"]).read_bytes()
                   for domain, ref in bridge.REFS.items()}

    def project(self, domain, raw=None, anchor=None, run_id=None, *, source_kind="PUBLISHED_REPLAY"):
        ref = bridge.REFS[domain]
        return bridge.project_bytes(domain, raw if raw is not None else self.raw[domain],
            anchor or ref["sha256"], run_id or ref["run_id"], source_kind=source_kind)

    def negative_order(self, mutate):
        value = json.loads(self.raw["order"])
        mutate(value)
        value["digests"] = {k: bridge.digest(value[k]) for k in value["digests"]}
        raw = bridge.canonical(value)
        with self.assertRaisesRegex(bridge.ProjectionRejected, "SOURCE_WITNESS_REJECTED"):
            self.project("order", raw, hashlib.sha256(raw).hexdigest(), source_kind="SYNTHETIC_NEGATIVE")

    def test_two_published_sources_share_field_validation_but_keep_trust_levels(self):
        with patch.object(bridge, "validate_projection", wraps=bridge.validate_projection) as common:
            projections = bridge.published_projections()
            self.assertEqual(common.call_count, 2)
        order, config = projections["order"], projections["config"]
        self.assertEqual(order["source_kind"], "PUBLISHED_REPLAY")
        self.assertEqual(order["effect"]["outcome"], config["effect"]["outcome"])
        self.assertNotEqual(order["authority"]["scope"], config["authority"]["scope"])
        self.assertNotEqual(order["target_source"], config["target_source"])
        self.assertIsNone(config["effect"]["receipt_sha256"])
        self.assertTrue(bridge.require_claim(config, "CONTRACT_SATISFIED_IN_RETAINED_RUN"))

    def test_config_has_no_fault_activation_proof(self):
        value = self.project("config")
        self.assertEqual(value["fault"], {"planned": None, "triggered": None,
                                         "observed": None, "activation": "UNKNOWN"})
        with self.assertRaisesRegex(bridge.ProjectionRejected, "NO_FAULT_ACTIVATION_PROOF"):
            bridge.require_claim(value, "FAULT_TRIGGERED")
        value["fault"].update(planned=True, triggered=True, observed=True, activation="TRIGGERED")
        with self.assertRaisesRegex(bridge.ProjectionRejected, "CONFIG_FAULT_OR_AUTHORITY_OVERCLAIM"):
            bridge.validate_projection(value)

    def test_triggered_order_capture_does_not_establish_explorer_adaptation(self):
        value = self.project("order")
        self.assertTrue(bridge.require_claim(value, "FAULT_TRIGGERED"))
        for domain in bridge.REFS:
            with self.subTest(domain=domain), self.assertRaisesRegex(
                    bridge.ProjectionRejected, "NO_PREREGISTERED_SESSION_OR_SELECTION_LINEAGE"):
                bridge.require_claim(self.project(domain), "PGE_ADAPTATION_OBSERVED")

    def test_satisfied_effect_is_not_violation(self):
        for domain in bridge.REFS:
            with self.subTest(domain=domain), self.assertRaisesRegex(
                    bridge.ProjectionRejected, "SATISFIED_EFFECT_IS_NOT_VIOLATION"):
                bridge.require_claim(self.project(domain), "VIOLATION_CONFIRMED")

    def test_wrong_external_anchor_is_rejected_before_projection(self):
        for domain in bridge.REFS:
            with self.subTest(domain=domain), self.assertRaisesRegex(
                    bridge.ProjectionRejected, "EXTERNAL_ANCHOR_MISMATCH"):
                self.project(domain, anchor="0" * 64)

    def test_wrong_run_id_is_rejected_after_valid_source_verification(self):
        for domain in bridge.REFS:
            with self.subTest(domain=domain), self.assertRaisesRegex(
                    bridge.ProjectionRejected, "RUN_ID_MISMATCH"):
                self.project(domain, run_id="rpf54-synthetic-wrong-run")

    def test_external_only_source_cannot_gain_managed_evaluation(self):
        self.negative_order(lambda d: d["capture"].update(source_level="EXTERNAL_EVIDENCE_ONLY"))
        projection = self.project("order")
        projection["evaluation_scope"] = "EXTERNAL_EVIDENCE_ONLY"
        with self.assertRaisesRegex(bridge.ProjectionRejected, "EXTERNAL_ONLY_NOT_MANAGED"):
            bridge.validate_projection(projection)

    def test_missing_authority_is_rejected_with_recomputed_digests(self):
        self.negative_order(lambda d: d["observation"].pop("authority_after"))
        projection = self.project("config")
        projection["authority"]["refs"] = []
        with self.assertRaisesRegex(bridge.ProjectionRejected, "AUTHORITY_REQUIRED"):
            bridge.validate_projection(projection)

    def test_rehashed_cross_namespace_readback_splice_is_rejected(self):
        envelope = json.loads(self.raw["config"])
        payload = envelope["payload"]
        row = payload["http_observations"][payload["authority_after"]["current_seq"] - 1]
        row["response"]["data"]["key"] = "rpf54.synthetic.other-namespace"
        row["response_body_sha256"] = bridge.digest(row["response"])
        envelope["payload_sha256"] = bridge.digest(payload)
        raw = bridge.canonical(envelope)
        with self.assertRaisesRegex(bridge.ProjectionRejected, "SOURCE_WITNESS_REJECTED"):
            self.project("config", raw, hashlib.sha256(raw).hexdigest(), source_kind="SYNTHETIC_NEGATIVE")

    def test_same_service_reads_cannot_become_database_independent(self):
        projection = self.project("config")
        projection["authority"]["database_independence"] = "ESTABLISHED"
        with self.assertRaisesRegex(bridge.ProjectionRejected, "AUTHORITY_REQUIRED"):
            bridge.validate_projection(projection)

    def test_real_catalog_and_cross_runner_reject_direct_config_live_splice(self):
        from runtime.runproof_runtime.effectwitness.pge_contracts import SessionPlan
        from runtime.runproof_runtime.effectwitness.cross_contracts import CrossContracts
        from runtime.runproof_runtime.effectwitness import cross_trial
        from runtime.runproof_runtime.models import RuntimeFailure
        from runtime.runproof_runtime.effectwitness.witness_verify import VerificationRejected
        plan = SessionPlan.create()
        changed = plan.document
        changed["target_driver"] = "REAL_PROVIDER_TARGET"
        with self.assertRaises(RuntimeFailure):
            SessionPlan.freeze(changed)
        with self.assertRaises(RuntimeFailure):
            plan.candidate("config-http-response-lost")
        with self.assertRaises(VerificationRejected):
            CrossContracts.create("config-http", "rpf54-synthetic")
        contracts = CrossContracts.create("order", "rpf54-synthetic")
        with patch.object(cross_trial, "OrderSandbox") as sandbox:
            with self.assertRaisesRegex(RuntimeFailure, "STORAGE_TASK_REJECTED"):
                cross_trial.run_trial(contracts, storage_task="rpf-54")
            sandbox.assert_not_called()

    def test_synthetic_extra_fault_metadata_is_inert_not_activation_proof(self):
        # Inspection found that the legacy validator accepts this extra key.
        # This is an actual interface gap; production code stays unchanged.
        envelope = json.loads(self.raw["config"])
        envelope["payload"]["contracts"]["experiment"]["fault"] = "response-lost"
        envelope["payload_sha256"] = bridge.digest(envelope["payload"])
        raw = bridge.canonical(envelope)
        projection = self.project("config", raw, hashlib.sha256(raw).hexdigest(),
                                  source_kind="SYNTHETIC_NEGATIVE")
        self.assertEqual(projection["fault"]["activation"], "UNKNOWN")
        with self.assertRaisesRegex(bridge.ProjectionRejected, "SYNTHETIC_NOT_REAL_EVIDENCE"):
            bridge.require_claim(projection, "FAULT_TRIGGERED")

    def test_rpf46_research_summary_is_not_a_full_lab_session_envelope(self):
        from runtime.runproof_runtime.effectwitness.lab_evidence import verify_session
        from runtime.runproof_runtime.effectwitness.witness_verify import VerificationRejected
        summary = json.loads((bridge.ROOT / "spikes/rpf-46/session-report.json").read_bytes())
        self.assertEqual(summary["schema_version"], "rpf46-research-summary-v1")
        self.assertNotIn("plan", summary)
        self.assertNotIn("contracts", summary["trials"][0])
        with self.assertRaises(VerificationRejected):
            verify_session(summary)

    def test_import_has_no_artifact_reads_writes_or_execution(self):
        spec = importlib.util.spec_from_file_location("rpf54_import_only", HERE / "bridge_probe.py")
        module = importlib.util.module_from_spec(spec)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("artifact read at import")), \
             patch.object(Path, "open", side_effect=AssertionError("artifact open at import")):
            spec.loader.exec_module(module)
        self.assertEqual(module.KIND, "DISPOSABLE_INCOMPATIBILITY_SPIKE")

    def test_offline_guard_blocks_low_level_writes_network_and_processes(self):
        counts = {"network_attempts": 0, "child_process_attempts": 0}
        audit = bridge.offline_auditor(counts)
        outside = str(bridge.ROOT / "rpf54-synthetic-outside.txt")
        with self.assertRaisesRegex(bridge.ProjectionRejected, "OUTPUT_OUTSIDE_TASK"):
            audit("open", (outside, None, os.O_WRONLY | os.O_CREAT))
        with self.assertRaisesRegex(bridge.ProjectionRejected, "MUTATION_OUTSIDE_TASK"):
            audit("os.mkdir", (outside, 0o777, -1))
        with self.assertRaisesRegex(PermissionError, "RPF54_NETWORK_FORBIDDEN"):
            audit("socket.connect", (None, ("invalid.example", 443)))
        with self.assertRaisesRegex(PermissionError, "RPF54_CHILD_PROCESS_FORBIDDEN"):
            audit("subprocess.Popen", ("java", ["java"], None, None))
        self.assertEqual(counts, {"network_attempts": 1, "child_process_attempts": 1})


if __name__ == "__main__":
    unittest.main()
