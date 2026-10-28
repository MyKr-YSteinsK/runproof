"""Focused offline admission, feedback, transition, fairness and attack tests."""
import copy
import ast
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runproof_runtime.effectwitness import pge_r75_contracts as c
from runproof_runtime.effectwitness.pge_r75_policy import decide
from runproof_runtime.effectwitness.pge_r75_feedback import visible
from runproof_runtime.effectwitness.pge_r75_replay import run
from runproof_runtime.effectwitness.pge_r75_verify import verify, verify_file

spec = importlib.util.spec_from_file_location('rpf75_probe', c.ROOT / 'spikes/rpf-75/probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class OfflinePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = c.catalog()
        cls.trace = run()

    def setUp(self):
        self.case = copy.deepcopy(self.fixture['cases'][0])
        self.v = c.view(self.case)

    def choice(self, case=None, step=0, **state_changes):
        case = case or self.case
        v = c.view(case)
        state = c.initial(v)
        state.update(state_changes)
        state['step'] = step
        records = [r for r in case['feedback'] if r['visible_at'] <= step]
        return decide(v, records, state, trusted_records={r['evidence_id']: c.digest(r) for r in records})

    def invalid_view(self, field, value, reason):
        self.v[field] = value
        with self.assertRaisesRegex(c.Invalid, '^' + reason + '$'):
            c.validate_view(self.v)

    def test_01_initial_select_has_explanation(self):
        result = self.choice()
        self.assertEqual(result['candidate_id'], 'normal')
        self.assertEqual(result['reason'], 'MAX_EXPLAINABLE_SCORE')
        self.assertEqual(result['ranking'][0]['score'], sum(result['ranking'][0]['terms'].values()))

    def test_02_feedback_changes_ranking(self):
        self.assertNotEqual(self.choice()['candidate_id'], self.choice(step=1, attempted=['normal'])['candidate_id'])

    def test_03_empty_feedback_repeat_is_legal(self):
        result = self.choice(self.fixture['cases'][1], step=1, attempted=['normal-full-refund'])
        self.assertEqual(result['candidate_id'], 'normal-full-refund')

    def test_04_inconclusive_does_not_add_facts(self):
        result = self.choice(self.fixture['cases'][2], step=1, attempted=['normal'])
        self.assertEqual(result['evidence']['facts'], {'seed': 'ready'})

    def test_05_contradiction_stops(self):
        result = self.choice(self.fixture['cases'][3], step=1, attempted=['normal-full-refund'])
        self.assertEqual(result['action'], 'INCONCLUSIVE')
        self.assertEqual(result['reason'], 'CONTRADICTORY_FEEDBACK')

    def test_06_late_evidence_not_visible(self):
        result = self.choice(self.fixture['cases'][4], step=1, attempted=['normal'])
        self.assertEqual(result['evidence']['facts'], {'seed': 'ready'})

    def test_07_missing_contract_anchor_ignored(self):
        result = self.choice(self.fixture['cases'][5], step=1, attempted=['normal-full-refund'])
        self.assertEqual(result['evidence']['rejected'][0]['reason'], 'EVIDENCE_CONTRACT')

    def test_08_model_assertion_not_verified(self):
        result = self.choice(self.fixture['cases'][6], step=1, attempted=['normal'])
        self.assertEqual(result['evidence']['rejected'][0]['reason'], 'EVIDENCE_UNTRUSTED')

    def test_09_zero_budget_stops(self):
        self.assertEqual(self.choice(self.fixture['cases'][7])['action'], 'STOP')

    def test_10_permission_guard(self):
        result = self.choice(self.fixture['cases'][8])
        self.assertTrue(all(r['reason'] == 'PERMISSION' for r in result['rejected']))

    def test_11_risk_guard(self):
        result = self.choice(self.fixture['cases'][9])
        self.assertIn('RISK', [r['reason'] for r in result['rejected']])

    def test_12_unknown_stops_without_ranking(self):
        result = self.choice(self.fixture['cases'][10])
        self.assertEqual((result['reason'], result['ranking']), ('UNKNOWN_STOP', []))

    def test_13_deadline_stops(self):
        result = self.choice(self.fixture['cases'][11], step=1, attempted=['normal-full-refund'], elapsed=1)
        self.assertEqual(result['reason'], 'DEADLINE_STOP')

    def test_14_empty_pool_stops(self):
        self.assertEqual(self.choice(self.fixture['cases'][13])['reason'], 'NO_CANDIDATES')

    def test_15_no_repeat_is_explicit(self):
        result = self.choice(self.fixture['cases'][14], step=1, attempted=['normal'])
        self.assertIn(dict(candidate_id='normal', reason='ALREADY_ATTEMPTED'), result['rejected'])

    def test_16_missing_trusted_feedback_inconclusive(self):
        result = decide(self.v, [], c.initial(self.v), trusted_records={})
        self.assertEqual(result['reason'], 'NO_TRUSTED_FEEDBACK')

    def test_17_negative_budget_invalid(self):
        self.invalid_view('budget', -1, 'BUDGET_RANGE')

    def test_18_budget_overflow_invalid(self):
        self.invalid_view('budget', 2 ** 63, 'BUDGET_RANGE')

    def test_19_boolean_budget_invalid(self):
        self.invalid_view('budget', True, 'BUDGET_RANGE')

    def test_20_duplicate_candidate_invalid(self):
        self.v['candidates'].append(copy.deepcopy(self.v['candidates'][0]))
        with self.assertRaisesRegex(c.Invalid, 'DUPLICATE_CANDIDATE'):
            c.validate_view(self.v)

    def test_21_cross_domain_candidate_invalid(self):
        self.v['candidates'][0]['candidate_id'] = 'normal-full-refund'
        with self.assertRaisesRegex(c.Invalid, 'CANDIDATE_DOMAIN'):
            c.validate_view(self.v)

    def test_22_arbitrary_path_schema_invalid(self):
        self.v['path'] = 'external.json'
        with self.assertRaisesRegex(c.Invalid, 'VIEW_SCHEMA'):
            c.validate_view(self.v)

    def test_23_future_feedback_rejected(self):
        records = self.case['feedback']
        with self.assertRaisesRegex(c.Invalid, 'FUTURE_EVIDENCE'):
            visible(self.v, records, {r['evidence_id']: c.digest(r) for r in records}, 0)

    def test_24_forged_verified_record_rejected(self):
        original = self.case['feedback'][0]
        forged = dict(original, facts={'seed': 'other'})
        with self.assertRaisesRegex(c.Invalid, 'EVIDENCE_NOT_FROZEN'):
            visible(self.v, [forged], {original['evidence_id']: c.digest(original)}, 0)

    def test_25_duplicate_evidence_rejected(self):
        r = self.case['feedback'][0]
        with self.assertRaisesRegex(c.Invalid, 'DUPLICATE_EVIDENCE'):
            visible(self.v, [r, r], {r['evidence_id']: c.digest(r)}, 0)

    def test_26_policy_id_rejected(self):
        with self.assertRaisesRegex(c.Invalid, 'POLICY_ID'):
            decide(self.v, [], c.initial(self.v), trusted_records={}, policy='new-policy')

    def test_27_state_budget_rejected(self):
        with self.assertRaisesRegex(c.Invalid, 'STATE_BUDGET'):
            decide(self.v, [], dict(c.initial(self.v), remaining=100), trusted_records={})

    def test_28_independent_replay_accepts(self):
        self.assertEqual(verify(self.trace)['runs'], 48)

    def test_29_replay_deterministic(self):
        self.assertEqual(c.canonical(run()), c.canonical(self.trace))

    def test_30_input_order_invariant(self):
        self.assertEqual(c.canonical(run(reverse=True)), c.canonical(self.trace))

    def test_31_direct_candidate_order_invariant(self):
        records = [self.case['feedback'][0]]
        roster = {r['evidence_id']: c.digest(r) for r in records}
        other = dict(self.v, candidates=list(reversed(self.v['candidates'])), permissions=list(reversed(self.v['permissions'])))
        self.assertEqual(decide(self.v, records, c.initial(self.v), trusted_records=roster),
                         decide(other, records, c.initial(self.v), trusted_records=roster))

    def test_32_cli_missing_anchor_exit_two(self):
        self.assertEqual(verify_file(c.WORK / 'absent.json', None)[0], 2)

    def test_33_cli_missing_file_exit_two(self):
        self.assertEqual(verify_file(c.WORK / 'absent.json', '0' * 64)[0], 2)

    def test_34_path_scope_rejected(self):
        self.assertEqual(verify_file(c.ROOT / 'AGENTS.md', '0' * 64)[0], 3)

    def test_35_duplicate_json_rejected(self):
        with self.assertRaisesRegex(c.Invalid, 'DUPLICATE_JSON_KEY'):
            c.strict(b'{"x":1,"x":2}')

    def test_36_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(c.Invalid, 'NONFINITE_JSON'):
            c.strict(b'{"x":NaN}')

    def test_37_unknown_outcome_next_step_stops(self):
        replay = next(r for r in self.trace['runs'] if r['case_id'] == 'case-15' and r['policy'] == 'PGE-v1')
        self.assertEqual(replay['rows'][1]['decision']['reason'], 'UNKNOWN_STOP')

    def test_38_baselines_same_case_state_oracle(self):
        self.assertEqual(len(self.trace['comparison']['table']), 48)
        self.assertEqual(set(r['policy'] for r in self.trace['runs']), set(c.POLICIES))

    def test_39_deep_reanchor_compound_rejected(self):
        mutant = probe.mutate(self.trace, probe.control_specs()[31])
        mutant['runs'][30]['rows'][0]['outcome'] = dict(status='VERIFIED', facts={'version': 'v2'})
        probe.reanchor(mutant)
        with self.assertRaisesRegex(c.Invalid, 'DECISION_SEMANTICS'):
            verify(mutant)

    def test_40_timeout_budget_and_unknown_priorities(self):
        result = self.choice(unknown=True, elapsed=99, remaining=0)
        self.assertEqual(result['reason'], 'UNKNOWN_STOP')

    def test_41_baseline_wrappers(self):
        from runproof_runtime.effectwitness.pge_r75_baselines import fixed_order, no_feedback
        records = [self.case['feedback'][0]]
        roster = {r['evidence_id']: c.digest(r) for r in records}
        for function, policy in ((fixed_order, 'B0-fixed-v1'), (no_feedback, 'B1-no-feedback-v1')):
            self.assertEqual(function(self.v, records, c.initial(self.v), trusted_records=roster),
                             decide(self.v, records, c.initial(self.v), trusted_records=roster, policy=policy))

    def test_42_configurable_weights(self):
        self.v['weights'] = dict(gain=0, priority=0, cost=0, risk=0)
        r = dict(self.case['feedback'][0], contract_sha256=c.digest(self.v))
        r['payload_sha256'] = c.digest({k: v for k, v in r.items() if k != 'payload_sha256'})
        result = decide(self.v, [r], c.initial(self.v), trusted_records={r['evidence_id']: c.digest(r)})
        self.assertEqual(result['candidate_id'], min(x['candidate_id'] for x in self.v['candidates']))

    def test_43_preconditions_block_selection(self):
        for candidate in self.v['candidates']:
            candidate['requires'] = ['recovery']
        r = dict(self.case['feedback'][0], contract_sha256=c.digest(self.v))
        r['payload_sha256'] = c.digest({k: v for k, v in r.items() if k != 'payload_sha256'})
        result = decide(self.v, [r], c.initial(self.v), trusted_records={r['evidence_id']: c.digest(r)})
        self.assertEqual(result['reason'], 'NO_LEGAL_CANDIDATE')
        self.assertTrue(all(x['reason'] == 'PRECONDITION' for x in result['rejected']))

    def test_44_offline_guard_denies_event_types(self):
        # Invoke the guard directly; never attempt a socket or child process.
        for event in ('socket.__new__', 'subprocess.Popen', 'os.system'):
            with self.assertRaisesRegex(c.Invalid, 'OFFLINE_OPERATION_FORBIDDEN'):
                probe.offline_guard(event, ())

    def test_45_no_external_adapter_imports(self):
        allowed = {'ast', 'argparse', 'copy', 'hashlib', 'json', 'pathlib', 'sys', 'unittest', 'importlib.util'}
        for rel in c.SOURCE_PATHS:
            if not rel.endswith('.py'):
                continue
            tree = ast.parse((c.ROOT / rel).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(x.name in allowed for x in node.names))
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertTrue(node.module in allowed or 'pge_r75_' in node.module
                                    or node.module == 'runproof_runtime.effectwitness')


def make_control(spec):
    def test(self):
        mutant = probe.mutate(self.trace, spec)
        self.assertNotEqual(mutant['result_sha256'], self.trace['result_sha256'])
        with self.assertRaises(c.Invalid):
            verify(mutant)
    return test


for index, control in enumerate(probe.control_specs(), 1):
    setattr(OfflinePolicyTests, 'test_negative_%02d_%s' % (index, control[0].replace('-', '_')), make_control(control))


if __name__ == '__main__':
    unittest.main()
