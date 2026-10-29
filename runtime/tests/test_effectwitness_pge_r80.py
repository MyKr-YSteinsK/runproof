"""Finite offline safety contract tests; no legacy runtime imported."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runproof_runtime.effectwitness import pge_r80_oracle as oracle
from runproof_runtime.effectwitness import pge_r80_unknown_barrier as barrier
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('probe80',ROOT/'spikes/rpf-80/probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class SafetyTests(unittest.TestCase):
    def test_no_shared_decision_import(self):
        tree=ast.parse((ROOT/'runtime/runproof_runtime/effectwitness/pge_r80_oracle.py').read_text())
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):self.assertTrue(all(x.name in ('hashlib','json','re') for x in n.names))
            self.assertNotIsInstance(n,ast.ImportFrom)
    def test_scope_rejects_legacy_private(self):
        with self.assertRaisesRegex(ValueError,'FILE_SCOPE'):probe.path(ROOT/'.local/rpf-74/wal.json')
    def test_anchor_missing(self):self.assertEqual(oracle.inspect(b'{}',None,'0'*64)['reason'],'ANCHOR_REQUIRED')
    def test_anchor_wrong(self):self.assertEqual(oracle.inspect(b'{}','0'*64,'0'*64)['reason'],'OUTER_ANCHOR')
    def test_false_is_not_integer_seq(self):
        c=probe.cases()[0];v=json.loads(c['raw']);v['frames'][0]['seq']=False;raw=probe.canonical(v)
        self.assertEqual(oracle.inspect(raw,probe.sha(raw),probe.sha(raw))['reason'],'WAL_CHAIN')
    def test_unknown_global_all_roles_domains(self):
        s,_=barrier.step(barrier.initial(),dict(kind='TOOL_RETURN',domain='config',role='TARGET',row={'result':{'status':'UNKNOWN_OUTCOME'}}))
        for d in ('config','order'):
            for role in ('TARGET','EXPLORER'):self.assertEqual(barrier.admit(s,'RESERVE',d,role,'provider','ticket-9')['decision'],'DENY')
        self.assertEqual(barrier.admit(s,'RESERVE','order','TARGET','business_write','ticket-9')['decision'],'ALLOW')
        self.assertEqual(barrier.admit(s,'RESERVE','config','TARGET','business_write','ticket-9')['decision'],'DENY')
    def test_old_ticket_send_distinct_from_new_reserve(self):
        c=next(x for x in probe.cases() if x['id']=='old-ticket-send-risk');a=oracle.inspect(c['raw'].encode(),c['raw_sha256'],c['raw_sha256'])
        self.assertEqual(a['status'],'NO_VIOLATION');self.assertEqual(len(a['post_unknown_send_risks']),1);self.assertEqual(a['physical_send'],'UNPROVEN')
    def test_collusive_root_rewrite_not_authenticated(self):
        c=next(x for x in probe.cases() if x['id']=='violation-config-target');v=probe.mutation(json.loads(c['raw']),5);raw=probe.canonical(v)
        a=oracle.inspect(raw,probe.sha(raw),probe.sha(raw));self.assertEqual(a['source_authenticity'],'UNPROVEN_SOURCE_AUTHENTICITY')
    def test_mutation_index_rejected(self):
        with self.assertRaises(ValueError):probe.mutation(json.loads(probe.cases()[0]['raw']),99)
    def test_roster_digests_unique(self):
        cases=probe.cases();self.assertEqual(len(cases),14);self.assertEqual(len({x['raw_sha256'] for x in cases}),14)
    def test_mutants_distinct_and_not_original(self):
        c=next(x for x in probe.cases() if x['id']=='violation-config-target');v=json.loads(c['raw'])
        roots={probe.sha(probe.canonical(probe.mutation(v,i))) for i in range(8)}
        self.assertEqual(len(roots),8);self.assertNotIn(c['raw_sha256'],roots)
    def test_fault_flags_do_not_replace_unknown_observation(self):
        s,_=barrier.step(barrier.initial(),dict(kind='FAULT',domain='config',role='HOST',observed=True,agent_exposed=True))
        self.assertEqual(barrier.admit(s,'RESERVE','config','TARGET','provider','ticket-1')['decision'],'ALLOW')


def case_test(case):
    def test(self):
        raw=case['raw'].encode();self.assertEqual(probe.sha(raw),case['raw_sha256']);result=oracle.inspect(raw,case['raw_sha256'],case['raw_sha256'])
        self.assertEqual(result['status'],case['expected']);self.assertEqual(result['same_domain_rule'],case['expected_same_domain']);probe.compare(json.loads(raw),result)
    return test


for case in probe.cases():setattr(SafetyTests,'test_case_'+case['id'].replace('-','_'),case_test(case))


def mutant_test(i):
    def test(self):
        c=next(x for x in probe.cases() if x['id']=='violation-config-target');raw=probe.canonical(probe.mutation(json.loads(c['raw']),i));a=oracle.inspect(raw,probe.sha(raw),c['raw_sha256']);self.assertEqual(a['status'],'INVALID')
        if i>=5:self.assertEqual(a['reason'],'REGISTERED_CASE_ROOT')
    return test


for i in range(8):setattr(SafetyTests,'test_mutation_%02d'%i,mutant_test(i))


if __name__=='__main__':unittest.main()
