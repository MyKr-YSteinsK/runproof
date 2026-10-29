"""Task-only immutable identities, scope, finite limits; no Provider API."""
import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import time

ROOT=Path(__file__).resolve().parents[3]
WORK=ROOT/'.local/rpf-81-durable-unknown-presend-loopback'
OWNER='rpf-81-rev-1'
ABI='rpf81-loopback-v1'
KIND='LOCAL_LOOPBACK_ONLY'
SOURCES=tuple('runtime/runproof_runtime/effectwitness/pge_r81_'+n+'.py' for n in ('contracts','journal','barrier','loopback','oracle'))+('runtime/tests/test_effectwitness_pge_r81.py','spikes/rpf-81/probe.py','spikes/rpf-81/fixtures.json')


def require(ok,reason):
    if not ok:raise ValueError(reason)


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(x):return sha(canonical(x))


def strict(raw):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'DUPLICATE_KEY');out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'NONFINITE'))


def clock():return dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),mono=time.monotonic(),pid=os.getpid())


def scope(path):
    p=Path(path).absolute();require(p.is_relative_to(WORK) and p.resolve()==p,'TASK_SCOPE')
    for q in (p,*p.parents):
        require(not q.is_symlink() and not q.is_junction(),'REPARSE')
        if q==ROOT:break
    return p


def source_map():return {p:dict(raw_sha256=sha((ROOT/p).read_bytes()),lf_sha256=sha((ROOT/p).read_bytes().replace(b'\r\n',b'\n'))) for p in SOURCES}
def source_id():return digest(source_map())


def spec(case_id):
    if re.fullmatch(r'unit-[a-z0-9-]+-[0-9]+',case_id):return dict(id=case_id,scenario='unit',payload='UNIT_NO_SEND',localhost=False)
    rows=strict((ROOT/'spikes/rpf-81/fixtures.json').read_bytes())['cases']
    require(case_id in {x['id'] for x in rows},'CASE_ROSTER');return next(x for x in rows if x['id']==case_id)


def case_dir(case_id):
    spec(case_id);return scope(WORK/'sessions'/case_id)


def once(path,value):
    p=scope(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())


def append(path,value):
    with scope(path).open('ab') as f:f.write(canonical(value)+b'\n');f.flush();os.fsync(f.fileno())


class WriterLock:
    """Nonblocking kernel byte lock, held until close/process exit."""
    def __init__(self,path):
        p=scope(path)
        try:
            with p.open('xb') as f:f.write(b'0');f.flush();os.fsync(f.fileno())
        except FileExistsError:pass
        self.file=p.open('r+b',buffering=0)
        try:
            require(p.stat().st_size==1,'LOCK_CONTENT')
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:self.file.close();raise ValueError('WRITER_LOCK_UNAVAILABLE')
    def close(self):self.file.close()


def claim_send(case_id,ticket,payload):
    require(spec(case_id)['localhost'] and 0<len(payload)<=4096,'SEND_SCOPE_LIMIT')
    folder=scope(WORK/'budget');folder.mkdir(exist_ok=True)
    lock=WriterLock(folder/'writer.lock')
    try:
        path=folder/'send-attempts.jsonl';raw=path.read_bytes() if path.exists() else b''
        require(not raw or raw.endswith(b'\n'),'BUDGET_TORN')
        rows=[strict(line) for line in raw.splitlines()];require(len(rows)<64,'GLOBAL_SEND_LIMIT')
        require(sum(x['case_id']==case_id for x in rows)<4,'CASE_SEND_LIMIT')
        for i,x in enumerate(rows):require(x['ordinal']==i+1 and re.fullmatch('[a-f0-9]{64}',x['source']) and x['owner']==OWNER,'BUDGET_IDENTITY')
        append(path,dict(ordinal=len(rows)+1,owner=OWNER,case_id=case_id,ticket=ticket,bytes=len(payload),payload_sha256=sha(payload),source=source_id(),**clock()))
    finally:lock.close()


@contextlib.contextmanager
def serial(lock):
    require(lock.acquire(timeout=2),'SERIAL_LOCK_TIMEOUT')
    try:yield
    finally:lock.release()
