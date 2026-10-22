"""Independent rev-2 staged RPF65 runner. No old live/metadata/cold entrypoints."""
import argparse, hashlib, os, sys, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from runtime.runproof_runtime.effectwitness import pge_r65_context as c, pge_r65_session as s, pge_r65_target_config as port, pge_r65_verify as v

WORK=ROOT/'.local/rpf-65-rev-2'
def load():
    ctx=c.TaskContext(WORK,c.canonical(c.strict_json((WORK/'context.json').read_bytes()))); return ctx,c.Ledger(ctx,WORK/'account')
def main():
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=('init','metadata','cold','live','verify')); a=p.parse_args()
    if a.mode=='init':
        _,old=c.helpers(); ports=[]
        for _ in range(16):
            n=old._free_port()
            if n>=1024 and n not in ports: ports.append(n)
            if len(ports)==4: break
        c.require(len(ports)==4,'PORTS_UNAVAILABLE')
        ctx=c.make_context(uuid.uuid4().hex[:16],tuple(ports[:2]),tuple(ports[2:])); ctx.once(WORK/'context.json',ctx.public()); c.Ledger(ctx,WORK/'account',create=True); print(c.canonical({'status':'INITIALIZED','sources_sha256':c.digest(c.sources())}).decode()); return 0
    ctx,ledger=load()
    if a.mode=='metadata':
        c.require(not (WORK/'preflight/metadata.json').exists(),'METADATA_EXISTS'); c.metadata(ctx,ledger); print('METADATA_PASS'); return 0
    if a.mode=='cold':
        meta=c.strict_json((WORK/'preflight/metadata.json').read_bytes()); c.require(meta['sources']==c.sources(),'METADATA_SOURCE'); s.cold(ctx,ledger,meta); print('COLD_PASS'); return 0
    if a.mode=='live':
        c.require(ledger.read()['counts']['provider']==ledger.read()['counts']['session']==0,'LIVE_CONSUMED')
        meta=c.strict_json((WORK/'preflight/metadata.json').read_bytes()); cold=c.strict_json((WORK/'preflight/cold.json').read_bytes())
        gate=c.strict_json((WORK/'paid-gate.json').read_bytes()); c.require(gate=={'status':'PASS','revision':'rev-2','paid_permission':'RPF-65/rev-2/P2_USER_AUTHORIZED','sources_sha256':c.digest(c.sources()),'price':c.PRICE,'tokens':15000,'cost_cny_upper':0.5,'zero_provider_tests':True,'freeze':True},'PAID_GATE')
        c.require(meta['sources']==cold['sources']==c.sources() and cold['status']=='PASS' and ledger.read()['counts']['cold']==1,'FREE_GATE')
        c.require(all(ledger.read()['counts'][r]==0 for r in ('session','trial','jvm','sdk','provider','http','post','health')) and set(ledger.read()['tickets'])==set(ledger.read()['results']),'UNCONSUMED_LIVE_RESOURCES')
        ctx.once(WORK/'live-admission.json',{'revision':'rev-2','context_sha256':c.digest(ctx.public()),'sources_sha256':c.digest(c.sources())})
        key=os.environ.get('DEEPSEEK_API_KEY'); c.require(type(key) is str and bool(key),'PROVIDER_KEY_UNAVAILABLE')
        try:
            row=s.Session().execute(ctx,ledger,port.ConfigPort(key)); payload=dict(source_kind=c.REAL,context=ctx.public(),row=row,cold=cold,ledger=ledger.read() and ledger.frames,boundaries=c.BOUNDARIES)
            result=v.verify_payload(payload); raw=c.canonical(v.seal(payload)); ctx.once(WORK/'trial-result.json',{'status':'PASS','verdict':result,'witness_sha256':hashlib.sha256(raw).hexdigest()})
            target=ROOT/'spikes/rpf-65/rev-2/target-witness.json'
            with target.open('xb') as f: f.write(raw)
            print(c.canonical(result).decode()); return 0
        except Exception as exc:
            ctx.once(WORK/'trial-failure.json',{'error_type':type(exc).__name__,'code':getattr(exc,'code','PLATFORM_ERROR'),'counts':ledger.read()['counts']}); print(getattr(exc,'code',type(exc).__name__)); return 3
        finally: key=None
    path=ROOT/'spikes/rpf-65/rev-2/target-witness.json'; print(c.canonical(v.verify_bytes(path.read_bytes(),hashlib.sha256(path.read_bytes()).hexdigest())).decode()); return 0
if __name__=='__main__': raise SystemExit(main())
