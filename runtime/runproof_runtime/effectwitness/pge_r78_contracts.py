"""Offline synthetic forecast ABI, finite inputs, no resource locators."""
import hashlib
import json
from pathlib import Path
import re

OWNER='rpf-78-rev-1'
ABI='rpf78-offline-forecast-v1'
LEVEL='OFFLINE_SYNTHETIC_FORECAST_RELIABILITY_ONLY'
POLICIES=('R78-BOUNDED_ABSTAIN','R78-POINT_ESTIMATE','PGE-v3-utility','B0-fixed')
BUCKETS=('HIGH','LOW','RARE')
MIN_N=6
Z=1.96
METHOD='laplace-point-wilson-description-v1'
SHIFTS=('COST_UP','LABEL_FLIP','UNSEEN_BUCKET','EXPIRED_SOURCE','DELAY_FEEDBACK','REVERSE_CANDIDATES','MISSING_DOMAIN')
ROOT=Path(__file__).resolve().parents[3]
WORK=ROOT/'.local/rpf-78'
INPUTS=('spikes/rpf-78/development-catalog.json','spikes/rpf-78/challenge-catalog.json')
SOURCES=tuple('runtime/runproof_runtime/effectwitness/pge_r78_'+n+'.py' for n in (
    'contracts','provenance','forecast','calibration','policy','oracle','baselines','replay','metrics','verify'))+(
    'runtime/tests/test_effectwitness_pge_r78.py','spikes/rpf-78/probe.py')+INPUTS
REFERENCES=('AGENTS.md','runtime/runproof_runtime/effectwitness/pge_r77_utility.py',
    'runtime/runproof_runtime/effectwitness/pge_r77_policy.py','runtime/runproof_runtime/effectwitness/pge_r77_projection.py',
    'runtime/runproof_runtime/effectwitness/pge_r77_oracle.py','spikes/rpf-77/counterexamples.json')
LIMITATIONS=['SYNTHETIC_NON_IID','AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND','NO_REAL_WORLD_CALIBRATION',
             'NO_INTERVAL_COVERAGE_GUARANTEE','NO_AUTHORITY_OR_CAUSAL_PROOF','RPF74_PAUSED']
COUNTERS='decisions selects eligible_selects unsafe_select total_stop correct_stop stop_not_determinable missed_opportunity over_exploration wasted_simulated_cost simulated_cost verified_facts realized_synthetic_net_utility abstention_count appropriate_abstention unknown_bucket unsupported_forecast risk_guard_violation repeated redundant safety_rejections opportunity_cost'.split()


class Invalid(ValueError):
    pass


def require(ok,reason):
    if not ok:raise Invalid(reason)


def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def sha(x):return hashlib.sha256(x).hexdigest()
def digest(x):return sha(canonical(x))
def equal(a,b):return canonical(a)==canonical(b)


def strict(raw):
    def pairs(rows):
        result={}
        for k,v in rows:require(k not in result,'DUPLICATE_JSON');result[k]=v
        return result
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'NONFINITE'))
    except (UnicodeError,json.JSONDecodeError) as exc:raise Invalid('JSON_STRUCTURE') from exc


def keys(x,names,reason):require(type(x) is dict and set(x)==set(names.split()),reason)
def integer(x,reason,low=0,high=1_000_000):require(type(x) is int and low<=x<=high,reason)
def ident(x,reason):require(type(x) is str and re.fullmatch('[a-z][a-z0-9-]{1,95}',x) is not None,reason)
def hexsha(x,reason):require(type(x) is str and re.fullmatch('[a-f0-9]{64}',x) is not None,reason)


def normalize(v):
    return dict(v,candidates=sorted(v['candidates'],key=lambda x:x['candidate_id']),permissions=sorted(v['permissions']))


def snapshot_sha(v):return digest(normalize(v))


