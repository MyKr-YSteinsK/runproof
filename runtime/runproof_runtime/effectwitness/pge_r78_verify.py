"""Independent fit, inference, Oracle and metrics. No generator imports."""
import copy
import math
from . import pge_r78_contracts as c


def expected_model(fit_cases,source):
    counts={k:dict(n=0,k=0) for k in c.BUCKETS};ids=[];oids=[];domains=set()
    for case in fit_cases:
        c.require(case['view']['split']=='fit','FIT_PARTITION_ONLY');ids.append(case['view']['case_id']);domains.add(case['view']['domain'])
        for x in case['view']['candidates']:
            o=case['outcomes'][x['candidate_id']];c.require(o['status']=='VERIFIED','FIT_COMPLETED_ONLY')
            oids.append(o['outcome_id']);counts[x['feature_kind']]['n']+=1;counts[x['feature_kind']]['k']+=o['useful_effect']
    buckets={}
    for name,counts_row in counts.items():
        n,k=counts_row['n'],counts_row['k']
        if n:
            d=1+c.Z**2/n;a=(k/n+c.Z**2/(2*n))/d;b=c.Z*math.sqrt((k/n)*(1-k/n)/n+c.Z**2/(4*n*n))/d
            low,high=round(max(0,a-b),12),round(min(1,a+b),12)
        else:low,high=0.0,1.0
        buckets[name]=dict(n=n,positive=k,p_hat=round((k+1)/(n+2),12),lower=low,upper=high,width=round(high-low,12),status='SUPPORTED' if n>=c.MIN_N else 'INSUFFICIENT_SUPPORT')
    return dict(schema=c.ABI,owner=c.OWNER,method=c.METHOD,source_sha256=source,target='useful_effect-binary-v1',fit_partition='fit',
        fit_case_ids=sorted(ids),fit_outcome_ids=sorted(oids),fit_input_sha256=c.digest(fit_cases),domain_support=sorted(domains),min_n=c.MIN_N,z=c.Z,buckets=buckets,
        warning='DESCRIPTIVE_SYNTHETIC_NON_IID_NO_COVERAGE_GUARANTEE')


def expected_evidence(v,records,case,s):
    facts={};accepted=[];refused=[];conflict=False
    for r in sorted(records,key=lambda z:z['evidence_id']):
        c.require(case['roster']['entries'].get(r['evidence_id'])==c.digest(r),'FROZEN_ROSTER_MEMBER')
        why=('FUTURE' if r['visible_at']>s['step'] or r['seq']>s['step']+1 else 'LATE' if r['seq']<r['visible_at']+1
            else 'EXPIRED' if r['valid_until']<s['elapsed'] else 'CROSS_CASE' if r['case_id']!=v['case_id'] else
            'CROSS_DOMAIN' if r['domain']!=v['domain'] else 'SNAPSHOT' if r['snapshot_id']!=v['snapshot_id'] else
            'CONTRACT' if r['contract_sha256']!=c.snapshot_sha(v) else 'SOURCE' if r['source_kind']!='FROZEN_SYNTHETIC' else 'STATUS' if r['status']!='VERIFIED' else None)
        if why:refused.append(dict(evidence_id=r['evidence_id'],reason=why))
        else:
            for key,value in r['facts'].items():conflict=conflict or (key in facts and facts[key]!=value);facts[key]=value
            accepted.append(dict(evidence_id=r['evidence_id'],raw_sha256=c.digest(r)))
    return dict(facts=facts,accepted=accepted,refused=refused,conflict=conflict)


def eligible(v,s,ev):
    barrier='UNKNOWN_STOP' if v['domain'] in s['unknown_domains'] else 'TIME_STOP' if s['elapsed']>=v['deadline'] else 'STEP_STOP' if s['step']>=v['max_steps'] else None
    yes=[];no=[]
    if not barrier and ev['accepted'] and not ev['conflict']:
        for x in v['candidates']:
            why='REPEAT' if not x['repeat'] and x['candidate_id'] in s['attempted'] else 'BUDGET' if x['cost']>s['remaining'] else 'RISK' if x['risk']>v['risk_cap'] else 'PERMISSION' if x['permission'] not in v['permissions'] else 'PRECONDITION' if not set(x['requires'])<=ev['facts'].keys() else None
            if why:no.append(dict(candidate_id=x['candidate_id'],reason=why))
            else:yes.append(x)
    return barrier,yes,sorted(no,key=lambda z:z['candidate_id'])


