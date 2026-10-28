"""New synthetic cases plus explicitly exposed RPF76 diagnostic projections."""
import copy
from . import pge_r77_contracts as c


def seal(case):
    v = case['view']
    for x in v['candidates']:
        x['contract_sha256'] = c.digest({k: z for k, z in x.items() if k != 'contract_sha256'})
    for record in case['records']:
        record['contract_sha256'] = c.snapshot_sha(v)
    case['roster'] = dict(case_id=v['case_id'], entries={r['evidence_id']: c.digest(r) for r in case['records']})
    case['roster_sha256'] = c.digest(case['roster'])
    return case


def make(split):
    c.require(split in ('development', 'challenge'), 'SPLIT_ID')
    domains = ('lab-lumen', 'lab-mica', 'lab-oxide') if split == 'development' else ('lab-nacre', 'lab-sable', 'lab-zircon')
    cases = []
    for index in range(30 if split == 'development' else 18):
        kind = index % 12
        domain = domains[index % 3]
        cid = ('dev-' if split == 'development' else 'challenge-') + str(index).zfill(2)
        size = 1 + index % 4 if split == 'development' else 4 + index % 3
        snapshot = cid + '-snapshot-0'
        pool = []
        for i in range(size):
            x = dict(candidate_id=domain+'-c'+str(i), snapshot_id=snapshot, domain=domain,
                     cost=7 if kind == 1 else 2+i, risk=2 if kind == 1 else i%3,
                     permission='simulate', requires=['fact-00'], effect_keys=['fact-'+str(i+1).zfill(2)],
                     priority=size-i, order=i, repeat=index%2 == 0,
                     verification_need=2 if kind == 9 and i == 0 else 1 if kind in (0,5,11) and i == 0 else 0,
                     freshness_need=1 if kind == 0 and i == 0 else 0,
                     value_update_kind='UPDATE' if kind == 0 and i == 0 else 'NONE',
                     feature_status='UNKNOWN' if kind == 8 else 'KNOWN', feature_visible_at=0,
                     source_kind='SYNTHETIC_CONTRACT', source_sha256=c.digest(dict(source='PUBLIC_OBSERVABLE_ESTIMATE',domain=domain,kind=kind,i=i)))
            pool.append(x)
        v = dict(schema=c.ABI, case_id=cid, split=split, snapshot_id=snapshot, domain=domain,
                 fact_keys=['fact-'+str(i).zfill(2) for i in range(12)], candidates=pool,
                 budget=0 if kind == 6 else 20, risk_cap=2, permissions=['observe','simulate'],
                 deadline=1 if kind == 7 else 6, max_steps=3, initial_elapsed=1 if kind == 7 else 0,
                 initial_unknown=[domain] if kind == 4 else ['lab-unrelated'] if kind == 5 else [])
        seed = {'fact-00':'ready'}
        if kind in (0,10):
            seed.update({name:'seen' for x in pool for name in x['effect_keys']})
        def record(name, at, facts, **changes):
            r = dict(evidence_id=cid+'-'+name,case_id=cid,domain=domain,snapshot_id=snapshot,
                     contract_sha256='',visible_at=at,seq=at+1,status='VERIFIED',source_kind='FROZEN_SYNTHETIC',facts=facts)
            r.update(changes)
            return r
        records = [record('initial',0,seed,source_kind='MODEL_ASSERTION' if kind == 3 else 'FROZEN_SYNTHETIC'),
                   record('update',1,{'fact-01':'seen'})]
        if kind == 2:
            records.append(record('conflict',0,{'fact-00':'not-ready'}))
        good = [pool[0]['candidate_id']] if kind in (0,5,10,11) else []
        unknown = sorted(x['candidate_id'] for x in pool) if kind == 8 else []
        bad = sorted({x['candidate_id'] for x in pool}-set(good)-set(unknown))
        outcomes = {x['candidate_id']:dict(status='UNKNOWN' if kind == 5 and i == 0 else 'VERIFIED',
                    facts={} if kind == 5 and i == 0 else {key:'outcome-'+str(i) for key in x['effect_keys']}) for i,x in enumerate(pool)}
        cases.append(seal(dict(view=c.normalize(v),records=records,roster={},roster_sha256='',
            evaluation=dict(rules=c.RULES,worthwhile_ids=good,no_benefit_ids=bad,ambiguous_ids=unknown),
            outcomes=outcomes,kind=kind,source_kind='SYNTHETIC_OFFLINE')))
    return dict(schema=c.ABI,owner=c.OWNER,split=split,seed=7701 if split=='development' else 7702,
                exposure='DEVELOPMENT' if split=='development' else 'CHALLENGE_AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND',cases=cases)


