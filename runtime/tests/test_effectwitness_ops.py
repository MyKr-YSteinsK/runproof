"""RPF-44 real SQLite controls and cross-domain/offline attack matrix; no provider."""
import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import ExitStack, closing
from pathlib import Path
from unittest.mock import patch

from runtime.runproof_runtime.models import RuntimeFailure
from runtime.runproof_runtime.effectwitness.contracts import FrozenContracts, make_contracts
from runtime.runproof_runtime.effectwitness.cross_contracts import CrossContracts
from runtime.runproof_runtime.effectwitness.cross_core import project_feedback, validate_snapshot
from runtime.runproof_runtime.effectwitness.cross_trial import run_trial
from runtime.runproof_runtime.effectwitness.engine import Budget, Orchestrator
from runtime.runproof_runtime.effectwitness.ops import OpsSandbox, OpsAuthorityReader, OpsAdapter
from runtime.runproof_runtime.effectwitness.ops_oracle import evaluate_ops_effect
from runtime.runproof_runtime.effectwitness.witness_verify import canonical, digest, verify_bytes, VerificationRejected

REPO = Path(__file__).resolve().parents[2]
TASK = REPO / ".local/rpf-45/compat-runtime/.local/rpf-44"
OLD_SHA = "ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e"


def legacy_test_scope(namespace):
    """Redirect legacy fixture owners below this task; production defaults stay intact."""
    from runtime.runproof_runtime.effectwitness import contracts, orders, exploration, pge_contracts, __main__
    scope = ExitStack()
    root = REPO / ".local/rpf-45/compat-runtime"
    local = root / ".local/rpf-41"
    pge = root / ".local/rpf-42"
    for module, name, value in ((contracts, "ROOT", root), (contracts, "LOCAL_ROOT", local),
            (orders, "LOCAL_ROOT", local), (__main__, "LOCAL_ROOT", local),
            (pge_contracts, "ROOT", root), (pge_contracts, "PGE_ROOT", pge),
            (exploration, "ROOT", root), (exploration, "PGE_ROOT", pge)):
        scope.enter_context(patch.object(module, name, value))
    for key, value in (("ROOT", root), ("PGE_ROOT", pge), ("TEST_ROOT", REPO / ".local/rpf-45/tmp/witness-tests")):
        if key in namespace:
            scope.enter_context(patch.dict(namespace, {key: value}))
    return scope


def setUpModule():
    from runtime.runproof_runtime.effectwitness import ops, cross_trial
    global _task_scope
    _task_scope = legacy_test_scope(globals())
    root = REPO / ".local/rpf-45/compat-runtime"
    _task_scope.enter_context(patch.object(ops, "ROOT", root))
    _task_scope.enter_context(patch.object(cross_trial, "ROOT", root))


def tearDownModule():
    _task_scope.close()


def refresh(bundle):
    c, o = bundle["contracts"], bundle["observation"]
    c["experiment"].update(execution_digest=digest(c["execution"]), effect_digest=digest(c["effect"]))
    c["sha256"] = {k: digest(c[k]) for k in ("execution", "effect", "experiment")}
    for key in ("authority_before", "authority_after"):
        if isinstance(o.get(key), dict):
            o[key]["sha256"] = digest(o[key]["data"])
    for event in bundle["events"]:
        event["facts_sha256"] = digest(event["facts"])
    bundle["digests"] = {k: digest(bundle[k]) for k in ("contracts", "observation", "events", "claims")}


