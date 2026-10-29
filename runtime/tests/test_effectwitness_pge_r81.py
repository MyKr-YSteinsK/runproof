"""No TCP in unittest: finite journal/Oracle tests, separate physical CLI cases."""
import ast
import copy
import importlib.util
import os
from pathlib import Path
import sys
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runproof_runtime.effectwitness import pge_r81_contracts as c
from runproof_runtime.effectwitness import pge_r81_oracle as oracle
from runproof_runtime.effectwitness.pge_r81_journal import Journal
from runproof_runtime.effectwitness.pge_r81_barrier import Host
spec=importlib.util.spec_from_file_location('probe81',c.ROOT/'spikes/rpf-81/probe.py');probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class ConformanceTests(unittest.TestCase):
    def uid(self,label):return 'unit-'+label+'-'+str(os.getpid())+'-'+str(time.monotonic_ns())
    def test_strict_json(self):
        for raw in [b'{"a":1,"a":2}',b'{"a":NaN}']:
            with self.assertRaises(ValueError):c.strict(raw)
            with self.assertRaises(ValueError):oracle.strict(raw)
    def test_fixture_roots(self):
        rows=c.strict((c.ROOT/'spikes/rpf-81/fixtures.json').read_bytes())['cases']
        self.assertEqual(len({x['id'] for x in rows}),len(rows))
        for x in rows:self.assertEqual(x['input_sha256'],c.digest({k:v for k,v in x.items() if k!='input_sha256'}))
    def test_oracle_imports_independent(self):
        tree=ast.parse((c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r81_oracle.py').read_text())
        for n in ast.walk(tree):
            if isinstance(n,ast.ImportFrom):self.assertEqual(n.module,'pathlib')
            if isinstance(n,ast.Import):self.assertTrue(all(x.name in ('hashlib','json','re') for x in n.names))
    def test_normal_journal_ack(self):
        h=Host(self.uid('normal'),True)
        try:
            self.assertEqual(h.reserve(),'ticket-1');self.assertEqual(len(h.journal.read()['frames']),2);h.terminal();self.assertTrue(h.journal.read()['terminal'])
        finally:h.close()
    def test_unknown_denies_all_domains_roles_old_send(self):
        h=Host(self.uid('unknown'),True)
        try:
            h.reserve();self.assertEqual(h.unknown(),'COMMITTED');before=h.journal.path.read_bytes()
            for d in ('config','order'):
                for role in ('TARGET','EXPLORER'):self.assertEqual(h.reserve(d,role),'DENY')
            self.assertEqual(h.send('ticket-1',0),'DENY');self.assertEqual(before,h.journal.path.read_bytes());self.assertFalse((h.root/'calls.jsonl').exists())
            h.reconcile();h.terminal()
        finally:h.close()
    def test_restart_same_journal(self):
        name=self.uid('restart');h=Host(name,True);h.reserve();h.unknown();old=h.journal.path.read_bytes();h.close();other=Host(name,False)
        try:
            self.assertTrue(other.journal.read()['unknown']);self.assertEqual(other.reserve(),'DENY');self.assertEqual(other.send('ticket-1',0),'DENY');self.assertEqual(old,other.journal.path.read_bytes())
        finally:other.close()
    def test_existing_session_rejected(self):
        name=self.uid('exists');h=Host(name,True)
        try:
            with self.assertRaises(FileExistsError):Host(name,True)
        finally:h.close()
    def test_single_writer_kernel_lock(self):
        name=self.uid('writer');a=Journal(name,True)
        try:
            with self.assertRaisesRegex(ValueError,'WRITER_LOCK_UNAVAILABLE'):Journal(name,False)
            self.assertEqual(len(a.read()['frames']),1)
        finally:a.close()
    def test_injected_write_failure_stop(self):self.persist('write')
    def test_injected_fsync_failure_stop(self):self.persist('fsync')
    def persist(self,kind):
        h=Host(self.uid(kind),True)
        try:
            h.reserve();self.assertEqual(h.unknown(inject=kind),'INCONCLUSIVE');self.assertEqual(h.reserve(),'DENY');self.assertEqual(h.send('ticket-1',0),'DENY');self.assertFalse((h.root/'calls.jsonl').exists());self.assertTrue((h.root/'persist-failure.json').exists())
        finally:h.close()
    def test_lock_timeout_fail_closed(self):
        h=Host(self.uid('timeout'),True);h.reserve();entered=threading.Event();release=threading.Event()
        def hold():
            with h.journal.mutex:entered.set();release.wait(5)
        t=threading.Thread(target=hold);t.start();self.assertTrue(entered.wait(1))
        try:self.assertEqual(h.unknown(),'INCONCLUSIVE')
        finally:release.set();t.join(2)
        try:self.assertEqual(h.reserve(),'DENY');self.assertEqual(h.send('ticket-1',0),'DENY')
        finally:h.close()
    def test_torn_new_candidate_rejected(self):
        name=self.uid('torn');root=c.case_dir(name);root.mkdir(parents=True);(root/'wal.jsonl').write_bytes(b'{"seq":0')
        with self.assertRaisesRegex(ValueError,'TORN_WAL'):Journal(name,False)
    def test_missing_committed_tail_rejected(self):
        name=self.uid('missing');root=c.case_dir(name);root.mkdir(parents=True)
        e=dict(kind='OWNER',owner=c.OWNER,abi=c.ABI,source=c.source_id(),case_id=name,session_id='session-'+name,source_kind=c.KIND,fixture_sha256=c.digest(c.spec(name)),**c.clock());f=dict(seq=0,previous=None,event=e);f['sha256']=c.digest(f);raw=c.canonical(f)+b'\n'
        with (root/'wal.jsonl').open('xb') as out:out.write(raw)
        for i in (0,1):c.once(root/'commits'/('%02d.json'%i),dict(seq=i,frame_sha256=f['sha256'],wal_sha256=c.sha(raw),source=c.source_id(),case_id=name))
        with self.assertRaisesRegex(ValueError,'COMMIT_HEAD_MISMATCH'):Journal(name,False)
    def test_units_cannot_consume_network_budget(self):
        with self.assertRaisesRegex(ValueError,'SEND_SCOPE_LIMIT'):c.claim_send(self.uid('nosend'),'ticket-1',b'unit')
    def test_old_scope_refused(self):
        with self.assertRaisesRegex(ValueError,'TASK_SCOPE'):c.scope(c.ROOT/'.local/rpf-74/wal.jsonl')
    def test_semantic_old_ticket_proposal(self):self.proposal('p8-unsafe-send','OLD_TICKET_SEND_AFTER_UNKNOWN')
    def test_semantic_new_ticket_proposal(self):self.proposal('p8-unsafe-reserve','NEW_RESERVE_AFTER_UNKNOWN')
    def proposal(self,name,reason):
        v=probe.proposal(name);raw=c.canonical(v);r=oracle.inspect(raw,c.sha(raw),c.source_id(),c.spec(name));self.assertEqual(r['status'],'VIOLATION');self.assertEqual(r['violations'][0]['kind'],reason);self.assertFalse(r['actual_physical_send'])
    def test_wrong_missing_anchor(self):
        v=probe.proposal('p8-unsafe-send');raw=c.canonical(v)
        self.assertEqual(oracle.inspect(raw,None,c.source_id(),c.spec(v['case_id']))['classification'],'ANCHOR_REQUIRED');self.assertEqual(oracle.inspect(raw,'0'*64,c.source_id(),c.spec(v['case_id']))['classification'],'OUTER_ANCHOR')
    def test_bad_owner_source_boolean_seq(self):
        original=probe.proposal('p8-unsafe-send')
        for mode in ('owner','source','seq'):
            v=copy.deepcopy(original);frames=[c.strict(x) for x in v['wal_raw'].splitlines()]
            if mode=='seq':frames[1]['seq']=True
            else:frames[0]['event'][mode]='wrong'
            text=''.join(c.canonical(f).decode()+'\n' for f in frames);v['wal_raw']=text if mode=='seq' else probe.rechain(text);raw=c.canonical(v);self.assertEqual(oracle.inspect(raw,c.sha(raw),c.source_id(),c.spec(v['case_id']))['status'],'INVALID')


if __name__=='__main__':unittest.main()
