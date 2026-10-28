"""Development-only focused tests; holdout not used for weight selection."""
import ast
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runproof_runtime.effectwitness import pge_r76_contracts as c
from runproof_runtime.effectwitness.pge_r76_fixtures import load
from runproof_runtime.effectwitness.pge_r76_policy import decide
from runproof_runtime.effectwitness.pge_r76_provenance import project
from runproof_runtime.effectwitness.pge_r76_oracle import evaluate
from runproof_runtime.effectwitness.pge_r76_metrics import row_metrics
from runproof_runtime.effectwitness.pge_r76_replay import run, replay_case
from runproof_runtime.effectwitness.pge_r76_verify import verify, verify_file, adjudicate

spec = importlib.util.spec_from_file_location('probe76', c.ROOT / 'spikes/rpf-76/probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class OfflineEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load('development')
        cls.trace = run(('development',))

    def setUp(self):
        self.case = copy.deepcopy(self.data['cases'][0])
        self.v = self.case['view']

    def choice(self, index=0, **changes):
        case = self.data['cases'][index]
        state = dict(c.initial(case['view']), **changes)
        records = [r for r in case['records'] if r['visible_at'] <= state['step']]
        return decide(case['view'], records, state, case['roster'], case['roster_sha256'])

    def bad(self, field, value, code):
        self.v[field] = value
        with self.assertRaisesRegex(c.Invalid, '^' + code + '$'):
            c.validate_view(self.v)

    def test_01_domain_neutral(self):
        self.assertEqual(len({x['view']['domain'] for x in self.data['cases']}), 3)

    def test_02_fact_space(self):
        self.assertGreaterEqual(len(self.v['fact_keys']), 8)

    def test_03_candidate_shapes(self):
        self.assertEqual({len(x['view']['candidates']) for x in self.data['cases']}, {1, 2, 3, 4})

    def test_04_explainable_selection(self):
        d = self.choice()
        self.assertEqual(d['action'], 'SELECT')
        self.assertEqual(d['ranking'][0]['score'], sum(d['ranking'][0]['terms'].values()))

    def test_05_stop_counterexample(self):
        case = self.data['cases'][1]
        rows = replay_case(case, 'PGE-v2')['rows']
        self.assertEqual(rows[0]['decision']['action'], 'STOP')
        self.assertEqual(rows[0]['oracle']['verdict'], 'SHOULD_SELECT')
        self.assertEqual(row_metrics(rows)['correct_stop'], 0)
        self.assertEqual(row_metrics(rows)['missed_opportunity'], 1)

    def test_06_unknown_domain_stops(self):
        self.assertEqual(self.choice(2)['reason'], 'UNKNOWN_STOP')

    def test_07_other_domain_unknown_does_not_stop(self):
        self.assertEqual(self.choice(3)['action'], 'SELECT')

    def test_08_permissions(self):
        self.assertEqual(self.choice(4)['reason'], 'NO_ELIGIBLE')

    def test_09_zero_budget(self):
        self.assertEqual(self.choice(5)['action'], 'STOP')

    def test_10_risk_guard(self):
        self.assertTrue(all(x['reason'] == 'RISK' for x in self.choice(6)['rejected']))

    def test_11_observed_not_verified(self):
        self.assertEqual(self.choice(7)['action'], 'INCONCLUSIVE')

    def test_12_conflict_is_independent_uncertainty(self):
        self.assertEqual(self.choice(8)['reason'], 'CONFLICT')

    def test_13_time_limit(self):
        self.assertEqual(self.choice(9, elapsed=1)['reason'], 'TIME_STOP')

    def test_14_untrusted_source(self):
        self.assertEqual(self.choice(10)['reason'], 'NO_TRUSTED_EVIDENCE')

    def test_15_unknown_outcome_transitions(self):
        rows = replay_case(self.data['cases'][11], 'PGE-v2')['rows']
        self.assertEqual(rows[1]['decision']['reason'], 'UNKNOWN_STOP')

    def test_16_frozen_roster_preexists_projection(self):
        roster = self.case['roster']
        self.assertGreater(len(roster['entries']), 1)
        self.assertEqual(c.digest(roster), self.case['roster_sha256'])

    def test_17_self_signed_record_refused(self):
        r = dict(self.case['records'][0], facts={'fact-00': 'fake'})
        with self.assertRaisesRegex(c.Invalid, 'RECORD_NOT_IN_FROZEN_ROSTER'):
            project(self.v, [r], self.case['roster'], self.case['roster_sha256'], 0)

    def test_18_self_signed_roster_refused(self):
        roster = copy.deepcopy(self.case['roster'])
        roster['entries']['new-record'] = '0' * 64
        with self.assertRaisesRegex(c.Invalid, 'ROSTER_ANCHOR'):
            project(self.v, [], roster, self.case['roster_sha256'], 0)

    def test_19_future_records_rejected_reason(self):
        p = project(self.v, self.case['records'], self.case['roster'], self.case['roster_sha256'], 0)
        self.assertIn('FUTURE_RECORD', [x['reason'] for x in p['rejected']])

    def test_20_cross_domain_case_reasons(self):
        p = project(self.v, self.case['records'], self.case['roster'], self.case['roster_sha256'], 1)
        self.assertTrue({'CROSS_DOMAIN', 'CROSS_CASE'} <= {x['reason'] for x in p['rejected']})

    def test_21_wrong_contract_reason(self):
        case = self.data['cases'][11]
        p = project(case['view'], case['records'], case['roster'], case['roster_sha256'], 1)
        self.assertIn('WRONG_CONTRACT', [x['reason'] for x in p['rejected']])

    def test_22_duplicate_records(self):
        record = self.case['records'][0]
        with self.assertRaisesRegex(c.Invalid, 'DUPLICATE_RECORD'):
            project(self.v, [record, record], self.case['roster'], self.case['roster_sha256'], 0)

    def test_23_negative_budget(self):
        self.bad('budget', -1, 'BUDGET')

    def test_24_overflow_budget(self):
        self.bad('budget', 2 ** 63, 'BUDGET')

    def test_25_boolean_budget(self):
        self.bad('budget', False, 'BUDGET')

    def test_26_deadline_overflow(self):
        self.bad('deadline', 2 ** 63, 'DEADLINE')

    def test_27_unknown_schema_field(self):
        self.v['uri'] = 'external'
        with self.assertRaisesRegex(c.Invalid, 'VIEW_SCHEMA'):
            c.validate_view(self.v)

    def test_28_invalid_id(self):
        self.bad('case_id', '../external', 'CASE_ID')

    def test_29_duplicate_candidate(self):
        self.v['candidates'] *= 2
        with self.assertRaisesRegex(c.Invalid, 'DUPLICATE_CANDIDATE'):
            c.validate_view(self.v)

    def test_30_cross_domain_candidate(self):
        self.v['candidates'][0]['domain'] = 'lab-foreign'
        with self.assertRaisesRegex(c.Invalid, 'CANDIDATE_SCOPE'):
            c.validate_view(self.v)

    def test_31_bad_candidate_anchor(self):
        self.v['candidates'][0]['cost'] += 1
        with self.assertRaisesRegex(c.Invalid, 'CANDIDATE_ANCHOR'):
            c.validate_view(self.v)

    def test_32_empty_pool(self):
        self.v['candidates'] = []
        c.validate_view(self.v)
        for record in self.case['records']:
            record['contract_sha256'] = c.snapshot_sha(self.v)
        self.case['roster']['entries'] = {r['evidence_id']: c.digest(r) for r in self.case['records']}
        self.case['roster_sha256'] = c.digest(self.case['roster'])
        records = [r for r in self.case['records'] if r['visible_at'] == 0]
        self.assertEqual(decide(self.v, records, c.initial(self.v), self.case['roster'],
                                self.case['roster_sha256'])['reason'], 'NO_ELIGIBLE')

    def test_33_no_repeat_guard(self):
        d = self.choice(15, step=1, elapsed=1, attempted=['lab-amber-c0'])
        self.assertIn('REPEAT', [r['reason'] for r in d['rejected']])

    def test_34_state_cost_bound(self):
        with self.assertRaisesRegex(c.Invalid, 'STATE_BUDGET'):
            self.choice(0, remaining=19)

    def test_35_state_false_step(self):
        with self.assertRaisesRegex(c.Invalid, 'STATE_STEP'):
            self.choice(0, step=False)

    def test_36_oracle_does_not_accept_decision_argument(self):
        tree = ast.parse((c.ROOT / 'runtime/runproof_runtime/effectwitness/pge_r76_oracle.py').read_text())
        f = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
        self.assertEqual([x.arg for x in f.args.args], ['case', 'records', 'state'])

    def test_37_independent_oracle_matches(self):
        for case in self.data['cases']:
            state = c.initial(case['view'])
            records = [r for r in case['records'] if r['visible_at'] == 0]
            self.assertEqual(evaluate(case, records, state), adjudicate(case, records, state, 'PGE-v2')[1])

    def test_38_verifier_does_not_import_generators(self):
        tree = ast.parse((c.ROOT / 'runtime/runproof_runtime/effectwitness/pge_r76_verify.py').read_text())
        names = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(x and any(w in x for w in ('policy', 'replay', 'metrics', 'oracle')) for x in names))

    def test_39_original_trace_verifies(self):
        self.assertEqual(verify(self.trace)['runs'], 72)

    def test_40_deterministic_replay(self):
        self.assertEqual(c.canonical(self.trace), c.canonical(run(('development',))))

    def test_41_input_order_invariant(self):
        self.assertEqual(c.canonical(self.trace), c.canonical(run(('development',), reverse=True)))

    def test_42_missing_anchor_exit_two(self):
        self.assertEqual(verify_file(c.WORK / 'absent.json', None)[0], 2)

    def test_43_wrong_path_scope(self):
        self.assertEqual(verify_file(c.ROOT / 'AGENTS.md', '0' * 64)[0], 3)

    def test_44_missing_file_exit_two(self):
        self.assertEqual(verify_file(c.WORK / 'absent.json', '0' * 64)[0], 2)

    def test_45_duplicate_json(self):
        with self.assertRaisesRegex(c.Invalid, 'DUPLICATE_JSON'):
            c.strict(b'{"x":0,"x":1}')

    def test_46_nonfinite_json(self):
        with self.assertRaisesRegex(c.Invalid, 'NONFINITE'):
            c.strict(b'{"x":NaN}')

    def test_47_stop_accuracy_is_not_tautology(self):
        s = self.trace['evaluation']['summaries']['development']['PGE-v2']
        self.assertLess(s['correct_stop'], s['total_stop'])
        self.assertGreater(s['missed_opportunity'], 0)

    def test_48_not_determinable_not_counted_correct(self):
        rows = [dict(decision=dict(action='STOP', rejected=[]), oracle=dict(verdict='INCONCLUSIVE_ALLOWED'))]
        m = row_metrics(rows)
        self.assertEqual((m['correct_stop'], m['stop_not_determinable']), (0, 1))

    def test_49_unsafe_select_independently_detected(self):
        row = copy.deepcopy(self.trace['runs'][0]['rows'][0])
        row['oracle']['eligible'] = []
        self.assertEqual(row_metrics([row])['unsafe_select'], 1)

    def test_50_guard_types_without_operations(self):
        for event in ('socket.__new__', 'subprocess.Popen', 'os.system'):
            with self.assertRaisesRegex(c.Invalid, 'OFFLINE_OPERATION_FORBIDDEN'):
                probe.guard(event, ())

    def test_51_late_record_is_separate_reason(self):
        record = dict(self.case['records'][0], visible_at=1, seq=1)
        roster = dict(self.case['roster'], entries={record['evidence_id']: c.digest(record)})
        projected = project(self.v, [record], roster, c.digest(roster), 1)
        self.assertEqual(projected['rejected'][0]['reason'], 'LATE_RECORD')

    def test_52_input_catalog_hashes_unchanged(self):
        expected = ['8a7ecf764bd16a17832eebf099486613300d8af2a877497309af1fe8f2d6d36b',
                    '80313d60ec288fa54c7547012e0dde6f2489fdabd2f6002a68a604b38b8cf577']
        self.assertEqual([c.sha((c.ROOT / p).read_bytes()) for p in c.INPUTS], expected)


def make_control(index):
    def test(self):
        _, value = probe.mutant(self.trace, index)
        self.assertNotEqual(value['result_sha256'], self.trace['result_sha256'])
        with self.assertRaises(c.Invalid):
            verify(value)
    return test


for i in range(len(probe.specs()) + 12):
    setattr(OfflineEvaluationTests, 'test_negative_%02d' % (i + 1), make_control(i))


if __name__ == '__main__':
    unittest.main()
