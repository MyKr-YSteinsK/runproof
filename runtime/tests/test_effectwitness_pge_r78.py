"""Fit-only components before freeze; formal artifact checks only after freeze."""
import ast
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runproof_runtime.effectwitness import pge_r78_contracts as c
from runproof_runtime.effectwitness.pge_r78_calibration import fit
from runproof_runtime.effectwitness.pge_r78_forecast import estimate
from runproof_runtime.effectwitness.pge_r78_provenance import project
from runproof_runtime.effectwitness.pge_r78_policy import decide
from runproof_runtime.effectwitness.pge_r78_replay import replay_case,stress_cases
from runproof_runtime.effectwitness.pge_r78_metrics import measure,comparison
from runproof_runtime.effectwitness.pge_r78_verify import expected_model,adjudicate,measurements,stress_inputs,comparison as independent_comparison,verify,verify_file
spec=importlib.util.spec_from_file_location('probe78',c.ROOT/'spikes/rpf-78/probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class ComponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No validation/challenge replay or threshold selection in this class.
        dev,_=c.catalogs();cls.fit_cases=dev['fit'];cls.model=fit(cls.fit_cases,c.source_identity())

    def toy(self,**changes):
        case=copy.deepcopy(self.fit_cases[1]);case['view']['candidates']=case['view']['candidates'][:1]
        first=case['view']['candidates'][0]['candidate_id'];case['outcomes']={first:case['outcomes'][first]}
        case['view']['candidates'][0].update(changes);c.seal(case);return case

    def choice(self,case,policy=c.POLICIES[0],**state):
        v=case['view'];s=dict(c.initial(v),**state);return decide(v,case['records'],s,case['roster'],case['roster_sha256'],self.model,policy)

    def test_component_01_fit_counts(self):
        self.assertEqual({k:(v['n'],v['positive']) for k,v in self.model['buckets'].items()},{'HIGH':(24,18),'LOW':(22,4),'RARE':(2,0)})
    def test_component_02_fit_identity(self):self.assertEqual(self.model,expected_model(self.fit_cases,c.source_identity()))
    def test_component_03_fit_partition_first(self):
        with self.assertRaisesRegex(c.Invalid,'FIT_PARTITION_ONLY'):fit([{'view':{'split':'challenge'}}],c.source_identity())
    def test_component_04_fit_completed_only(self):
        case=self.toy();next(iter(case['outcomes'].values()))['status']='UNKNOWN'
        with self.assertRaisesRegex(c.Invalid,'FIT_COMPLETED_ONLY'):fit([case],c.source_identity())
    def test_component_05_rare_unsupported(self):
        d=self.choice(self.toy(feature_kind='RARE'));self.assertEqual(d['reason'],'UNSUPPORTED_FORECAST');self.assertEqual(d['unsupported'][0]['status'],'INSUFFICIENT_SUPPORT')
    def test_component_06_unseen_bucket(self):self.assertEqual(self.choice(self.toy(feature_kind='UNSEEN'))['unsupported'][0]['status'],'UNSUPPORTED_BUCKET')
    def test_component_07_unknown_feature(self):self.assertEqual(self.choice(self.toy(feature_status='UNKNOWN'))['action'],'INCONCLUSIVE')
    def test_component_08_positive_lower_select(self):self.assertEqual(self.choice(self.toy(cost=2,risk=0))['action'],'SELECT')
    def test_component_09_interval_refuses_positive_point(self):
        case=self.toy(cost=5,risk=0);self.assertEqual(self.choice(case)['reason'],'INTERVAL_CROSSES_ZERO');self.assertEqual(self.choice(case,c.POLICIES[1])['action'],'SELECT')
    def test_component_10_all_upper_nonpositive(self):self.assertEqual(self.choice(self.toy(feature_kind='LOW',cost=6,risk=0))['reason'],'NONPOSITIVE_UPPER_NET')
    def test_component_11_point_nonpositive(self):self.assertEqual(self.choice(self.toy(feature_kind='LOW',cost=3,risk=0),c.POLICIES[1])['reason'],'NONPOSITIVE_POINT_NET')
    def test_component_12_no_unknown_unlock(self):
        case=self.toy();self.assertEqual(self.choice(case,unknown_domains=[case['view']['domain']])['reason'],'UNKNOWN_STOP')
    def test_component_13_other_domain_unknown(self):self.assertEqual(self.choice(self.toy(),unknown_domains=['lab-unrelated'])['action'],'SELECT')
    def test_component_14_no_budget_unlock(self):self.assertEqual(self.choice(self.toy(),remaining=0)['reason'],'NO_ELIGIBLE')
    def test_component_15_risk_guard(self):self.assertEqual(self.choice(self.toy(risk=3))['filtered'][0]['reason'],'RISK')
    def test_component_16_permission_guard(self):
        case=self.toy();case['view']['permissions']=[];c.seal(case);self.assertEqual(self.choice(case)['filtered'][0]['reason'],'PERMISSION')
    def test_component_17_precondition_guard(self):self.assertEqual(self.choice(self.toy(requires=['missing-fact']))['filtered'][0]['reason'],'PRECONDITION')
    def test_component_18_expired_source(self):
        case=self.toy();case['records'][0]['valid_until']=0;c.seal(case);self.assertEqual(self.choice(case,elapsed=1)['reason'],'NO_TRUSTED_SOURCE')
    def test_component_19_future_feedback(self):
        case=self.toy();case['records'][0].update(visible_at=1,seq=2);c.seal(case);self.assertEqual(self.choice(case)['evidence']['refused'][0]['reason'],'FUTURE')
    def test_component_20_cross_domain_feedback(self):
        case=self.toy();case['records'][0]['domain']='lab-foreign';c.seal(case);self.assertEqual(self.choice(case)['evidence']['refused'][0]['reason'],'CROSS_DOMAIN')
    def test_component_21_roster_self_sign(self):
        case=self.toy();r=dict(case['records'][0],facts={'fact-00':'forged'})
        with self.assertRaisesRegex(c.Invalid,'FROZEN_ROSTER_MEMBER'):project(case['view'],[r],case['roster'],case['roster_sha256'],c.initial(case['view']))
    def test_component_22_duplicate_record(self):
        case=self.toy()
        with self.assertRaisesRegex(c.Invalid,'DUPLICATE_RECORD'):project(case['view'],case['records']*2,case['roster'],case['roster_sha256'],c.initial(case['view']))
    def test_component_23_false_zero_type(self):
        case=self.toy();case['view']['candidates'][0]['visible_at']=False
        with self.assertRaisesRegex(c.Invalid,'FEATURE_visible_at'):c.validate(case['view'])
    def test_component_24_duplicate_candidate(self):
        case=self.toy();case['view']['candidates']*=2
        with self.assertRaisesRegex(c.Invalid,'DUPLICATE_CANDIDATE'):c.validate(case['view'])
    def test_component_25_no_locator_fields(self):
        case=self.toy();case['view']['url']='external'
        with self.assertRaisesRegex(c.Invalid,'VIEW_SCHEMA'):c.validate(case['view'])
    def test_component_26_intervals_are_descriptive_and_bounded(self):
        for r in self.model['buckets'].values():self.assertTrue(0<=r['lower']<=r['p_hat']<=r['upper']<=1)
    def test_component_27_no_verifier_generator_imports(self):
        tree=ast.parse((c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r78_verify.py').read_text())
        self.assertFalse(any(n.module and any(z in n.module for z in ('policy','calibration','forecast','replay','metrics','oracle','baselines')) for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)))
    def test_component_28_no_truth_in_forecast_or_policy_signature(self):
        for module in ('forecast','policy'):
            tree=ast.parse((c.ROOT/('runtime/runproof_runtime/effectwitness/pge_r78_'+module+'.py')).read_text())
            args=[a.arg for f in tree.body if isinstance(f,ast.FunctionDef) for a in f.args.args]
            self.assertFalse(any(x in args for x in ('outcomes','useful_effect','worthwhile_ids','labels')))
    def test_component_29_independent_adjudication_fit_only(self):
        for case in self.fit_cases:
            for policy in c.POLICIES:
                run=replay_case(case,policy,self.model)
                for row in run['rows']:self.assertEqual((row['decision'],row['oracle']),adjudicate(case,row['records'],row['state'],self.model,policy))
                self.assertEqual(measure(run),measurements(run))
    def test_component_30_independent_stress_derivation_fit_only(self):self.assertEqual(stress_cases(self.fit_cases[:2]),stress_inputs(self.fit_cases[:2]))
    def test_component_31_stress_preserves_unknown_scope(self):
        case=self.toy();case['view']['initial_unknown']=[case['view']['domain']]
        x=next(z for z in stress_cases([case]) if z['transform']=='MISSING_DOMAIN');self.assertEqual(x['view']['initial_unknown'],['lab-absent'])
    def test_component_32_offline_events_without_operations(self):
        for event in ('socket.__new__','subprocess.Popen','os.system'):
            with self.assertRaisesRegex(c.Invalid,'OFFLINE_OPERATION_FORBIDDEN'):probe.guard(event,())
    def test_component_33_json_duplicate(self):
        with self.assertRaisesRegex(c.Invalid,'DUPLICATE_JSON'):c.strict(b'{"x":1,"x":2}')
    def test_component_34_file_scope(self):self.assertEqual(verify_file(c.ROOT/'AGENTS.md','0'*64)[0],3)
    def test_component_35_missing_anchor(self):self.assertEqual(verify_file(c.WORK/'absent.json',None)[0],2)
    def test_component_36_independent_prediction_metrics_fit_only(self):
        runs=[];predictions=[]
        for case in self.fit_cases:
            v=case['view'];s=c.initial(v);ev=project(v,case['records'],case['roster'],case['roster_sha256'],s)
            for x in v['candidates']:predictions.append(dict(split='fit',case_id=v['case_id'],candidate_id=x['candidate_id'],forecast=estimate(x,self.model,s,ev),observed_useful=case['outcomes'][x['candidate_id']]['useful_effect']))
            runs.extend(replay_case(case,p,self.model) for p in c.POLICIES)
        self.assertEqual(comparison(runs,predictions),independent_comparison(runs,predictions))
    def test_component_37_future_feature_not_used(self):
        case=self.toy(visible_at=1);self.assertEqual(self.choice(case)['unsupported'][0]['status'],'FUTURE_FEATURE')
        self.assertEqual(self.choice(case,'PGE-v3-utility')['action'],'INCONCLUSIVE')
    def test_component_38_expired_feature_not_used(self):
        case=self.toy(valid_until=0);self.assertEqual(self.choice(case,elapsed=1)['unsupported'][0]['status'],'EXPIRED_FEATURE')
        self.assertEqual(self.choice(case,'PGE-v3-utility',elapsed=1)['action'],'INCONCLUSIVE')
    def test_component_39_unsupported_domain(self):
        case=self.toy();case['view']['domain']='lab-absent';case['view']['candidates'][0]['domain']='lab-absent'
        # Use the already validated stress namespace to change every identity coherently.
        parent=self.toy();derived=next(x for x in stress_cases([parent]) if x['transform']=='MISSING_DOMAIN')
        self.assertEqual(self.choice(derived)['unsupported'][0]['status'],'UNSUPPORTED_DOMAIN')


class FrozenAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace=c.strict((c.WORK/'main-1.json').read_bytes())
    def test_original_main(self):self.assertEqual(verify(self.trace)['runs'],120)
    def test_model_from_fit_only(self):
        dev,_=c.catalogs();self.assertEqual(self.trace['model'],expected_model(dev['fit'],self.trace['source_sha256']))
    def test_source_freeze(self):self.assertEqual(c.strict((c.WORK/'source-freeze.json').read_bytes())['source'],c.source_map())
    def test_main_order_invariant(self):self.assertEqual((c.WORK/'main-1.json').read_bytes(),(c.WORK/'main-2.json').read_bytes())
    def test_no_abstention_continuation(self):
        for run in self.trace['runs']:
            for row in run['rows'][:-1]:self.assertEqual(row['decision']['action'],'SELECT')
    def test_prediction_truth_is_evaluation_only(self):
        for run in self.trace['runs']:
            for row in run['rows']:self.assertNotIn('useful_effect',row['decision'])
    def test_stress_original(self):self.assertEqual(verify(c.strict((c.WORK/'stress.json').read_bytes()))['runs'],504)
    def test_public_model_exact_private(self):
        raw=(c.WORK/'fitted-model.json').read_bytes();self.assertEqual(c.sha(raw),self.trace['model_raw_sha256'])


def attack(index):
    def test(self):
        _,v=probe.mutant(self.trace,index);self.assertNotEqual(v['result_sha256'],self.trace['result_sha256'])
        with self.assertRaises(c.Invalid):verify(v)
    return test


for i in range(len(probe.specs())+8):setattr(FrozenAcceptanceTests,'test_negative_%02d'%(i+1),attack(i))
if __name__=='__main__':unittest.main()