def validate_case(case):
    c.keys(case, 'view records roster roster_sha256 evaluation outcomes kind source_kind', 'CASE_SCHEMA')
    v = case['view']
    c.validate(v)
    c.require(case['source_kind']=='SYNTHETIC_OFFLINE', 'SYNTHETIC_LABEL')
    pool = {x['candidate_id'] for x in v['candidates']}
    c.keys(case['evaluation'], 'rules worthwhile_ids no_benefit_ids ambiguous_ids', 'EVALUATION_SCHEMA')
    c.require(c.equal(case['evaluation']['rules'],c.RULES), 'RULES_ID')
    labels = [set(case['evaluation'][key]) for key in ('worthwhile_ids','no_benefit_ids','ambiguous_ids')]
    c.require(set.union(*labels)==pool and all(not a&b for i,a in enumerate(labels) for b in labels[i+1:]), 'LABEL_PARTITION')
    c.require(case['roster_sha256']==c.digest(case['roster']) and case['roster']['entries']=={r['evidence_id']:c.digest(r) for r in case['records']}
              and len(case['records'])==len(case['roster']['entries']), 'FROZEN_ROSTER')
    c.require(set(case['outcomes'])==pool, 'OUTCOME_POOL')
    for o in case['outcomes'].values():
        c.keys(o,'status facts','OUTCOME_SCHEMA')
        c.require(o['status'] in ('VERIFIED','OBSERVED','INCONCLUSIVE','UNKNOWN') and type(o['facts']) is dict
                  and set(o['facts'])<=set(v['fact_keys']) and all(type(x) is str for x in o['facts'].values()),'OUTCOME_VALUE')


def load(split):
    c.require(split in ('development','challenge'), 'SPLIT_ID')
    data = c.strict((c.ROOT/c.INPUTS[0 if split=='development' else 1]).read_bytes())
    c.keys(data,'schema owner split seed exposure cases','CATALOG_SCHEMA')
    c.require(data['schema']==c.ABI and data['owner']==c.OWNER and data['split']==split,'CATALOG_ID')
    c.require(len(data['cases'])==(30 if split=='development' else 18),'CASE_COUNT')
    c.require(data['exposure']==('DEVELOPMENT' if split=='development' else 'CHALLENGE_AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND'),'EXPOSURE')
    ids=[]
    for case in data['cases']:
        validate_case(case)
        c.require(case['view']['split']==split,'SPLIT_SCOPE')
        ids.append(case['view']['case_id'])
    c.require(len(set(ids))==len(ids),'DUPLICATE_CASE')
    return data


def diagnostic76():
    """Map three public exposed inputs; no historical runtime or private Run read."""
    cases=[]
    for filename,wanted in (('fixture-catalog.json',('dev-01','dev-13')),('holdout-catalog.json',('hold-01',))):
        data=c.strict((c.ROOT/'spikes/rpf-76'/filename).read_bytes())
        for old in data['cases']:
            if old['view']['case_id'] not in wanted:
                continue
            ov=old['view'];cid='diag-'+ov['case_id'];snapshot=cid+'-snapshot-0'
            pool=[]
            for x in ov['candidates']:
                pool.append(dict(candidate_id=x['candidate_id'],snapshot_id=snapshot,domain=x['domain'],
                    cost=x['cost'],risk=x['risk'],permission=x['permission'],requires=x['requires'],effect_keys=x['effects'],
                    priority=x['priority'],order=x['order'],repeat=x['repeat'],verification_need=0,freshness_need=0,
                    value_update_kind='NONE',feature_status='UNKNOWN',feature_visible_at=0,source_kind='SYNTHETIC_CONTRACT',
                    source_sha256=x['source_sha256']))
            v=dict(schema=c.ABI,case_id=cid,split='diagnostic76',snapshot_id=snapshot,domain=ov['domain'],fact_keys=ov['fact_keys'],
                   candidates=pool,budget=ov['budget'],risk_cap=ov['risk_cap'],permissions=ov['permissions'],deadline=ov['deadline'],
                   max_steps=ov['max_steps'],initial_elapsed=0,initial_unknown=ov['initial_unknown'])
            records=[dict(evidence_id=cid+'-record-'+str(i),case_id=cid if r['case_id']==ov['case_id'] else 'diag-foreign-case',domain=r['domain'],snapshot_id=snapshot,contract_sha256='',
                          visible_at=r['visible_at'],seq=r['seq'],status=r['status'],source_kind=r['source_kind'],facts=r['facts']) for i,r in enumerate(old['records'])]
            worth=old['oracle']['worthwhile_ids'];others=set(old['outcomes'])-set(worth)
            cases.append(seal(dict(view=c.normalize(v),records=records,roster={},roster_sha256='',
                evaluation=dict(rules=c.RULES,worthwhile_ids=worth,no_benefit_ids=sorted(others),ambiguous_ids=[]),
                outcomes=copy.deepcopy(old['outcomes']),kind='RPF76_EXPOSED_DIAGNOSTIC',source_kind='SYNTHETIC_OFFLINE')))
    c.require(len(cases)==3,'DIAGNOSTIC_COUNT')
    return cases