def validate(v):
    keys(v,'schema case_id split domain snapshot_id candidates budget risk_cap permissions deadline max_steps initial_elapsed initial_unknown','VIEW_SCHEMA')
    require(v['schema']==ABI and v['split'] in ('fit','development_validation','challenge','stress'),'VIEW_ID')
    for field in ('case_id','domain','snapshot_id'):ident(v[field],'ID_'+field)
    require(v['domain'].startswith('lab-'),'ABSTRACT_DOMAIN')
    for name in ('budget','risk_cap','deadline','max_steps','initial_elapsed'):
        integer(v[name],name.upper(),high=dict(risk_cap=3,deadline=100,max_steps=2,initial_elapsed=100).get(name,1_000_000))
    require(v['deadline']>=1 and v['max_steps']>=1,'POSITIVE_LIMIT')
    require(type(v['permissions']) is list and len(set(v['permissions']))==len(v['permissions']) and set(v['permissions'])<={'observe','simulate'},'PERMISSIONS')
    require(type(v['initial_unknown']) is list and len(set(v['initial_unknown']))==len(v['initial_unknown']),'UNKNOWN_DOMAINS')
    for d in v['initial_unknown']:ident(d,'UNKNOWN_DOMAIN')
    require(type(v['candidates']) is list and len(v['candidates'])<=6,'POOL_SIZE')
    ids=[]
    for x in v['candidates']:
        keys(x,'candidate_id snapshot_id domain feature_kind feature_status visible_at valid_until source_id source_sha256 source_kind benefit_units cost risk permission requires effect_keys verification_need freshness_need value_update_kind order repeat contract_sha256','CANDIDATE_SCHEMA')
        ident(x['candidate_id'],'CANDIDATE_ID');ident(x['source_id'],'SOURCE_ID')
        require(x['domain']==v['domain'] and x['snapshot_id']==v['snapshot_id'] and x['candidate_id'].startswith(v['domain']+'-'),'CANDIDATE_SCOPE')
        for name in ('benefit_units','cost','risk','verification_need','freshness_need','visible_at','valid_until','order'):
            integer(x[name],'FEATURE_'+name,low=1 if name=='cost' else 0,high=dict(risk=3,verification_need=2,freshness_need=2,order=6,visible_at=100,valid_until=100).get(name,1_000_000))
        require(x['feature_kind'] in (*BUCKETS,'UNSEEN') and x['feature_status'] in ('KNOWN','UNKNOWN') and x['value_update_kind'] in ('UPDATE','REVALIDATE','NONE'),'FEATURE_ENUM')
        require(x['permission'] in ('observe','simulate') and type(x['repeat']) is bool,'CANDIDATE_MODE')
        require(x['source_kind']=='SYNTHETIC_CONTRACT','CANDIDATE_SOURCE');hexsha(x['source_sha256'],'SOURCE_SHA')
        require(x['source_sha256']==digest({k:z for k,z in x.items() if k not in ('source_sha256','contract_sha256')}),'SOURCE_CONTENT_SHA')
        for name in ('requires','effect_keys'):
            require(type(x[name]) is list and len(set(x[name]))==len(x[name]) and len(x[name])<=12,'FACT_KEYS')
            for key in x[name]:ident(key,'FACT_ID')
        require(x['contract_sha256']==digest({k:z for k,z in x.items() if k!='contract_sha256'}),'CANDIDATE_ANCHOR')
        ids.append(x['candidate_id'])
    require(len(set(ids))==len(ids),'DUPLICATE_CANDIDATE')


def seal(case):
    v=case['view']
    for x in v['candidates']:
        x['source_sha256']=digest({k:z for k,z in x.items() if k not in ('source_sha256','contract_sha256')})
        x['contract_sha256']=digest({k:z for k,z in x.items() if k!='contract_sha256'})
    for r in case['records']:r['contract_sha256']=snapshot_sha(v)
    case['roster']=dict(case_id=v['case_id'],entries={r['evidence_id']:digest(r) for r in case['records']})
    case['roster_sha256']=digest(case['roster'])
    return case


