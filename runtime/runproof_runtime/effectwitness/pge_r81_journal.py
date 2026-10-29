"""Append/fsync task journal, single process writer plus thread serialization."""
import os
import threading
from . import pge_r81_contracts as c


class Journal:
    def __init__(self,case_id,create=False):
        self.case_id=case_id;self.root=c.case_dir(case_id);self.source=c.source_id();self.mutex=threading.RLock();self.poison=False
        if create:self.root.mkdir(parents=True,exist_ok=False)
        else:c.require(self.root.is_dir(),'SESSION_MISSING')
        self.writer=c.WriterLock(self.root/'writer.lock');self.path=self.root/'wal.jsonl'
        try:
            if create:self.append('OWNER',session_id='session-'+case_id,source_kind=c.KIND,fixture_sha256=c.digest(c.spec(case_id)))
            self.read()
        except BaseException:self.writer.close();raise

    def close(self):self.writer.close()

    def read(self):
        c.scope(self.path);c.require(c.source_id()==self.source,'SOURCE_DRIFT')
        raw=self.path.read_bytes();c.require(raw and raw.endswith(b'\n'),'TORN_WAL')
        c.require(len(raw)<=262144,'WAL_BOUND')
        state=self.replay([c.strict(x) for x in raw.splitlines()])
        files=sorted((self.root/'commits').glob('*.json')) if (self.root/'commits').exists() else []
        c.require([f.name for f in files]==['%02d.json'%i for i in range(len(state['frames']))],'COMMIT_HEAD_MISMATCH')
        for i,p in enumerate(files):
            c.scope(p);ack=c.strict(p.read_bytes());prefix=b'\n'.join(raw.splitlines()[:i+1])+b'\n'
            c.require(ack['seq']==i and ack['frame_sha256']==state['frames'][i]['sha256'] and ack['wal_sha256']==c.sha(prefix) and ack['source']==self.source and ack['case_id']==self.case_id,'COMMIT_HEAD_BINDING')
        return state

    def replay(self,frames):
        c.require(1<=len(frames)<=64,'FRAME_BOUND');previous=None;tickets={};unknown=False;terminal=False;last=-1
        for i,f in enumerate(frames):
            c.require(set(f)=={'seq','previous','event','sha256'} and type(f['seq']) is int and f['seq']==i and f['previous']==previous and f['sha256']==c.digest({k:v for k,v in f.items() if k!='sha256'}),'WAL_CHAIN')
            e=f['event'];kind=e['kind'];c.require(e['owner']==c.OWNER and e['abi']==c.ABI and e['source']==self.source and e['case_id']==self.case_id and type(e['mono']) in (float,int) and e['mono']>=last,'WAL_IDENTITY')
            c.require(not terminal and (i==0)==(kind=='OWNER'),'WAL_TERMINAL_OWNER')
            extra={'OWNER':{'session_id','source_kind','fixture_sha256'},'SLOT_RESERVED':{'ticket','domain','role'},'UNKNOWN_OBSERVED':{'domain','role','observed_mono','planned','triggered','observed','agent_exposed'},'SEND_BEGIN':{'ticket','payload_sha256','size'},'SEND_END':{'ticket','outcome'},'READ_ONLY_RECONCILE':{'status'},'SESSION_TERMINAL':{'status'}}
            c.require(kind in extra and set(e)=={'kind','owner','abi','source','case_id','utc','mono','pid'}|extra[kind],'WAL_SCHEMA')
            c.require(type(e['pid']) is int and e['pid']>0 and type(e['utc']) is str,'CLOCK_PID')
            if kind=='OWNER':c.require(e['session_id']=='session-'+self.case_id and e['source_kind']==c.KIND and e['fixture_sha256']==c.digest(c.spec(self.case_id)),'OWNER_BINDING')
            elif kind=='SLOT_RESERVED':
                c.require(not unknown and e['ticket'] not in tickets and e['domain'] in ('config','order') and e['role'] in ('TARGET','EXPLORER') and type(e['ticket']) is str,'RESERVE_BARRIER')
                tickets[e['ticket']]=dict(domain=e['domain'],role=e['role'],sent=False,ended=False)
            elif kind=='UNKNOWN_OBSERVED':
                c.require(e['domain'] in ('config','order') and e['role'] in ('TARGET','EXPLORER') and all(type(e[k]) is bool for k in ('planned','triggered','observed','agent_exposed')) and type(e['observed_mono']) in (int,float) and e['observed_mono']<=e['mono'],'UNKNOWN_FIELDS');unknown=True
            elif kind=='SEND_BEGIN':
                c.require(not unknown and e['ticket'] in tickets and not tickets[e['ticket']]['sent'],'SEND_BARRIER');tickets[e['ticket']]['sent']=True
            elif kind=='SEND_END':
                c.require(e['ticket'] in tickets and tickets[e['ticket']]['sent'] and not tickets[e['ticket']]['ended'] and e['outcome']=='RETURNED','SEND_END_LINEAGE');tickets[e['ticket']]['ended']=True
            elif kind=='SESSION_TERMINAL':terminal=True
            previous=c.digest(f);last=e['mono']
        return dict(frames=frames,tickets=tickets,unknown=unknown,terminal=terminal,last_hash=previous)

    def append(self,kind,inject=None,**fields):
        with c.serial(self.mutex):
            if self.poison:raise ValueError('PERSIST_FAILURE_INCONCLUSIVE')
            frames=self.read()['frames'] if self.path.exists() else []
            event=dict(kind=kind,owner=c.OWNER,abi=c.ABI,source=self.source,case_id=self.case_id,**c.clock(),**fields)
            f=dict(seq=len(frames),previous=c.digest(frames[-1]) if frames else None,event=event);f['sha256']=c.digest(f)
            self.replay(frames+[f])
            try:
                if inject=='write':raise OSError('INJECTED_WRITE_FAILURE')
                with self.path.open('ab') as file:
                    file.write(c.canonical(f)+b'\n');file.flush()
                    if inject=='fsync':raise OSError('INJECTED_FSYNC_FAILURE')
                    os.fsync(file.fileno())
                c.once(self.root/'commits'/('%02d.json'%f['seq']),dict(seq=f['seq'],frame_sha256=f['sha256'],wal_sha256=c.sha(self.path.read_bytes()),source=self.source,case_id=self.case_id,**c.clock()))
            except OSError:self.poison=True;raise
            return f
