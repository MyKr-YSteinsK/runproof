"""RPF-43 Witness integrity, downgrade and offline-process tests; no database or Provider calls."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from runtime.runproof_runtime.effectwitness.contracts import FrozenContracts, digest, make_contracts, owned_path
from runtime.runproof_runtime.effectwitness.exploration import SessionBudget, run_trial
from runtime.runproof_runtime.effectwitness.pge_contracts import LIMITS
from runtime.runproof_runtime.models import RuntimeFailure
from runtime.runproof_runtime.effectwitness.witness_verify import (
    EVENT_ORDER, VerificationRejected, canonical, verify_bytes, _derive_fault_activation)
from runtime.runproof_runtime.effectwitness.witness import _final_bundle, _precleanup_capture

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT
TEST_ROOT = REPO_ROOT / ".local" / "rpf-45" / "tmp" / "witness-tests"


def setUpModule():
    from runtime.tests.test_effectwitness_ops import legacy_test_scope
    global _task_scope
    _task_scope = legacy_test_scope(globals())


def tearDownModule():
    _task_scope.close()


def _fixture_bundle() -> dict:
    run_id = "rpf43-witness-test"
    capture_id = "capture-rpf43-witness-test"
    base = make_contracts(run_id, fault="response-lost")
    experiment = {**base.experiment, "schema_version": "rpf-experiment-v3", "owner": "rpf-43",
                  "capture_id": capture_id, "capture_mode": "DETERMINISTIC_CAPTURE"}
    frozen = FrozenContracts.freeze(base.execution, base.effect, experiment)
    execution, effect_contract, experiment = frozen.execution, frozen.effect, frozen.experiment
    environment = {"owner": "rpf-43", "run_id": run_id, "environment_id": experiment["environment_id"],
                   "environment_revision": "rpf41-sqlite-orders-v1", "reset_generation": 0}
    before_data = {"reader_id": "rpf41-sqlite-authority-reader", "reader_version": "1",
                   "source_id": effect_contract["authority_id"], "environment": environment,
                   "order": {"order_id": effect_contract["order_id"],
                             "paid_minor": effect_contract["amount_minor"], "refunded_minor": 0,
                             "currency": "CNY", "status": "PAID", "revision": 0}, "receipts": []}
    receipt = {"operation_id": effect_contract["operation_id"], "order_id": effect_contract["order_id"],
               "amount_minor": effect_contract["amount_minor"], "currency": "CNY",
               "receipt_id": "receipt-" + digest({"environment": experiment["environment_id"],
                                                  "operation_id": effect_contract["operation_id"]})[:24],
               "status": "COMMITTED", "committed_revision": 1}
    after_data = {**before_data, "order": {**before_data["order"], "refunded_minor": 2500,
                                             "status": "REFUNDED", "revision": 1},
                  "receipts": [receipt]}
    before = {"data": before_data, "sha256": digest(before_data)}
    after = {"data": after_data, "sha256": digest(after_data)}
    tool_call = {"name": "refund_order",
                 "arguments": {k: effect_contract[k] for k in ("order_id", "operation_id", "amount_minor")},
                 "result": {"status": "UNKNOWN_OUTCOME", "operation_id": effect_contract["operation_id"],
                            "reason": "CONTROLLED_POST_COMMIT_RESPONSE_LOSS"}}
    reconciliation = {"status": "RECONCILED_COMMITTED", "receipt_id": receipt["receipt_id"],
                      "operation_id": effect_contract["operation_id"]}
    cleanup = {"status": "RESET_AND_REMOVED", "reset_generation": 1, "receipt_count_after_reset": 0}
    effect = {"contract_outcome": "CONTRACT_SATISFIED_IN_RUN",
              "verifier_id": "rpf41-order-effect-verifier", "verifier_version": "1",
              "violated_rules": [], "evidence_gaps": [], "receipt_hash": digest([receipt]),
              "before_sha256": before["sha256"], "after_sha256": after["sha256"]}
    fault = {"planned": True, "triggered": True, "observed": True, "reconciled": True,
             "activation": "TRIGGERED"}
    observation = {"run_outcome": "PASS", "effect": effect, "fault": fault, "tool_calls": [tool_call],
                   "reconciliation": reconciliation, "authority_before": before,
                   "authority_after": after, "cleanup": cleanup}
    facts = [
        {"owner": "rpf-43", "capture_id": capture_id, "contract_hashes": frozen.hashes},
        {"owner": "rpf-43", "run_id": run_id, "environment_id": experiment["environment_id"]},
        {"snapshot_sha256": before["sha256"]},
        {"name": tool_call["name"], "arguments": tool_call["arguments"], "result": tool_call["result"]},
        {key: fault[key] for key in ("planned", "triggered", "observed")},
        reconciliation,
        {"snapshot_sha256": after["sha256"]},
        {"contract_outcome": effect["contract_outcome"], "before_sha256": before["sha256"],
         "after_sha256": after["sha256"], "verifier_id": effect["verifier_id"],
         "verifier_version": effect["verifier_version"]},
        cleanup,
    ]
    events = []
    for seq, (name, event_facts) in enumerate(zip(EVENT_ORDER, facts), start=1):
        events.append({"seq": seq, "event_id": f"event-{run_id}-{seq:02d}",
                       "observed_at": f"2026-10-17T10:00:{seq:02d}.000000+00:00", "type": name,
                       "facts": event_facts, "facts_sha256": digest(event_facts)})
    contracts = {"execution": execution, "effect": effect_contract, "experiment": experiment,
                 "sha256": frozen.hashes}
    claims = {"contract_outcome": effect["contract_outcome"], "fault_activation": "TRIGGERED",
              "attribution_strength": "CORRELATIONAL_ONLY", "reproduction": "NOT_TESTED",
              "run_outcome": "PASS"}
    bundle = {"schema_version": "rpf-effect-witness-v1",
              "issuer": {"issuer_id": "runproof-effectwitness-witness-issuer", "issuer_version": "1",
                         "attestation": "UNSIGNED_LOCAL_TOOL", "source_digest": "a" * 64},
              "capture": {"capture_id": capture_id, "captured_at": events[-1]["observed_at"],
                          "source_level": "MANAGED_LOCAL_SIMULATION",
                          "target_driver": "DETERMINISTIC_CONTROLLED_TARGET",
                          "session_reference": {"kind": "DETERMINISTIC_CAPTURE", "session_id": None,
                                                "session_digest": None, "policy": "NOT_APPLICABLE"},
                          "environment": {"owner": "rpf-43", "run_id": run_id,
                                          "environment_id": experiment["environment_id"],
                                          "revision": "rpf41-sqlite-orders-v1"}},
              "contracts": contracts, "observation": observation, "events": events,
              "claims": claims, "digests": {},
              "limitations": ["NO_ISSUER_SIGNATURE", "NO_PROVIDER_SESSION", "SINGLE_RUN_NOT_REPRODUCTION",
                              "CONTROLLED_LOCAL_SIMULATION_ONLY"]}
    _refresh(bundle)
    return bundle


def _refresh(bundle: dict) -> None:
    """Recompute public consistency digests to model an attacker who can rehash a bundle."""
    contracts = bundle.get("contracts", {})
    if all(key in contracts for key in ("execution", "effect", "experiment", "sha256")):
        exp = contracts["experiment"]
        exp["execution_digest"] = digest(contracts["execution"])
        exp["effect_digest"] = digest(contracts["effect"])
        contracts["sha256"] = {key: digest(contracts[key]) for key in ("execution", "effect", "experiment")}
    observation = bundle.get("observation", {})
    for key in ("authority_before", "authority_after"):
        if type(observation.get(key)) is dict and "data" in observation[key]:
            observation[key]["sha256"] = digest(observation[key]["data"])
    effect = observation.get("effect", {})
    before = (observation.get("authority_before") or {}).get("sha256")
    after = (observation.get("authority_after") or {}).get("sha256")
    if before:
        effect["before_sha256"] = before
    if after:
        effect["after_sha256"] = after
        receipts = observation.get("authority_after", {}).get("data", {}).get("receipts", [])
        effect["receipt_hash"] = digest(receipts)
    for event in bundle.get("events", []):
        if event.get("type") == "contracts_preregistered":
            event["facts"] = {"owner": contracts.get("experiment", {}).get("owner"),
                               "capture_id": contracts.get("experiment", {}).get("capture_id"),
                               "contract_hashes": contracts.get("sha256")}
        elif event.get("type") == "authority_before_verified" and before:
            event["facts"] = {"snapshot_sha256": before}
        elif event.get("type") == "tool_result_observed" and observation.get("tool_calls"):
            call = observation["tool_calls"][0]
            event["facts"] = {"name": call["name"], "arguments": call["arguments"], "result": call["result"]}
        elif event.get("type") == "fault_activation_observed":
            event["facts"] = {key: observation.get("fault", {}).get(key)
                               for key in ("planned", "triggered", "observed")}
        elif event.get("type") == "authority_after_verified" and after:
            event["facts"] = {"snapshot_sha256": after}
        elif event.get("type") == "effect_verified":
            event["facts"] = {"contract_outcome": effect.get("contract_outcome"),
                               "before_sha256": before, "after_sha256": after,
                               "verifier_id": effect.get("verifier_id"),
                               "verifier_version": effect.get("verifier_version")}
        event["facts_sha256"] = digest(event["facts"])
    bundle["digests"] = {"contracts": digest(bundle["contracts"]),
                         "observation": digest(bundle["observation"]),
                         "events": digest(bundle["events"]), "claims": digest(bundle["claims"])}


class WitnessVerifierTests(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=TEST_ROOT)
        self.temp_path = Path(self.temp.name)
        self.bundle = _fixture_bundle()
        self.raw = canonical(self.bundle)
        self.anchor = hashlib.sha256(self.raw).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def _tampered(self, mutate, *, refresh=True):
        bundle = copy.deepcopy(self.bundle)
        mutate(bundle)
        if refresh:
            _refresh(bundle)
        return canonical(bundle)

    def test_anchored_and_unanchored_verdicts_are_distinct(self):
        self.assertEqual(verify_bytes(self.raw, self.anchor)["status"], "VERIFIED_ANCHORED")
        unanchored = verify_bytes(self.raw)
        self.assertEqual(unanchored["status"], "UNANCHORED_INCONCLUSIVE")
        self.assertEqual(unanchored["reason_codes"], ["TRUSTED_EXTERNAL_SHA256_REQUIRED"])
        self.assertEqual(unanchored["issuer_authenticity"], "NOT_ESTABLISHED")
        with self.assertRaisesRegex(VerificationRejected, "BUNDLE_NOT_CANONICAL"):
            verify_bytes(self.raw + b"\n")

    def test_raw_mutation_and_self_consistent_rehash_do_not_pass_old_anchor(self):
        mutated = bytearray(self.raw)
        mutated[-3] ^= 1
        with self.assertRaisesRegex(VerificationRejected, "FILE_SHA256_MISMATCH"):
            verify_bytes(bytes(mutated), self.anchor)
        internally_rehashed = self._tampered(
            lambda bundle: bundle["claims"].update(contract_outcome="VIOLATION_CONFIRMED"))
        with self.assertRaisesRegex(VerificationRejected, "FILE_SHA256_MISMATCH"):
            verify_bytes(internally_rehashed, self.anchor)

    def test_claim_overreach_is_rejected_even_with_a_new_anchor(self):
        raw = self._tampered(lambda bundle: bundle["claims"].update(reproduction="REPRODUCED"))
        with self.assertRaisesRegex(VerificationRejected, "CLAIM_OVERREACH_OR_MISMATCH"):
            verify_bytes(raw, hashlib.sha256(raw).hexdigest())

    def test_wrong_owner_and_external_only_source_cannot_gain_managed_trust(self):
        wrong_owner = self._tampered(lambda bundle: bundle["contracts"]["experiment"].update(owner="rpf-42"))
        with self.assertRaisesRegex(VerificationRejected, "EXPERIMENT_IDENTITY"):
            verify_bytes(wrong_owner, hashlib.sha256(wrong_owner).hexdigest())
        external = self._tampered(lambda bundle: bundle["capture"].update(source_level="EXTERNAL_EVIDENCE_ONLY"))
        with self.assertRaisesRegex(VerificationRejected, "CAPTURE_SOURCE_LEVEL"):
            verify_bytes(external, hashlib.sha256(external).hexdigest())

    def test_missing_receipt_and_tool_result_contradiction_are_rejected(self):
        missing = self._tampered(lambda bundle: bundle["observation"]["authority_after"]["data"].update(
            receipts=[]))
        with self.assertRaisesRegex(VerificationRejected, "LIVE_ORACLE_MISMATCH"):
            verify_bytes(missing, hashlib.sha256(missing).hexdigest())
        contradiction = self._tampered(lambda bundle: bundle["observation"]["tool_calls"][0]["result"].update(
            status="SUCCESS"))
        with self.assertRaisesRegex(VerificationRejected, "TOOL_RESULT_MISMATCH"):
            verify_bytes(contradiction, hashlib.sha256(contradiction).hexdigest())
        duplicate = self._tampered(lambda bundle: bundle["observation"]["authority_after"]["data"][
            "receipts"].append(copy.deepcopy(bundle["observation"]["authority_after"]["data"]["receipts"][0])))
        with self.assertRaisesRegex(VerificationRejected, "LIVE_ORACLE_MISMATCH"):
            verify_bytes(duplicate, hashlib.sha256(duplicate).hexdigest())

    def test_oracle_reports_fixture_violation_and_missing_authority_is_rejected(self):
        def make_violation(bundle):
            bundle["observation"]["authority_after"]["data"]["order"]["refunded_minor"] = 2499
            bundle["observation"]["effect"].update(
                contract_outcome="VIOLATION_CONFIRMED",
                violated_rules=["EXACTLY_ONE_FULL_REFUND_STATE"])
            bundle["claims"]["contract_outcome"] = "VIOLATION_CONFIRMED"
        violation = self._tampered(make_violation)
        result = verify_bytes(violation)
        self.assertEqual(result["status"], "UNANCHORED_INCONCLUSIVE")
        self.assertEqual(result["contract_outcome"], "VIOLATION_CONFIRMED")

        missing = self._tampered(lambda bundle: bundle["observation"].update(authority_before=None))
        with self.assertRaisesRegex(VerificationRejected, "AUTHORITY_SNAPSHOT_FIELDS"):
            verify_bytes(missing, hashlib.sha256(missing).hexdigest())

    def test_planned_but_untriggered_cannot_be_relabelled_triggered(self):
        def lie(bundle):
            bundle["observation"]["fault"].update(triggered=False, observed=False, reconciled=False,
                                                   activation="TRIGGERED")
        raw = self._tampered(lie)
        with self.assertRaisesRegex(VerificationRejected, "FAULT_ACTIVATION_MISMATCH"):
            verify_bytes(raw, hashlib.sha256(raw).hexdigest())

    def test_nonmonotonic_event_time_is_rejected(self):
        def reverse_time(bundle):
            bundle["events"][3]["observed_at"], bundle["events"][4]["observed_at"] = (
                bundle["events"][4]["observed_at"], bundle["events"][3]["observed_at"])
        raw = self._tampered(reverse_time)
        with self.assertRaisesRegex(VerificationRejected, "EVENT_TIME_ORDER"):
            verify_bytes(raw, hashlib.sha256(raw).hexdigest())

    def test_schema_event_refs_fault_axes_and_digest_are_strict(self):
        extra = self._tampered(lambda bundle: bundle.update(unreviewed=True))
        with self.assertRaisesRegex(VerificationRejected, "WITNESS_FIELDS"):
            verify_bytes(extra, hashlib.sha256(extra).hexdigest())
        duplicate_event = self._tampered(lambda bundle: bundle["events"][1].update(
            event_id=bundle["events"][0]["event_id"]))
        with self.assertRaisesRegex(VerificationRejected, "EVENT_IDENTITY"):
            verify_bytes(duplicate_event, hashlib.sha256(duplicate_event).hexdigest())
        bad_axis = self._tampered(lambda bundle: bundle["claims"].update(attribution_strength="INTERVENTION_SUPPORTED"))
        with self.assertRaisesRegex(VerificationRejected, "CLAIM_OVERREACH_OR_MISMATCH"):
            verify_bytes(bad_axis, hashlib.sha256(bad_axis).hexdigest())
        broken_digest = copy.deepcopy(self.bundle)
        broken_digest["digests"]["claims"] = "0" * 64
        raw = canonical(broken_digest)
        with self.assertRaisesRegex(VerificationRejected, "INTERNAL_DIGEST_MISMATCH"):
            verify_bytes(raw, hashlib.sha256(raw).hexdigest())

    def test_fault_activation_preserves_negative_and_unknown_evidence(self):
        planned_not_triggered = {"planned": True, "triggered": False, "observed": False,
                                 "reconciled": False, "activation": "NOT_TRIGGERED"}
        unknown = {"planned": True, "triggered": True, "observed": False,
                   "reconciled": False, "activation": "UNKNOWN"}
        self.assertEqual(_derive_fault_activation(planned_not_triggered), "NOT_TRIGGERED")
        self.assertEqual(_derive_fault_activation(unknown), "UNKNOWN")
        planned_absent = {"planned": False, "triggered": False, "observed": False,
                          "reconciled": False, "activation": "NOT_PLANNED"}
        self.assertEqual(_derive_fault_activation(planned_absent), "NOT_PLANNED")

    def test_owner_rpf43_trial_captures_verified_state_before_cleanup(self):
        run_id = "rpf43-capture-hook-test"
        base = make_contracts(run_id, fault="response-lost")
        experiment = {**base.experiment, "schema_version": "rpf-experiment-v3", "owner": "rpf-43",
                      "capture_id": "capture-hook-test", "capture_mode": "DETERMINISTIC_CAPTURE"}
        contracts = FrozenContracts.freeze(base.execution, base.effect, experiment)
        events = []
        pre_cleanup = []
        shared = SessionBudget(dict(LIMITS), lambda: None)
        shared.reserve_trial("PGE")

        def capture(trial):
            run_directory = ROOT / ".local" / "rpf-43" / run_id
            self.assertTrue(run_directory.is_dir())
            self.assertTrue((run_directory / "orders.sqlite3").is_file())
            self.assertEqual(trial["effect"]["contract_outcome"], "CONTRACT_SATISFIED_IN_RUN")
            self.assertEqual(len(trial["effect"]["after"]["data"]["receipts"]), 1)
            pre_cleanup.append(trial["effect"]["after"]["sha256"])

        result = run_trial(contracts, shared, event_hook=events.append, before_cleanup_hook=capture)
        self.assertEqual(result["run_outcome"], "PASS")
        self.assertEqual(result["fault"]["activation"], "TRIGGERED")
        self.assertTrue(result["fault"]["reconciled"])
        self.assertEqual(result["cleanup"]["status"], "RESET_AND_REMOVED")
        self.assertEqual(len(pre_cleanup), 1)
        self.assertEqual(len(events), 9)
        self.assertEqual([event["name"] for event in events], list(EVENT_ORDER))
        self.assertFalse((ROOT / ".local" / "rpf-43" / run_id).exists())

    def test_witness_issue_builder_freezes_precleanup_observations(self):
        observation = self.bundle["observation"]
        effect = {**observation["effect"], "before": observation["authority_before"],
                  "after": observation["authority_after"]}
        trial = {"contracts": {key: self.bundle["contracts"][key]
                                for key in ("execution", "effect", "experiment")},
                 "contract_hashes": self.bundle["contracts"]["sha256"],
                 "target_driver": self.bundle["capture"]["target_driver"], "run_outcome": "PASS",
                 "effect": effect, "fault": observation["fault"],
                 "tool_calls": observation["tool_calls"], "reconciliation": observation["reconciliation"]}
        events = [{"name": event["type"], "observed_at": event["observed_at"], "facts": event["facts"]}
                  for event in self.bundle["events"]]
        precleanup = json.loads(_precleanup_capture(trial, events[:-1]).decode("utf-8"))
        rebuilt = _final_bundle(precleanup, observation["cleanup"], events, "a" * 64)
        self.assertEqual(verify_bytes(canonical(rebuilt))["status"], "UNANCHORED_INCONCLUSIVE")
        self.assertEqual(precleanup["authority_after"]["sha256"], observation["authority_after"]["sha256"])

    def test_rpf43_storage_owner_is_exactly_scoped(self):
        owned = ROOT / ".local" / "rpf-43" / "safe.json"
        self.assertEqual(owned_path(owned, task="rpf-43"), owned.resolve())
        with self.assertRaisesRegex(RuntimeFailure, "PATH_OUTSIDE_RPF43"):
            owned_path(ROOT / ".local" / "rpf-42" / "do-not-touch.json", task="rpf-43")

    def test_independent_subprocess_verifies_without_sqlite_provider_or_network(self):
        witness_path = self.temp_path / "offline.json"
        witness_path.write_bytes(self.raw)
        code = ("import sys; sys.modules['sqlite3']=None; import socket; "
                "socket.socket=lambda *a, **k: (_ for _ in ()).throw(AssertionError('network disabled')); "
                "from runtime.runproof_runtime.effectwitness.witness_verify import main; "
                "raise SystemExit(main())")
        env = os.environ.copy()
        env.pop("DEEPSEEK_API_KEY", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["TEMP"] = str(self.temp_path)
        env["TMP"] = str(self.temp_path)
        env["TMPDIR"] = str(self.temp_path)
        completed = subprocess.run([sys.executable, "-c", code, str(witness_path),
                                    "--expected-sha256", self.anchor], cwd=REPO_ROOT, env=env,
                                   capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "VERIFIED_ANCHORED")

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(VerificationRejected, "DUPLICATE_JSON_KEY"):
            verify_bytes(b'{"schema_version":"x","schema_version":"y"}')


if __name__ == "__main__":
    unittest.main()
