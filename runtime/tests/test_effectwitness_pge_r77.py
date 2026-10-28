"""Development-only tests plus semantic variants; no historical runtime calls."""
import ast
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runproof_runtime.effectwitness import pge_r77_contracts as c
from runproof_runtime.effectwitness.pge_r77_fixtures import load,diagnostic76,seal
from runproof_runtime.effectwitness.pge_r77_projection import evidence
from runproof_runtime.effectwitness.pge_r77_policy import decide
from runproof_runtime.effectwitness.pge_r77_oracle import evaluate
from runproof_runtime.effectwitness.pge_r77_replay import run,replay_case,measure,rates
from runproof_runtime.effectwitness.pge_r77_verify import verify,verify_file,adjudicate
spec=importlib.util.spec_from_file_location('probe77',c.ROOT/'spikes/rpf-77/probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class UtilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=load('development');cls.trace=run(('development',))

    def choice(self,index=0,policy=None,**changes):
        case=self.data['cases'][index];v=case['view'];s=dict(c.initial(v),**changes)
        records=[r for r in case['records'] if r['visible_at']<=s['step']]
        return decide(v,records,s,case['roster'],case['roster_sha256'],policy or c.POLICIES[0])

    def test_01_zero_key_obligation_selects(self):
        d=self.choice();self.assertEqual(d['action'],'SELECT');self.assertEqual(d['ranking'][0]['expected_key_novelty'],0)

    def test_02_v2_zero_key_stops(self):self.assertEqual(self.choice(policy=c.POLICIES[1])['reason'],'ESTIMATED_ZERO_GAIN')
    def test_03_b0_zero_key_selects(self):self.assertEqual(self.choice(policy=c.POLICIES[2])['action'],'SELECT')
    def test_04_novel_but_costly_v3_stops(self):self.assertEqual(self.choice(1)['reason'],'NONPOSITIVE_VISIBLE_UTILITY')
    def test_05_v2_overexploration(self):
        rows=replay_case(self.data['cases'][1],c.POLICIES[1]);self.assertGreater(measure(rows)['over_exploration'],0)
    def test_06_conflict(self):self.assertEqual(self.choice(2)['reason'],'CONFLICT')
    def test_07_untrusted(self):self.assertEqual(self.choice(3)['reason'],'NO_TRUSTED_SOURCE')
    def test_08_unknown_current(self):self.assertEqual(self.choice(4)['reason'],'UNKNOWN_STOP')
    def test_09_unknown_other(self):self.assertEqual(self.choice(5)['action'],'SELECT')
    def test_10_zero_budget(self):self.assertEqual(self.choice(6)['reason'],'NO_ELIGIBLE')
    def test_11_expired(self):self.assertEqual(self.choice(7)['reason'],'TIME_STOP')
    def test_12_unknown_features_inconclusive(self):self.assertEqual(self.choice(8)['reason'],'UTILITY_FEATURES_UNKNOWN')
    def test_13_v3_false_positive_preserved(self):self.assertGreater(measure(replay_case(self.data['cases'][9],c.POLICIES[0]))['over_exploration'],0)
    def test_14_v3_false_negative_preserved(self):self.assertEqual(measure(replay_case(self.data['cases'][10],c.POLICIES[0]))['missed_opportunity'],1)
    def test_15_unknown_after_selected_outcome(self):self.assertEqual(replay_case(self.data['cases'][5],c.POLICIES[0])['rows'][1]['decision']['reason'],'UNKNOWN_STOP')
    def test_16_domains_and_shapes(self):
        self.assertEqual(len({x['view']['domain'] for x in self.data['cases']}),3)
        self.assertEqual({len(x['view']['candidates']) for x in self.data['cases']},{1,2,3,4})
    def test_17_no_labels_in_policy_arguments(self):
        tree=ast.parse((c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r77_policy.py').read_text())
        f=next(x for x in tree.body if isinstance(x,ast.FunctionDef));self.assertEqual([x.arg for x in f.args.args],['v','records','s','roster','anchor','policy'])
    def test_18_oracle_no_decision_argument(self):
        tree=ast.parse((c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r77_oracle.py').read_text())
        f=next(x for x in tree.body if isinstance(x,ast.FunctionDef));self.assertEqual([x.arg for x in f.args.args],['case','records','state'])
    def test_19_verifier_no_generators(self):
        tree=ast.parse((c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r77_verify.py').read_text())
        self.assertFalse(any(n.module and any(w in n.module for w in ('policy','replay','utility','baselines','oracle')) for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)))
    def test_20_roster_self_sign_refused(self):
        case=self.data['cases'][0];r=dict(case['records'][0],facts={'fact-00':'fake'})
        with self.assertRaisesRegex(c.Invalid,'FROZEN_ROSTER_MEMBER'):evidence(case['view'],[r],case['roster'],case['roster_sha256'],0)
    def test_21_duplicate_record(self):
        case=self.data['cases'][0];r=case['records'][0]
        with self.assertRaisesRegex(c.Invalid,'DUPLICATE_RECORD'):evidence(case['view'],[r,r],case['roster'],case['roster_sha256'],0)
    def test_22_future_record_reason(self):
        case=self.data['cases'][0];p=evidence(case['view'],case['records'],case['roster'],case['roster_sha256'],0)
        self.assertEqual(p['refused'][0]['reason'],'FUTURE')
    def test_23_late_record_reason(self):
        case=copy.deepcopy(self.data['cases'][0]);case['records'][0]['visible_at']=1;case['records'][0]['seq']=1;seal(case)
        p=evidence(case['view'],case['records'][:1],case['roster'],case['roster_sha256'],1);self.assertEqual(p['refused'][0]['reason'],'LATE')
    def test_24_false_zero_feature_type(self):
        v=copy.deepcopy(self.data['cases'][0]['view']);v['candidates'][0]['feature_visible_at']=False
        with self.assertRaisesRegex(c.Invalid,'FEATURE_feature_visible_at'):c.validate(v)
    def test_25_candidate_overflow(self):
        v=copy.deepcopy(self.data['cases'][0]['view']);v['candidates'][0]['cost']=2**63
        with self.assertRaisesRegex(c.Invalid,'FEATURE_cost'):c.validate(v)
    def test_26_domain_reference(self):
        v=copy.deepcopy(self.data['cases'][0]['view']);v['candidates'][0]['domain']='lab-other'
        with self.assertRaisesRegex(c.Invalid,'CANDIDATE_SCOPE'):c.validate(v)
    def test_27_duplicate_candidate(self):
        v=copy.deepcopy(self.data['cases'][0]['view']);v['candidates']*=2
        with self.assertRaisesRegex(c.Invalid,'DUPLICATE_CANDIDATE'):c.validate(v)
    def test_28_risk_not_unlocked_by_utility(self):
        case=copy.deepcopy(self.data['cases'][0]);case['view']['candidates'][0]['risk']=3;seal(case);v=case['view']
        d=decide(v,case['records'][:1],c.initial(v),case['roster'],case['roster_sha256']);self.assertEqual(d['filtered'][0]['reason'],'RISK')
    def test_29_permission_not_unlocked_by_utility(self):
        case=copy.deepcopy(self.data['cases'][0]);case['view']['permissions']=[];seal(case);v=case['view']
        d=decide(v,case['records'][:1],c.initial(v),case['roster'],case['roster_sha256']);self.assertEqual(d['filtered'][0]['reason'],'PERMISSION')
    def test_30_zero_facts_cost_ratio(self):
        self.assertEqual(rates(dict(correct_stop=0,total_stop=0,stop_not_determinable=0,eligible_selects=0,selects=0,appropriate_inconclusive=0,inconclusive=0,simulated_cost=3,verified_facts=0))['cost_per_verified_fact']['status'],'ZERO_FACTS')
    def test_31_independent_oracle(self):
        for case in self.data['cases']:
            s=c.initial(case['view']);r=[x for x in case['records'] if x['visible_at']==0]
            self.assertEqual(evaluate(case,r,s),adjudicate(case,r,s,c.POLICIES[0])[1])
    def test_32_original_verifies(self):self.assertEqual(verify(self.trace)['runs'],90)
    def test_33_repeat_deterministic(self):self.assertEqual(c.canonical(self.trace),c.canonical(run(('development',))))
    def test_34_reverse_invariant(self):self.assertEqual(c.canonical(self.trace),c.canonical(run(('development',),True)))
    def test_35_anchor_required(self):self.assertEqual(verify_file(c.WORK/'absent.json',None)[0],2)
    def test_36_file_scope(self):self.assertEqual(verify_file(c.ROOT/'AGENTS.md','0'*64)[0],3)
    def test_37_json_duplicate(self):
        with self.assertRaisesRegex(c.Invalid,'DUPLICATE_JSON'):c.strict(b'{"x":1,"x":2}')
    def test_38_no_operations_guard(self):
        for event in ('socket.__new__','subprocess.Popen','os.system'):
            with self.assertRaisesRegex(c.Invalid,'OFFLINE_OPERATION_FORBIDDEN'):probe.guard(event,())
    def test_39_exposed_diagnostics_not_filled_with_labels(self):
        ds=diagnostic76();self.assertEqual(len(ds),3)
        for case in ds:
            r=replay_case(case,c.POLICIES[0]);self.assertEqual(r['rows'][0]['decision']['reason'],'UTILITY_FEATURES_UNKNOWN')
            self.assertEqual(replay_case(case,c.POLICIES[1])['rows'][0]['decision']['reason'],'ESTIMATED_ZERO_GAIN')
    def test_40_v2_math_reference(self):
        d=self.choice(11,c.POLICIES[1]);x=self.data['cases'][11]['view']['candidates'][0];row=next(r for r in d['ranking'] if r['candidate_id']==x['candidate_id'])
        self.assertEqual(row['score'],10*row['gain']+2*x['priority']-x['cost']-x['risk'])
    def test_41_preconditions_precede_utility(self):
        case=copy.deepcopy(self.data['cases'][0]);case['view']['candidates'][0]['requires']=['fact-11'];seal(case);v=case['view']
        d=decide(v,case['records'][:1],c.initial(v),case['roster'],case['roster_sha256']);self.assertEqual(d['filtered'][0]['reason'],'PRECONDITION')
    def test_42_empty_pool_stops(self):
        case=copy.deepcopy(self.data['cases'][0]);case['view']['candidates']=[];seal(case);v=case['view']
        d=decide(v,case['records'][:1],c.initial(v),case['roster'],case['roster_sha256']);self.assertEqual(d['reason'],'NO_ELIGIBLE')
    def test_43_arbitrary_locator_is_not_a_contract(self):
        v=copy.deepcopy(self.data['cases'][0]['view']);v['url']='external'
        with self.assertRaisesRegex(c.Invalid,'VIEW_SCHEMA'):c.validate(v)


def attack(index):
    def test(self):
        _,value=probe.mutant(self.trace,index);self.assertNotEqual(value['result_sha256'],self.trace['result_sha256'])
        with self.assertRaises(c.Invalid):verify(value)
    return test


for i in range(len(probe.specs())+12):setattr(UtilityTests,'test_negative_%02d'%(i+1),attack(i))
if __name__=='__main__':unittest.main()