class OpsTests(unittest.TestCase):
    def setUp(self):
        TASK.mkdir(parents=True, exist_ok=True)
        self.c = CrossContracts.create("ops", "test-" + uuid.uuid4().hex, fault="none")
        self.s = OpsSandbox(self.c)
        self.s.initialize()
        self.addCleanup(self.cleanup)
        self.r = OpsAuthorityReader(self.s.path, self.c)
        self.a = OpsAdapter(self.s)
        self.b = Budget(self.c.execution["budgets"])
        self.o = Orchestrator(self.c, self.a, self.r, self.b)
        self.args = {k: self.c.effect[k] for k in ("config_id", "operation_id", "release")}

    def cleanup(self):
        if self.s.path.exists():
            with closing(sqlite3.connect(self.s.path)) as db:
                db.execute("UPDATE environment SET owner='rpf-44',reset_generation=0")
                db.commit()
            self.s.cleanup()

    def execute(self, sql, parameters=()):
        with closing(sqlite3.connect(self.s.path)) as db:
            db.execute(sql, parameters)
            db.commit()

    def result(self):
        return self.o.effect_result(lambda before, after: evaluate_ops_effect(self.c.effect,
            self.c.experiment["environment_id"], self.r.validate(before), self.r.validate(after)))

    def test_normal_persistence_independent_reader_and_idempotent_replay(self):
        first = self.o.dispatch("apply_config", self.args)
        self.assertEqual(first["status"], "APPLIED")
        self.assertEqual(self.o.dispatch("apply_config", self.args)["status"], "IDEMPOTENT_REPLAY")
        self.assertEqual(self.r.read().public(), OpsAuthorityReader(self.s.path, self.c).read().public())
        self.assertEqual(self.result()["contract_outcome"], "CONTRACT_SATISFIED_IN_RUN")
        self.assertEqual(self.r.validate(self.r.read())["config"]["effect_count"], 1)
        self.assertEqual(self.o.dispatch("inspect_config", {"config_id": self.args["config_id"]})["release"], "release-v2")
        for changed in ({**self.args, "operation_id": "second"}, {**self.args, "release": "evil"},
                        {**self.args, "command": "anything"}):
            with self.subTest(changed=changed), self.assertRaises(RuntimeFailure):
                self.o.dispatch("apply_config", changed)
        with self.assertRaises(RuntimeFailure):
            self.s.apply(self.args["config_id"], "second", "release-v2")

    def test_dependency_and_revision_preconditions_do_not_write(self):
        for field, value in (("dependency", "UNAVAILABLE"), ("revision", 9)):
            self.execute(f"UPDATE config SET {field}=?", (value,))
            before = self.r.read().public()
            with self.assertRaisesRegex(RuntimeFailure, "CONFIG_PRECONDITION_OR_DEPENDENCY"):
                self.o.dispatch("apply_config", self.args)
            self.assertEqual(before, self.r.read().public())
            self.assertEqual(before["data"]["receipts"], [])
            self.execute("UPDATE config SET dependency='READY',revision=0")

    def test_tool_success_without_persistent_effect_is_not_business_success(self):
        with patch.object(self.s, "apply", return_value={"status": "APPLIED"}):
            self.assertEqual(self.o.dispatch("apply_config", self.args), {"status": "APPLIED"})
        result = self.result()
        self.assertEqual(result["contract_outcome"], "VIOLATION_CONFIRMED")
        self.assertEqual(len(self.r.validate(self.r.read())["receipts"]), 0)

    def test_verified_bad_state_or_receipt_is_violation_missing_authority_inconclusive(self):
        self.o.dispatch("apply_config", self.args)
        for sql, restore, rule in (
            ("UPDATE config SET release='wrong'", "UPDATE config SET release='release-v2'", "READY_DEPENDENCY_EXACTLY_ONE_CONFIG_TRANSITION"),
            ("UPDATE config SET effect_count=2", "UPDATE config SET effect_count=1", "READY_DEPENDENCY_EXACTLY_ONE_CONFIG_TRANSITION"),
            ("UPDATE receipts SET release='wrong'", "UPDATE receipts SET release='release-v2'", "OPS_RECEIPT_BOUND_TO_FROZEN_OPERATION")):
            self.execute(sql)
            result = self.result()
            self.assertEqual(result["contract_outcome"], "VIOLATION_CONFIRMED")
            self.assertIn(rule, result["violated_rules"])
            self.execute(restore)
        self.r.available = False
        self.assertEqual(self.result()["contract_outcome"], "INCONCLUSIVE")
        self.assertEqual(evaluate_ops_effect(self.c.effect, "env", None, None)["contract_outcome"], "INCONCLUSIVE")

    def test_online_seal_owner_and_generation_fail_closed(self):
        snap = self.r.read()
        other = OpsAuthorityReader(self.s.path, self.c)
        with self.assertRaisesRegex(RuntimeFailure, "AUTHORITY_HASH_OR_ISSUER_MISMATCH"):
            other.validate(snap)
        with self.assertRaises(RuntimeFailure):
            self.r.validate({"data": snap.public()["data"]})
        self.execute("UPDATE environment SET owner='other'")
        with self.assertRaisesRegex(RuntimeFailure, "AUTHORITY_ENVIRONMENT_IDENTITY"):
            self.r.validate(self.r.read())
        self.execute("UPDATE environment SET owner='rpf-44'")
        self.s.cleanup()
        with self.assertRaisesRegex(RuntimeFailure, "ENVIRONMENT_RESET_REQUIRES_NEW_EXPERIMENT"):
            self.s.apply(**self.args)

    def test_unknown_blocks_retry_and_missing_receipt_stays_pending(self):
        c = CrossContracts.create("ops", self.c.experiment["run_id"], "response-lost")
        self.s.contracts = c
        reader, adapter = OpsAuthorityReader(self.s.path, c), OpsAdapter(self.s)
        o = Orchestrator(c, adapter, reader, Budget(c.execution["budgets"]))
        self.assertEqual(o.dispatch("apply_config", self.args)["status"], "UNKNOWN_OUTCOME")
        with self.assertRaisesRegex(RuntimeFailure, "RECONCILE_REQUIRED_BEFORE_TOOL"):
            o.dispatch("apply_config", self.args)
        reader.available = False
        with self.assertRaises(RuntimeFailure):
            o.reconcile()
        self.assertIsNotNone(o.pending)
        self.assertEqual(o.effect_result(None)["contract_outcome"], "INCONCLUSIVE")
        reader.available = True
        self.assertEqual(o.reconcile()["status"], "RECONCILED_COMMITTED")
        self.assertIsNone(o.pending)
        self.assertEqual(reader.validate(reader.read())["config"]["effect_count"], 1)


class CrossWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundles = {}
        for domain in ("order", "ops"):
            c = CrossContracts.create(domain, "test-" + uuid.uuid4().hex)
            def check(sandbox, observation):
                assert sandbox.path.is_file()
                assert observation["effect"]["contract_outcome"] == "CONTRACT_SATISFIED_IN_RUN"
            bundle, usage = run_trial(c, before_cleanup_hook=check)
            assert not (TASK / c.experiment["run_id"]).exists()
            assert usage["steps"] == 7 and usage["provider_requests"] == 0
            cls.bundles[domain] = bundle

    def reject_mutation(self, mutation, reason=None):
        bundle = copy.deepcopy(self.bundles["ops"])
        mutation(bundle)
        refresh(bundle)
        raw = canonical(bundle)
        with self.assertRaises(VerificationRejected) as caught:
            verify_bytes(raw, hashlib.sha256(raw).hexdigest())
        if reason:
            self.assertEqual(caught.exception.code, reason)

    def test_two_actual_domains_same_dispatch_and_recomputable_feedback(self):
        for domain, bundle in self.bundles.items():
            raw = canonical(bundle)
            self.assertEqual(verify_bytes(raw, hashlib.sha256(raw).hexdigest())["status"], "VERIFIED_ANCHORED")
            self.assertEqual(verify_bytes(raw)["status"], "UNANCHORED_INCONCLUSIVE")
            o = bundle["observation"]
            self.assertEqual(o["feedback"], project_feedback(domain, o["effect"], o["fault"]))

    def test_domain_version_tool_and_extra_fields_cannot_select_execution(self):
        mutations = [lambda b: b.update(domain="os.system"), lambda b: b.update(oracle_version="99"),
            lambda b: b.update(schema_version="unknown"), lambda b: b.update(command="touch forbidden"),
            lambda b: b["contracts"]["execution"].update(tools=["exec"]),
            lambda b: b["contracts"]["effect"].update(endpoint="https://invalid"),
            lambda b: b["contracts"]["experiment"].update(schema_version="rpf-experiment-v3"),
            lambda b: b["observation"]["tool_calls"][0].update(name="exec")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.reject_mutation(mutation)

    def test_identity_receipts_tools_feedback_and_fault_attack_matrix(self):
        mutations = [lambda b: b["contracts"]["experiment"].update(owner="rpf-43"),
            lambda b: b["observation"]["authority_after"]["data"]["environment"].update(environment_id="other"),
            lambda b: b["observation"]["authority_after"]["data"].update(reader_id="tool-reader"),
            lambda b: b["observation"]["authority_after"]["data"].update(receipts=[]),
            lambda b: b["observation"]["authority_after"]["data"]["receipts"].append(
                copy.deepcopy(b["observation"]["authority_after"]["data"]["receipts"][0])),
            lambda b: b["observation"]["authority_after"]["data"]["receipts"][0].update(operation_id="other"),
            lambda b: b["observation"]["tool_calls"][0]["result"].update(status="APPLIED"),
            lambda b: b["observation"].update(authority_before=None),
            lambda b: b["observation"]["feedback"].update(contract_outcome="VIOLATION_CONFIRMED"),
            lambda b: b["observation"]["fault"].update(triggered=False),
            lambda b: b["capture"].update(source_level="EXTERNAL_EVIDENCE_ONLY")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.reject_mutation(mutation)

    def test_event_and_claim_attack_matrix(self):
        self.reject_mutation(lambda b: b["events"][1].update(event_id=b["events"][0]["event_id"]), "EVENT_IDENTITY")
        self.reject_mutation(lambda b: b["events"][1].update(observed_at="2000-01-01T00:00:00+00:00"), "EVENT_TIME_ORDER")
        self.reject_mutation(lambda b: b["events"].reverse(), "EVENT_ORDER")
        self.reject_mutation(lambda b: b["claims"].update(reproduction="REPRODUCED"), "CLAIM_OVERREACH_OR_MISMATCH")
        self.reject_mutation(lambda b: b["claims"].update(attribution_strength="CAUSAL"), "CLAIM_OVERREACH_OR_MISMATCH")

    def test_canonical_size_duplicate_anchor_and_legacy_golden(self):
        raw = canonical(self.bundles["ops"])
        for bad, reason in ((raw + b'\n', "BUNDLE_NOT_CANONICAL"),
                (b'{"x":0,"x":1}', "DUPLICATE_JSON_KEY"), (b' ' * (128*1024+1), "BUNDLE_SIZE")):
            with self.assertRaisesRegex(VerificationRejected, reason):
                verify_bytes(bad)
        changed = copy.deepcopy(self.bundles["ops"])
        changed["claims"]["reproduction"] = "REPRODUCED"
        refresh(changed)
        with self.assertRaisesRegex(VerificationRejected, "FILE_SHA256_MISMATCH"):
            verify_bytes(canonical(changed), hashlib.sha256(raw).hexdigest())
        old = (REPO / "spikes/rpf-43/sample-witness.json").read_bytes()
        self.assertEqual(len(old), 9257)
        self.assertEqual(hashlib.sha256(old).hexdigest(), OLD_SHA)
        self.assertEqual(verify_bytes(old, OLD_SHA)["status"], "VERIFIED_ANCHORED")
        self.assertEqual(verify_bytes(old)["status"], "UNANCHORED_INCONCLUSIVE")
        with self.assertRaisesRegex(VerificationRejected, "FILE_SHA256_MISMATCH"):
            verify_bytes(old, "0"*64)
        legacy = make_contracts("strict-owner")
        for schema in ("rpf-experiment-v1", "rpf-experiment-v2", "rpf-experiment-v3"):
            with self.assertRaises(RuntimeFailure):
                FrozenContracts.freeze(legacy.execution, legacy.effect,
                    {**legacy.experiment, "schema_version": schema, "owner": "rpf-44"})

    def test_planned_untriggered_normal_and_zero_provider_budget(self):
        c = CrossContracts.create("ops", "test-" + uuid.uuid4().hex, "planned-not-triggered")
        b, usage = run_trial(c)
        self.assertEqual(b["claims"]["fault_activation"], "NOT_TRIGGERED")
        self.assertEqual(b["claims"]["contract_outcome"], "CONTRACT_SATISFIED_IN_RUN")
        self.assertEqual(usage["provider_requests"], 0)
        with self.assertRaisesRegex(RuntimeFailure, "BUDGET_REQUESTS_EXHAUSTED"):
            Budget(c.execution["budgets"]).reserve_request(0, 0)

    def test_failed_reconciliation_is_quarantined_without_reset_or_retry(self):
        from runtime.runproof_runtime.effectwitness import contracts as storage
        c = CrossContracts.create("ops", "test-" + uuid.uuid4().hex)
        quarantine = storage.ROOT / ".local/quarantine/rpf-44" / c.experiment["run_id"]
        with patch.object(OpsAuthorityReader, "reconcile", side_effect=RuntimeFailure("ENVIRONMENT", "READ_UNAVAILABLE")):
            with self.assertRaisesRegex(RuntimeFailure, "READ_UNAVAILABLE"):
                run_trial(c)
        self.assertTrue((quarantine / "ops.sqlite3").is_file())
        try:
            with closing(sqlite3.connect(quarantine / "ops.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT release,effect_count FROM config").fetchone(), ("release-v2", 1))
                self.assertEqual(db.execute("SELECT count(*) FROM receipts").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT reset_generation FROM environment").fetchone()[0], 0)
        finally:
            # Test fixture is now inspected/resolved. Restore ownership path for normal reset.
            restored = TASK / c.experiment["run_id"]
            quarantine.rename(restored)
            sandbox = OpsSandbox(c)
            sandbox.cleanup()

    def test_malformed_nested_shapes_and_boolean_budget_are_rejected(self):
        mutations = [lambda b: b["contracts"].update(experiment=[]),
            lambda b: b["observation"].update(fault=[]),
            lambda b: b["observation"]["authority_after"]["data"].update(environment=[]),
            lambda b: b["contracts"]["execution"]["budgets"].update(provider_requests=False)]
        for mutation in mutations:
            bundle = copy.deepcopy(self.bundles["ops"])
            mutation(bundle)
            with self.subTest(mutation=mutation), self.assertRaises(VerificationRejected):
                verify_bytes(canonical(bundle))

    def test_offline_subprocess_blocks_database_network_provider_and_executor(self):
        folder = TASK / "tmp"
        folder.mkdir(parents=True, exist_ok=True)
        code = """import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in ('sqlite3','socket','docker') or fullname.endswith(('.provider','.pge_provider','.engine','.orders','.ops','.cross_trial')):
            raise AssertionError('forbidden import: '+fullname)
sys.meta_path.insert(0,Block())
from runtime.runproof_runtime.effectwitness.witness_verify import main
raise SystemExit(main())
"""
        env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        env.update(PYTHONDONTWRITEBYTECODE="1", TEMP=str(folder), TMP=str(folder), TMPDIR=str(folder))
        raw_cases = [canonical(b) for b in self.bundles.values()]
        raw_cases.append((REPO / "spikes/rpf-43/sample-witness.json").read_bytes())
        for raw in raw_cases:
            with tempfile.TemporaryDirectory(dir=folder) as temp:
                path = Path(temp) / "bundle.json"
                path.write_bytes(raw)
                for anchor, expected in ((hashlib.sha256(raw).hexdigest(), 0), (None, 2), ("0"*64, 3)):
                    command = [sys.executable, "-c", code, str(path)]
                    if anchor:
                        command.extend(("--expected-sha256", anchor))
                    result = subprocess.run(command, cwd=REPO, env=env, capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
