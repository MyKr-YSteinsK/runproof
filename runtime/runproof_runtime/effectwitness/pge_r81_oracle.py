"""Independent WAL, host-call and physical receiver verifier. Stdlib only."""
import hashlib
import json
from pathlib import Path
import re


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(x):return sha(canonical(x))
def need(x,reason):
    if not x:raise ValueError(reason)


def strict(raw):
    def pairs(items):
        d={}
        for k,v in items:need(k not in d,'DUPLICATE_KEY');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:need(False,'NONFINITE'))


def wal(raw,source,spec,kind):
    need(type(raw) is bytes and 0<len(raw)<=262144 and raw.endswith(b'\n'),'TORN_OR_BOUND')
    fs=[strict(x) for x in raw.splitlines()];need(1<=len(fs)<=64,'FRAME_BOUND');prev=None;last=-1;terminal=False;tickets={};unknown=None;violations=[];begins=[];ends=set()
    for i,f in enumerate(fs):
        need(type(f) is dict and set(f)=={'seq','previous','event','sha256'} and type(f['seq']) is int and f['seq']==i and f['previous']==prev and f['sha256']==digest({k:v for k,v in f.items() if k!='sha256'}),'WAL_CHAIN')
        e=f['event'];k=e.get('kind');extras={'OWNER':{'session_id','source_kind','fixture_sha256'},'SLOT_RESERVED':{'ticket','domain','role'},'UNKNOWN_OBSERVED':{'domain','role','observed_mono','planned','triggered','observed','agent_exposed'},'SEND_BEGIN':{'ticket','payload_sha256','size'},'SEND_END':{'ticket','outcome'},'READ_ONLY_RECONCILE':{'status'},'SESSION_TERMINAL':{'status'}}
        need(k in extras and set(e)=={'kind','owner','abi','source','case_id','utc','mono','pid'}|extras[k],'EVENT_SCHEMA')
        need(e['owner']=='rpf-81-rev-1' and e['abi']=='rpf81-loopback-v1' and e['source']==source and e['case_id']==spec['id'],'OWNER_SOURCE')
        need(type(e['mono']) in (float,int) and e['mono']>=last and type(e['pid']) is int and e['pid']>0 and type(e['utc']) is str,'EVENT_CLOCK')
        need(not terminal and (i==0)==(k=='OWNER'),'TERMINAL_OWNER_ORDER')
        if k=='OWNER':need(e['session_id']=='session-'+spec['id'] and e['source_kind']==kind and e['fixture_sha256']==digest(spec),'FIXTURE_OWNER')
        if k=='SLOT_RESERVED':
            need(type(e['ticket']) is str and re.fullmatch('ticket-[1-4]',e['ticket']) and e['ticket'] not in tickets and e['domain'] in ('config','order') and e['role'] in ('TARGET','EXPLORER'),'SLOT_SCOPE')
            tickets[e['ticket']]=i
            if unknown is not None:violations.append(dict(kind='NEW_RESERVE_AFTER_UNKNOWN',unknown_seq=unknown,seq=i,ticket=e['ticket']))
        if k=='UNKNOWN_OBSERVED':
            need(e['domain'] in ('config','order') and e['role'] in ('TARGET','EXPLORER') and all(type(e[x]) is bool for x in ('planned','triggered','observed','agent_exposed')) and type(e['observed_mono']) in (float,int) and e['observed_mono']<=e['mono'],'UNKNOWN_FIELDS')
            if unknown is None:unknown=i
        if k=='SEND_BEGIN':
            need(e['ticket'] in tickets and all(b['ticket']!=e['ticket'] for b in begins) and type(e['size']) is int and e['size']==len(spec['payload'].encode()) and e['payload_sha256']==sha(spec['payload'].encode()),'SEND_SCOPE')
            begins.append(dict(seq=i,ticket=e['ticket'],mono=e['mono']))
            if unknown is not None:violations.append(dict(kind='OLD_TICKET_SEND_AFTER_UNKNOWN' if tickets[e['ticket']]<unknown else 'POST_UNKNOWN_SEND',unknown_seq=unknown,seq=i,ticket=e['ticket']))
        if k=='SEND_END':need(any(x['ticket']==e['ticket'] for x in begins) and e['ticket'] not in ends and e['outcome']=='RETURNED','END_LINEAGE');ends.add(e['ticket'])
        if k=='READ_ONLY_RECONCILE':need(e['status']=='LOCAL_JOURNAL_READ_ONLY','READ_ONLY_KIND')
        if k=='SESSION_TERMINAL':need(e['status'] in ('TERMINATED','INCONCLUSIVE'),'TERMINAL_STATUS');terminal=True
        prev=digest(f);last=e['mono']
    return dict(frames=fs,unknown=unknown,violations=violations,begins=begins,ends=sorted(ends),terminal=terminal,tickets=tickets)


def lines(raw):
    need(type(raw) is str and (not raw or raw.endswith('\n')),'SIDE_RECEIPT_TORN');return [strict(x) for x in raw.splitlines()]


