"""Offline scheduler with frozen truth lookup after SELECT, separate stress runs."""
import copy
from . import pge_r78_contracts as c
from .pge_r78_provenance import project,eligibility
from .pge_r78_forecast import estimate
from .pge_r78_policy import decide
from .pge_r78_oracle import evaluate
from .pge_r78_metrics import comparison


def stress_cases(challenge):
    result=[]
    for parent in challenge:
        for transform in c.SHIFTS:
            case=copy.deepcopy(parent);v=case['view'];old=v['case_id'];cid=old+'-s-'+transform.lower().replace('_','-')
            v.update(case_id=cid,split='stress',snapshot_id=cid+'-snapshot');case.update(parent_raw_sha256=c.digest(parent),transform=transform)
            outcomes={}
            old_domain=v['domain'];domain='lab-absent' if transform=='MISSING_DOMAIN' else old_domain;v['domain']=domain
            v['initial_unknown']=[domain if d==old_domain else d for d in v['initial_unknown']]
            for i,x in enumerate(v['candidates']):
                o=case['outcomes'][x['candidate_id']];x.update(candidate_id=domain+'-'+cid+'-c'+str(i),domain=domain,snapshot_id=v['snapshot_id'])
                o['outcome_id']='outcome-'+cid+'-c'+str(i)
                if transform=='COST_UP':x['cost']+=3
                if transform=='LABEL_FLIP':o['useful_effect']=1-o['useful_effect']
                if transform=='UNSEEN_BUCKET':x['feature_kind']='UNSEEN'
                outcomes[x['candidate_id']]=o
            case['outcomes']=outcomes
            if transform=='EXPIRED_SOURCE':v['initial_elapsed']=max(1,v['initial_elapsed'])
            for i,r in enumerate(case['records']):
                r.update(evidence_id=cid+'-r'+str(i),case_id=cid,domain=domain,snapshot_id=v['snapshot_id'])
                if transform=='EXPIRED_SOURCE':r['valid_until']=0
                if transform=='DELAY_FEEDBACK':r.update(visible_at=3,seq=4)
            if transform=='REVERSE_CANDIDATES':v['candidates'].reverse()
            case['view']=c.normalize(v);c.seal(case);result.append(case)
    return result


def replay_case(case,policy,model,reverse=False):
    v=case['view'];s=c.initial(v);rows=[];prev='0'*64
    for _ in range(v['max_steps']+1):
        records=sorted([r for r in case['records'] if r['visible_at']<=s['step']],key=lambda r:r['evidence_id'])
        supplied=dict(v,candidates=list(reversed(v['candidates']))) if reverse else v
        d=decide(supplied,list(reversed(records)) if reverse else records,s,case['roster'],case['roster_sha256'],model,policy)
        oracle=evaluate(case,records,s);outcome=case['outcomes'][d['candidate_id']] if d['action']=='SELECT' else None
        row=dict(seq=len(rows)+1,state=s,snapshot_sha256=c.snapshot_sha(v),records=records,roster=case['roster'],roster_sha256=case['roster_sha256'],decision=d,oracle=oracle,outcome=outcome,previous_sha256=prev)
        row['sha256']=c.digest(row);prev=row['sha256'];rows.append(row)
        if outcome is None:break
        unknown=set(s['unknown_domains'])|({v['domain']} if outcome['status']=='UNKNOWN' else set())
        s=dict(step=s['step']+1,remaining=s['remaining']-d['cost'],elapsed=s['elapsed']+1,attempted=s['attempted']+[d['candidate_id']],unknown_domains=sorted(unknown))
    return dict(case_id=v['case_id'],split=v['split'],policy=policy,snapshot=v,parent_raw_sha256=case['parent_raw_sha256'],transform=case['transform'],rows=rows)


def run(model,scope='MAIN',reverse=False):
    dev,challenge=c.catalogs();cases=dev['development_validation']+challenge['challenge'] if scope=='MAIN' else stress_cases(challenge['challenge'])
    predictions=[]
    for case in cases:
        v=case['view'];s=c.initial(v);records=[r for r in case['records'] if r['visible_at']<=s['step']]
        ev=project(v,records,case['roster'],case['roster_sha256'],s);_,allowed,_=eligibility(v,s,ev)
        for x in sorted(allowed,key=lambda z:z['candidate_id']):
            predictions.append(dict(split=v['split'],case_id=v['case_id'],candidate_id=x['candidate_id'],forecast=estimate(x,model,s,ev),observed_useful=case['outcomes'][x['candidate_id']]['useful_effect']))
    runs=[replay_case(case,p,model,reverse) for case in cases for p in c.POLICIES]
    value=dict(schema=c.ABI,owner=c.OWNER,level=c.LEVEL,scope=scope,source_sha256=c.source_identity(),
        input_sha256={p:c.sha((c.ROOT/p).read_bytes()) for p in c.INPUTS},model=model,model_raw_sha256=c.digest(model),
        exposure='AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND',runs=runs,predictions=predictions,comparison=comparison(runs,predictions),limitations=c.LIMITATIONS)
    value['result_sha256']=c.digest(value);return value