def case_valid(case):
    keys(case,'view records roster roster_sha256 outcomes design parent_raw_sha256 transform','CASE_SCHEMA');v=case['view'];validate(v)
    keys(case['roster'],'case_id entries','ROSTER_SCHEMA')
    require(case['roster']['case_id']==v['case_id'] and case['roster_sha256']==digest(case['roster'])
        and case['roster']['entries']=={r['evidence_id']:digest(r) for r in case['records']}
        and len(case['records'])==len(case['roster']['entries']),'FROZEN_ROSTER')
    require(set(case['outcomes'])=={x['candidate_id'] for x in v['candidates']},'OUTCOME_POOL')
    for o in case['outcomes'].values():
        keys(o,'outcome_id useful_effect status facts','OUTCOME_SCHEMA');ident(o['outcome_id'],'OUTCOME_ID')
        require(type(o['useful_effect']) is int and o['useful_effect'] in (0,1) and o['status'] in ('VERIFIED','UNKNOWN','INCONCLUSIVE','OBSERVED')
            and type(o['facts']) is dict and all(type(k) is str and type(z) is str for k,z in o['facts'].items()),'OUTCOME_VALUE')


def catalogs():
    dev=strict((ROOT/INPUTS[0]).read_bytes());challenge=strict((ROOT/INPUTS[1]).read_bytes())
    keys(dev,'schema owner seed fit development_validation exposure','DEV_SCHEMA')
    keys(challenge,'schema owner seed challenge exposure','CHALLENGE_SCHEMA')
    require(dev['schema']==challenge['schema']==ABI and dev['owner']==challenge['owner']==OWNER,'CATALOG_ID')
    require(dev['exposure']=='DEVELOPMENT' and challenge['exposure']=='AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND','EXPOSURE')
    require(len(dev['fit'])==24 and len(dev['development_validation'])==12 and len(challenge['challenge'])==18,'CASE_COUNT')
    ids=[];outcome_ids=[]
    for split,rows in [('fit',dev['fit']),('development_validation',dev['development_validation']),('challenge',challenge['challenge'])]:
        for case in rows:
            case_valid(case);require(case['view']['split']==split,'SPLIT_SCOPE');ids.append(case['view']['case_id'])
            outcome_ids.extend(o['outcome_id'] for o in case['outcomes'].values())
    require(len(set(ids))==len(ids) and len(set(outcome_ids))==len(outcome_ids),'SPLIT_ID_OVERLAP')
    return dev,challenge


def initial(v):return dict(step=0,remaining=v['budget'],elapsed=v['initial_elapsed'],attempted=[],unknown_domains=sorted(v['initial_unknown']))


def state_valid(v,s):
    keys(s,'step remaining elapsed attempted unknown_domains','STATE_SCHEMA')
    integer(s['step'],'STATE_STEP',high=v['max_steps']);integer(s['remaining'],'STATE_BUDGET',high=v['budget']);integer(s['elapsed'],'STATE_TIME',high=102)
    require(type(s['attempted']) is list and len(s['attempted'])==s['step'] and set(s['attempted'])<={x['candidate_id'] for x in v['candidates']},'STATE_ATTEMPTED')
    require(type(s['unknown_domains']) is list and len(set(s['unknown_domains']))==len(s['unknown_domains']),'STATE_UNKNOWN')
    for d in s['unknown_domains']:ident(d,'STATE_UNKNOWN_ID')


def allowed_file(value):
    p=Path(value).absolute();require(p.suffix=='.json' and (p==ROOT/'spikes/rpf-78/decision-traces.json' or p.is_relative_to(WORK)),'FILE_SCOPE')
    for q in (p,)+tuple(p.parents):
        require(not q.is_symlink() and not (hasattr(q,'is_junction') and q.is_junction()),'FILE_LINK')
        if q==ROOT:break
    require(p.resolve()==p,'FILE_SCOPE');return p


def source_map():
    rows=[]
    for rel in SOURCES+REFERENCES:
        raw=(ROOT/rel).read_bytes();lf=raw.replace(b'\r\n',b'\n')
        rows.append(dict(path=rel,bytes=len(raw),raw_sha256=sha(raw),lf_sha256=sha(lf),git_blob=hashlib.sha1(b'blob '+str(len(lf)).encode()+b'\0'+lf).hexdigest()))
    return dict(owner=OWNER,abi=ABI,files=rows)


def source_identity():return digest(source_map())