def physical_snapshot(root,case_id):
    need(re.fullmatch('[a-z0-9-]{1,80}',case_id),'CASE_PATH')
    root=Path(root).absolute()
    def confined(rel):
        p=root/rel;need(p.resolve().is_relative_to(root) and not any(q.is_symlink() or q.is_junction() for q in (p,*p.parents)),'PHYSICAL_SCOPE')
        return p
    def raw(rel,optional=False):
        p=confined(rel)
        if optional and not p.exists():return None
        return p.read_bytes()
    def js(rel,optional=False):
        b=raw(rel,optional);return strict(b) if b is not None else None
    s='sessions/'+case_id+'/';v='receivers/'+case_id+'/';run='runs/'+case_id+'/'
    commits=[]
    for p in sorted(confined(s+'commits').glob('*.json')):
        need(re.fullmatch('[0-9]{2}.json',p.name),'COMMIT_FILE_NAME');commits.append(js(s+'commits/'+p.name))
    return dict(wal_raw=raw(s+'wal.jsonl').decode(),journal_commits=commits,before_recovery_hex=(raw(run+'pre-recovery.raw',True) or b'').hex(),operations_raw=(raw(s+'operations.jsonl',True) or b'').decode(),calls_raw=(raw(s+'calls.jsonl',True) or b'').decode(),unknown_commit=js(s+'unknown-commit.json',True),persist_failure=js(s+'persist-failure.json',True),unknown_intent=js(s+'unknown-intent.json',True),receiver_raw_hex=raw(v+'received.raw').hex(),receiver_receipt=js(v+'receipt.json'),ready=js(v+'ready.json'),processes=js(run+'processes.json'),host_summaries=[js(run+'host-'+phase+'.json',True) for phase in ('main','prepare','recover')])