def expected_forecast(x,m,s,ev):
    status='UNTRUSTED_EVIDENCE' if ev['conflict'] or not ev['accepted'] else 'UNKNOWN_FEATURE' if x['feature_status']=='UNKNOWN' else 'FUTURE_FEATURE' if x['visible_at']>s['elapsed'] else 'EXPIRED_FEATURE' if x['valid_until']<s['elapsed'] else 'UNSUPPORTED_DOMAIN' if x['domain'] not in m['domain_support'] else 'UNSUPPORTED_BUCKET' if x['feature_kind'] not in m['buckets'] else m['buckets'][x['feature_kind']]['status']
    row=dict(bucket=x['feature_kind'],status=status,n=m['buckets'].get(x['feature_kind'],{}).get('n',0),p_hat=None,lower=None,upper=None,point_net=None,lower_net=None,upper_net=None)
    if status=='SUPPORTED':
        b=m['buckets'][x['feature_kind']]
        for key in ('p_hat','lower','upper'):row[key]=b[key]
        row['point_net']=round(x['benefit_units']*b['p_hat']-x['cost']-x['risk'],12)
        row['lower_net']=round(x['benefit_units']*b['lower']-x['cost']-x['risk'],12)
        row['upper_net']=round(x['benefit_units']*b['upper']-x['cost']-x['risk'],12)
    return row


def adjudicate(case,records,s,m,policy):
    v=case['view'];ev=expected_evidence(v,records,case,s);barrier,allowed,filtered=eligible(v,s,ev)
    nets={x['candidate_id']:x['benefit_units']*case['outcomes'][x['candidate_id']]['useful_effect']-x['cost']-x['risk'] for x in allowed}
    opportunities=sorted(k for k,n in nets.items() if n>0)
    oracle=dict(verdict='MUST_STOP' if barrier else 'INCONCLUSIVE_ALLOWED' if ev['conflict'] or not ev['accepted'] else 'SHOULD_SELECT' if opportunities else 'MUST_STOP',
        safety_barrier=barrier,eligible=sorted(nets),opportunities=opportunities,net_units=nets,target='benefit_units*useful_effect-cost-risk',trust='NORMATIVE_SYNTHETIC_NOT_AUTHORITY')
    d=dict(policy=policy,action='STOP',candidate_id=None,reason=None,cost=0,evidence=ev,filtered=filtered,ranking=[],unsupported=[])
    if barrier:d['reason']=barrier
    elif ev['conflict'] or not ev['accepted']:d.update(action='INCONCLUSIVE',reason='CONFLICT' if ev['conflict'] else 'NO_TRUSTED_SOURCE')
    elif not allowed:d['reason']='NO_ELIGIBLE'
    elif policy in c.POLICIES[:2]:
        for x in allowed:
            f=expected_forecast(x,m,s,ev)
            if f['status']=='SUPPORTED':d['ranking'].append(dict(candidate_id=x['candidate_id'],**f))
            else:d['unsupported'].append(dict(candidate_id=x['candidate_id'],status=f['status']))
        d['unsupported'].sort(key=lambda z:z['candidate_id']);score='lower_net' if policy==c.POLICIES[0] else 'point_net'
        d['ranking'].sort(key=lambda z:(-z[score],z['candidate_id']))
        if d['ranking'] and d['ranking'][0][score]>0:d.update(action='SELECT',reason='POSITIVE_LOWER_NET' if score=='lower_net' else 'POSITIVE_POINT_NET',candidate_id=d['ranking'][0]['candidate_id'])
        elif d['unsupported']:d.update(action='INCONCLUSIVE',reason='UNSUPPORTED_FORECAST')
        elif policy==c.POLICIES[0] and max(z['upper_net'] for z in d['ranking'])>0:d.update(action='INCONCLUSIVE',reason='INTERVAL_CROSSES_ZERO')
        else:d['reason']='NONPOSITIVE_UPPER_NET' if policy==c.POLICIES[0] else 'NONPOSITIVE_POINT_NET'
    else:
        for x in allowed:
            if policy=='PGE-v3-utility' and (x['feature_status']=='UNKNOWN' or x['visible_at']>s['elapsed'] or x['valid_until']<s['elapsed']):d['unsupported'].append(dict(candidate_id=x['candidate_id'],status='UNKNOWN_FEATURE'));continue
            fresh=x['candidate_id'] not in s['attempted'];novelty=sum(k not in ev['facts'] for k in x['effect_keys'])
            val=(2 if x['value_update_kind']=='UPDATE' else 1 if x['value_update_kind']=='REVALIDATE' else 0) if fresh else 0
            terms=dict(novelty=2*novelty,verification=4*x['verification_need'] if fresh else 0,freshness=3*x['freshness_need'] if fresh else 0,value=3*val,cost=-x['cost'],risk=-2*x['risk'])
            d['ranking'].append(dict(candidate_id=x['candidate_id'],score=sum(terms.values()),terms=terms,order=x['order']))
        d['unsupported'].sort(key=lambda z:z['candidate_id']);d['ranking'].sort(key=(lambda z:(z['order'],z['candidate_id'])) if policy=='B0-fixed' else lambda z:(-z['score'],z['candidate_id']))
        if not d['ranking']:d.update(action='INCONCLUSIVE',reason='UTILITY_FEATURES_UNKNOWN')
        elif policy=='PGE-v3-utility' and d['ranking'][0]['score']<=0:d['reason']='NONPOSITIVE_VISIBLE_UTILITY'
        else:d.update(action='SELECT',reason='FIXED_ORDER' if policy=='B0-fixed' else 'MAX_VISIBLE_UTILITY',candidate_id=d['ranking'][0]['candidate_id'])
    if d['action']=='SELECT':d['cost']=next(x['cost'] for x in allowed if x['candidate_id']==d['candidate_id'])
    return d,oracle


def stress_inputs(parents):
    cases=[]
    for parent in parents:
        for transform in c.SHIFTS:
            case=copy.deepcopy(parent);v=case['view'];original_domain=v['domain'];cid=v['case_id']+'-s-'+transform.lower().replace('_','-')
            v.update(case_id=cid,split='stress',snapshot_id=cid+'-snapshot');case['parent_raw_sha256']=c.digest(parent);case['transform']=transform
            domain='lab-absent' if transform=='MISSING_DOMAIN' else original_domain;v['domain']=domain
            v['initial_unknown']=[domain if d==original_domain else d for d in v['initial_unknown']];outs={}
            for i,x in enumerate(v['candidates']):
                o=case['outcomes'][x['candidate_id']];cid2=domain+'-'+cid+'-c'+str(i);x.update(candidate_id=cid2,domain=domain,snapshot_id=v['snapshot_id'])
                o['outcome_id']='outcome-'+cid+'-c'+str(i)
                if transform=='COST_UP':x['cost']+=3
                if transform=='LABEL_FLIP':o['useful_effect']=1-o['useful_effect']
                if transform=='UNSEEN_BUCKET':x['feature_kind']='UNSEEN'
                outs[cid2]=o
            case['outcomes']=outs
            if transform=='EXPIRED_SOURCE':v['initial_elapsed']=max(1,v['initial_elapsed'])
            for i,r in enumerate(case['records']):
                r.update(evidence_id=cid+'-r'+str(i),case_id=cid,domain=domain,snapshot_id=v['snapshot_id'])
                if transform=='EXPIRED_SOURCE':r['valid_until']=0
                if transform=='DELAY_FEEDBACK':r.update(visible_at=3,seq=4)
            if transform=='REVERSE_CANDIDATES':v['candidates'].reverse()
            case['view']=c.normalize(v);c.seal(case);cases.append(case)
    return cases