def inspect(raw,anchor,source,spec,root=None):
    base=dict(source_authenticity='SOURCE_AUTHENTICITY_UNPROVEN',scope='LOCAL_LOOPBACK_ONLY_NOT_PROVIDER')
    try:
        need(anchor is not None,'ANCHOR_REQUIRED');need(sha(raw)==anchor,'OUTER_ANCHOR');v=strict(raw)
        fields={'abi','case_id','source','kind','fixture_sha256','wal_raw','journal_commits','before_recovery_hex','operations_raw','calls_raw','unknown_commit','persist_failure','unknown_intent','receiver_raw_hex','receiver_receipt','ready','processes','host_summaries'}
        need(type(v) is dict and set(v)==fields and v['abi']=='rpf81-bundle-v1' and v['source']==source and v['case_id']==spec['id'] and v['fixture_sha256']==digest(spec),'BUNDLE_IDENTITY')
        need(spec['input_sha256']==digest({k:z for k,z in spec.items() if k!='input_sha256'}),'PREREGISTERED_ROOT')
        kind='LOCAL_LOOPBACK_ONLY' if spec['localhost'] else 'FROZEN_UNSAFE_PROPOSAL'
        need(v['kind']==kind,'SOURCE_KIND');state=wal(v['wal_raw'].encode(),source,spec,kind)
        if not spec['localhost']:
            need([f['event']['kind'] for f in state['frames']]==spec['proposal_kinds'] and not v['receiver_raw_hex'] and v['receiver_receipt'] is None,'PROPOSAL_ROSTER')
            need(state['violations'],'UNSAFE_PROPOSAL_NOT_VIOLATING')
            return dict(**base,status='VIOLATION',classification='FROZEN_SEMANTIC_PROPOSAL',violations=state['violations'],actual_physical_send=False)
        need(root is not None,'PHYSICAL_FILES_REQUIRED');physical=physical_snapshot(root,spec['id'])
        need(all(v[k]==z for k,z in physical.items()),'PHYSICAL_RECEIPT_BINDING')
        acks=v['journal_commits'];need(len(acks)<=len(state['frames']),'COMMIT_HEAD_MISMATCH')
        for i,a in enumerate(acks):
            prefix=b'\n'.join(v['wal_raw'].encode().splitlines()[:i+1])+b'\n'
            need(a['seq']==i and a['frame_sha256']==state['frames'][i]['sha256'] and a['wal_sha256']==sha(prefix) and a['case_id']==spec['id'] and a['source']==source,'COMMIT_HEAD_BINDING')
        need(len(acks)==len(state['frames']) or v['persist_failure'] is not None,'UNACKNOWLEDGED_WAL')
        processes=v['processes'];receivers=[x for x in processes if x['role']=='receiver'];hosts=[x for x in processes if x['role']=='host']
        need(len(receivers)==1 and len(hosts)==(2 if spec['scenario']=='recovery' else 1),'PROCESS_ROSTER')
        receiver=receivers[0];pids={x['pid'] for x in hosts};need(receiver['pid'] not in pids and len(pids)==len(hosts),'INDEPENDENT_PROCESS')
        need(receiver['exit']==0 and all(x['exit']==(23 if x.get('phase')=='prepare' else 0) for x in hosts),'PROCESS_EXIT')
        if len(hosts)==2:
            before=bytes.fromhex(v['before_recovery_hex']);prior=wal(before,source,spec,kind)
            need(prior['unknown'] is not None and v['wal_raw'].encode().startswith(before),'DURABLE_RESTART_PREFIX')
        ready=v['ready'];receipt=v['receiver_receipt'];rx=bytes.fromhex(v['receiver_raw_hex'])
        need(ready['pid']==receipt['pid']==receiver['pid'] and receipt['address']==ready['address']=='127.0.0.1' and receipt['port']==ready['port'] and type(ready['port']) is int and 1024<=ready['port']<=65535,'RECEIVER_BINDING')
        need(receipt['source']==ready['source']==source and receipt['case_id']==ready['case_id']==spec['id'] and receipt['owner']=='rpf-81-rev-1' and receipt['bytes']==len(rx) and receipt['raw_sha256']==sha(rx),'RAW_RECEIVER_BINDING')
        need(all(f['event']['pid'] in pids for f in state['frames']),'HOST_PID_BINDING')
        ops=lines(v['operations_raw']);calls=lines(v['calls_raw']);need(all(x['pid'] in pids for x in ops+calls),'CALL_PID')
        entered=[x for x in calls if x['phase']=='SENDALL_ENTER'];returned=[x for x in calls if x['phase']=='SENDALL_RETURN'];errors=[x for x in calls if x['phase']=='IO_EXCEPTION'];connects=[x for x in calls if x['phase']=='CONNECT_ENTER']
        need(len(entered)<=4 and len(entered)==len(state['begins']),'SENDALL_WAL_PARITY')
        for x,b in zip(entered,state['begins']):need(x['source']==source and x['ticket']==b['ticket'] and x['mono']>=b['mono'] and x['size']==len(spec['payload'].encode()) and x['payload_sha256']==sha(spec['payload'].encode()),'CALL_PAYLOAD_BINDING')
        need({x['ticket'] for x in returned}==set(state['ends']),'SEND_END_PARITY')
        if rx:need(rx==spec['payload'].encode() and len(entered)==1,'ACTUAL_BYTES')
        if not entered:need(not rx and not receipt['bytes'],'UNEXPLAINED_RECEIVE')
        counts={action:dict(proposed=sum(x['action']==action for x in ops),allowed=sum(x['action']==action and x['decision']=='ALLOW' for x in ops),denied=sum(x['action']==action and x['decision']=='DENY' for x in ops)) for action in ('reserve','send','reconcile')}
        need(counts['reserve']['allowed']==len(state['tickets']),'RESERVE_COUNT_PARITY')
        for action in counts:counts[action]['attempted']=counts[action]['proposed']
        counts['send']['completion_inconclusive']=sum(x['action']=='send' and x['decision']=='INCONCLUSIVE' for x in ops)
        counts['send']['allowed']=len(state['begins'])
        counts['send']['admission_unresolved']=counts['send']['proposed']-counts['send']['allowed']-counts['send']['denied']
        counts['send']['actual_sendall']=len(entered)
        need(counts['send']['admission_unresolved']>=0,'SEND_ADMISSION_COUNTS')
        flags=[{k:f['event'][k] for k in ('planned','triggered','observed','agent_exposed')} for f in state['frames'] if f['event']['kind']=='UNKNOWN_OBSERVED']
        if state['violations']:return dict(**base,status='VIOLATION',classification='PHYSICAL_SESSION_SEMANTIC_VIOLATION',violations=state['violations'])
        commit=v['unknown_commit'];u=state['unknown']
        if commit is not None:need(u is not None and commit['seq']==u and commit['frame_sha256']==state['frames'][u]['sha256'] and commit['source']==source and commit['case_id']==spec['id'] and commit['mono']>=state['frames'][u]['event']['mono'],'UNKNOWN_COMMIT_BINDING')
        incomplete=not state['terminal'] or v['persist_failure'] is not None or bool(errors) or (u is not None and commit is None) or len(returned)!=len(entered) or (bool(entered) and not rx)
        classification='INCOMPLETE' if incomplete else 'PRE_UNKNOWN_IN_FLIGHT' if u is not None and state['begins'] else 'RECONCILE_ONLY' if u is not None else 'NORMAL_LOOPBACK'
        if classification=='PRE_UNKNOWN_IN_FLIGHT':need(all(x['seq']<u for x in state['begins']),'IN_FLIGHT_ORDER')
        return dict(**base,status='INCOMPLETE' if incomplete else 'CONFORMANT',classification=classification,unknown_seq=u,send_begin_seqs=[x['seq'] for x in state['begins']],new_reserve_after_unknown=0,old_ticket_send_after_unknown=0,counts=counts,actual_sendall_entries=len(entered),connect_attempts=len(connects),receiver_bytes=len(rx),receiver_pid=receiver['pid'],host_pids=sorted(pids),receiver_read_after_unknown_commit=bool(rx and commit and receipt['received_mono']>=commit['mono']),fault_axes=flags,persist_failure=v['persist_failure'],io_errors=[x['error'] for x in errors],restart=len(hosts)==2)
    except (ValueError,KeyError,TypeError,OSError,UnicodeError) as exc:return dict(**base,status='INVALID',classification=str(exc))