def measurements(run):
    m=dict.fromkeys(c.COUNTERS,0);facts=set();seen=set()
    for row in run['rows']:
        d,o=row['decision'],row['oracle'];m['decisions']+=1;m['safety_rejections']+=len(d['filtered']);m['unsupported_forecast']+=len(d['unsupported'])
        m['unknown_bucket']+=sum(z['status']=='UNSUPPORTED_BUCKET' for z in d['unsupported'])
        if d['action']=='SELECT':
            cid=d['candidate_id'];x=next(x for x in run['snapshot']['candidates'] if x['candidate_id']==cid)
            safe=cid in o['eligible'] and o['safety_barrier'] is None;m['selects']+=1;m['eligible_selects']+=int(safe);m['unsafe_select']+=int(not safe)
            m['simulated_cost']+=d['cost'];m['risk_guard_violation']+=int(x['risk']>run['snapshot']['risk_cap'])
            net=o['net_units'][cid];m['realized_synthetic_net_utility']+=net
            if net<=0:m['over_exploration']+=1;m['wasted_simulated_cost']+=x['cost']
            m['repeated']+=int(cid in seen);seen.add(cid)
            actual=set(row['outcome']['facts'].items()) if row['outcome']['status']=='VERIFIED' else set();m['redundant']+=int(not(actual-facts));facts|=actual
        else:
            if o['verdict']=='SHOULD_SELECT':m['missed_opportunity']+=1;m['opportunity_cost']+=max(o['net_units'].values())
            if d['action']=='STOP':m['total_stop']+=1;m['correct_stop']+=int(o['verdict']=='MUST_STOP');m['stop_not_determinable']+=int(o['verdict'] in ('INCONCLUSIVE_ALLOWED','NOT_DETERMINABLE'))
            else:m['abstention_count']+=1;m['appropriate_abstention']+=int(o['verdict'] in ('INCONCLUSIVE_ALLOWED','NOT_DETERMINABLE'))
    m['verified_facts']=len(facts);return m


def prediction_quality(rows):
    result={}
    for split in sorted({r['split'] for r in rows}):
        part=[r for r in rows if r['split']==split];valid=[r for r in part if r['forecast']['status']=='SUPPORTED'];n=len(valid)
        error=round(sum((r['forecast']['p_hat']-r['observed_useful'])**2 for r in valid),12);bins=[]
        for i in range(4):
            b=[r for r in valid if min(3,int(r['forecast']['p_hat']*4))==i]
            bins.append(dict(bin=i,n=len(b),predicted_sum=round(sum(r['forecast']['p_hat'] for r in b),12),positive_sum=sum(r['observed_useful'] for r in b)))
        result[split]=dict(eligible_forecasts=len(part),supported=n,unsupported=len(part)-n,brier=dict(numerator=error,denominator=n,value=round(error/n,12) if n else None),
            ece=round(sum(abs(b['predicted_sum']-b['positive_sum']) for b in bins)/n,12) if n else None,bins=bins,
            mean_predicted=round(sum(r['forecast']['p_hat'] for r in valid)/n,12) if n else None,observed_rate=round(sum(r['observed_useful'] for r in valid)/n,12) if n else None,
            status='DESCRIPTIVE_ONLY' if n>=c.MIN_N else 'INSUFFICIENT_SUPPORT')
    return result


def comparison(runs,predictions):
    table=[dict(split=r['split'],case_id=r['case_id'],policy=r['policy'],**measurements(r)) for r in runs];summary={}
    for split in sorted({r['split'] for r in runs}):
        summary[split]={}
        for policy in c.POLICIES:
            part=[r for r in table if r['split']==split and r['policy']==policy];t={k:sum(r[k] for r in part) for k in c.COUNTERS}
            t.update(coverage=dict(numerator=t['decisions']-t['abstention_count'],denominator=t['decisions']),abstention_appropriateness=dict(numerator=t['appropriate_abstention'],denominator=t['abstention_count']),
                legal_selection_rate=dict(numerator=t['eligible_selects'],denominator=t['selects']),stop_correctness=dict(numerator=t['correct_stop'],denominator=t['total_stop']-t['stop_not_determinable']),
                cost_per_verified_fact=dict(numerator=t['simulated_cost'],denominator=t['verified_facts'],ratio=round(t['simulated_cost']/t['verified_facts'],12) if t['verified_facts'] else None,status='DEFINED' if t['verified_facts'] else 'ZERO_FACTS'))
            summary[split][policy]=t
    pairs=[]
    for split,cid in sorted({(r['split'],r['case_id']) for r in table}):
        p=next(r for r in table if r['split']==split and r['case_id']==cid and r['policy']==c.POLICIES[0])
        for baseline in c.POLICIES[1:]:
            b=next(r for r in table if r['split']==split and r['case_id']==cid and r['policy']==baseline)
            net=p['realized_synthetic_net_utility']-b['realized_synthetic_net_utility'];cost=p['simulated_cost']-b['simulated_cost']
            label='TIE' if net==cost==0 else 'FAVORABLE' if net>=0 and cost<=0 else 'UNFAVORABLE' if net<=0 and cost>=0 else 'TRADEOFF'
            pairs.append(dict(split=split,case_id=cid,baseline=baseline,label=label,net_delta=net,cost_delta=cost,missed_delta=p['missed_opportunity']-b['missed_opportunity']))
    return dict(table=table,summaries=summary,pairs=pairs,prediction_quality=prediction_quality(predictions),
        definitions=dict(net='benefit_units*useful_effect-cost-risk; frozen synthetic truth even for UNKNOWN delivery',over='SELECT normative net <=0',missed='SHOULD_SELECT but STOP/INCONCLUSIVE',opportunity_cost='best current eligible positive net at terminal refusal; local, not sequential regret',
        coverage='non-abstaining decision windows / all decision windows',brier='sum squared prediction error / supported initial eligible forecasts',ece='fixed four bins; unsupported excluded and separately counted',interval='descriptive Wilson sensitivity, synthetic non-iid; no coverage guarantee',value='normative units, not real business risk or information gain'))


def verify(value):
    c.keys(value,'schema owner level scope source_sha256 input_sha256 model model_raw_sha256 exposure runs predictions comparison limitations result_sha256','TRACE_SCHEMA')
    c.require(value['schema']==c.ABI and value['owner']==c.OWNER and value['level']==c.LEVEL,'TRACE_ID')
    c.require(value['source_sha256']==c.source_identity(),'SOURCE_IDENTITY');dev,challenge=c.catalogs()
    c.require(c.equal(value['model'],expected_model(dev['fit'],value['source_sha256'])),'FIT_MODEL_DERIVATION')
    c.require(value['model_raw_sha256']==c.digest(value['model']),'MODEL_RAW_ANCHOR')
    c.require(c.equal(value['input_sha256'],{p:c.sha((c.ROOT/p).read_bytes()) for p in c.INPUTS}),'INPUT_RAW_ANCHOR')
    c.require(value['exposure']=='AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND' and c.equal(value['limitations'],c.LIMITATIONS),'CLAIM_BOUNDARY')
    c.require(value['scope'] in ('MAIN','STRESS'),'ARTIFACT_SCOPE')
    c.require(value['result_sha256']==c.digest({k:v for k,v in value.items() if k!='result_sha256'}),'RESULT_HASH')
    cases=dev['development_validation']+challenge['challenge'] if value['scope']=='MAIN' else stress_inputs(challenge['challenge']);m=value['model']
    expected=[(case,p) for case in cases for p in c.POLICIES];c.require(type(value['runs']) is list and len(value['runs'])==len(expected),'RUN_COUNT')
    for run,(case,policy) in zip(value['runs'],expected):
        c.keys(run,'case_id split policy snapshot parent_raw_sha256 transform rows','RUN_SCHEMA');v=case['view']
        c.require(run['case_id']==v['case_id'] and run['split']==v['split'] and run['policy']==policy,'RUN_SCOPE')
        c.require(c.equal(run['snapshot'],v),'FROZEN_SNAPSHOT')
        c.require(run['parent_raw_sha256']==case['parent_raw_sha256'] and run['transform']==case['transform'],'STRESS_PARENT')
        state=c.initial(v);previous='0'*64;terminal=False;c.require(type(run['rows']) is list and 1<=len(run['rows'])<=v['max_steps']+1,'ROW_COUNT')
        for i,row in enumerate(run['rows']):
            c.require(not terminal,'AFTER_ABSTENTION_OR_TERMINAL');c.keys(row,'seq state snapshot_sha256 records roster roster_sha256 decision oracle outcome previous_sha256 sha256','ROW_SCHEMA')
            c.require(type(row['seq']) is int and row['seq']==i+1,'ROW_SEQ');c.require(c.equal(row['state'],state),'STATE_CHAIN');c.state_valid(v,row['state'])
            c.require(row['snapshot_sha256']==c.snapshot_sha(v),'SNAPSHOT_ANCHOR')
            c.require(c.equal(row['roster'],case['roster']) and row['roster_sha256']==case['roster_sha256'],'FROZEN_ROSTER')
            records=sorted([r for r in case['records'] if r['visible_at']<=state['step']],key=lambda z:z['evidence_id']);c.require(c.equal(row['records'],records),'FROZEN_VISIBLE_RECORDS')
            c.require(row['previous_sha256']==previous and row['sha256']==c.digest({k:v for k,v in row.items() if k!='sha256'}),'ROW_HASH_ORDER')
            d,o=adjudicate(case,records,state,m,policy);c.require(c.equal(row['decision'],d),'FORECAST_DECISION_SEMANTICS');c.require(c.equal(row['oracle'],o),'ORACLE_SEMANTICS')
            if d['action']=='SELECT':
                outcome=case['outcomes'][d['candidate_id']];c.require(c.equal(row['outcome'],outcome),'FROZEN_OUTCOME')
                unknown=set(state['unknown_domains'])|({v['domain']} if outcome['status']=='UNKNOWN' else set())
                state=dict(step=state['step']+1,remaining=state['remaining']-d['cost'],elapsed=state['elapsed']+1,attempted=state['attempted']+[d['candidate_id']],unknown_domains=sorted(unknown))
            else:c.require(row['outcome'] is None,'TERMINAL_OUTCOME');terminal=True
            previous=row['sha256']
        c.require(terminal,'MISSING_TERMINAL')
    predictions=[]
    for case in cases:
        v=case['view'];s=c.initial(v);records=[r for r in case['records'] if r['visible_at']<=s['step']];ev=expected_evidence(v,records,case,s);_,allowed,_=eligible(v,s,ev)
        for x in sorted(allowed,key=lambda z:z['candidate_id']):predictions.append(dict(split=v['split'],case_id=v['case_id'],candidate_id=x['candidate_id'],forecast=expected_forecast(x,m,s,ev),observed_useful=case['outcomes'][x['candidate_id']]['useful_effect']))
    c.require(c.equal(value['predictions'],predictions),'PREDICTION_TRUTH_REPLAY');c.require(c.equal(value['comparison'],comparison(value['runs'],predictions)),'METRIC_DENOMINATOR_REPLAY')
    return dict(status='PASS',reason='INDEPENDENT_FIT_FORECAST_EVALUATION',scope=value['scope'],runs=len(expected),decisions=sum(len(r['rows']) for r in value['runs']),level=c.LEVEL)


def verify_file(path,anchor):
    if not anchor:return 2,dict(status='NOT_RUN',reason='ANCHOR_REQUIRED')
    try:
        path=c.allowed_file(path)
        if not path.is_file():return 2,dict(status='NOT_RUN',reason='FILE_REQUIRED')
        raw=path.read_bytes();c.require(c.sha(raw)==anchor,'RAW_ANCHOR');return 0,verify(c.strict(raw))
    except (c.Invalid,OSError,KeyError,TypeError,IndexError,AttributeError) as exc:return 3,dict(status='FAIL',reason=str(exc) if isinstance(exc,c.Invalid) else 'MALFORMED_INPUT')
