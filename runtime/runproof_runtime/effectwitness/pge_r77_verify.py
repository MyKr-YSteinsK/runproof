"""Independent offline admission/utility/Oracle/metric recomputation."""
from . import pge_r77_contracts as c
from .pge_r77_fixtures import load, diagnostic76


def adjudicate(case,records,s,policy):
    v=case['view'];facts={};accepted=[];refused=[];conflict=False
    for r in sorted(records,key=lambda x:x['evidence_id']):
        c.require(case['roster']['entries'].get(r['evidence_id'])==c.digest(r),'ROSTER_MEMBER')
        why=('FUTURE' if r['visible_at']>s['step'] or r['seq']>s['step']+1 else 'LATE' if r['seq']<r['visible_at']+1
            else 'CROSS_CASE' if r['case_id']!=v['case_id'] else 'CROSS_DOMAIN' if r['domain']!=v['domain']
            else 'SNAPSHOT' if r['snapshot_id']!=v['snapshot_id'] else 'CONTRACT' if r['contract_sha256']!=c.snapshot_sha(v)
            else 'SOURCE' if r['source_kind']!='FROZEN_SYNTHETIC' else 'STATUS' if r['status']!='VERIFIED' else None)
        if why:
            refused.append(dict(evidence_id=r['evidence_id'],reason=why))
        else:
            for key,value in r['facts'].items():
                conflict=conflict or (key in facts and facts[key]!=value)
                facts[key]=value
            accepted.append(dict(evidence_id=r['evidence_id'],raw_sha256=c.digest(r)))
    ev=dict(facts=facts,accepted=accepted,refused=refused,conflict=conflict)
    barrier='UNKNOWN_STOP' if v['domain'] in s['unknown_domains'] else 'TIME_STOP' if s['elapsed']>=v['deadline'] else 'STEP_STOP' if s['step']>=v['max_steps'] else None
    allowed=[];filtered=[]
    if not barrier and accepted and not conflict:
        for x in v['candidates']:
            why=('REPEAT' if not x['repeat'] and x['candidate_id'] in s['attempted'] else 'BUDGET' if x['cost']>s['remaining']
                else 'RISK' if x['risk']>v['risk_cap'] else 'PERMISSION' if x['permission'] not in v['permissions']
                else 'PRECONDITION' if not set(x['requires'])<=facts.keys() else None)
            if why:filtered.append(dict(candidate_id=x['candidate_id'],reason=why))
            else:allowed.append(x)
    filtered.sort(key=lambda x:x['candidate_id'])
    eligible=sorted(x['candidate_id'] for x in allowed)
    opportunities=sorted(cid for cid in eligible if cid in case['evaluation']['worthwhile_ids'] and cid not in s['attempted'])
    if barrier or (not eligible and accepted and not conflict):verdict,reason='MUST_STOP','SAFETY_OR_ELIGIBILITY'
    elif conflict or not accepted:verdict,reason='INCONCLUSIVE_ALLOWED','EVIDENCE_UNCERTAIN'
    elif opportunities:verdict,reason='SHOULD_SELECT','FROZEN_NORMATIVE_OPPORTUNITY'
    elif any(cid in case['evaluation']['ambiguous_ids'] for cid in eligible):verdict,reason='NOT_DETERMINABLE','NORMATIVE_AMBIGUITY'
    else:verdict,reason='MUST_STOP','NO_RESIDUAL_NORMATIVE_UTILITY'
    oracle=dict(verdict=verdict,reason=reason,safety_barrier=barrier,eligible=eligible,opportunities=opportunities)
    d=dict(policy=policy,action='STOP',candidate_id=None,reason=None,cost=0,evidence=ev,ranking=[],filtered=filtered,feature_unknown=[])
    if barrier:d['reason']=barrier
    elif conflict or not accepted:d.update(action='INCONCLUSIVE',reason='CONFLICT' if conflict else 'NO_TRUSTED_SOURCE')
    elif not allowed:d['reason']='NO_ELIGIBLE'
    elif policy==c.POLICIES[0]:
        for x in allowed:
            if x['feature_status']=='UNKNOWN':d['feature_unknown'].append(x['candidate_id']);continue
            fresh=x['candidate_id'] not in s['attempted'];novelty=sum(k not in facts for k in x['effect_keys'])
            verify=x['verification_need'] if fresh else 0;age=x['freshness_need'] if fresh else 0
            val=(2 if x['value_update_kind']=='UPDATE' else 1 if x['value_update_kind']=='REVALIDATE' else 0) if fresh else 0
            terms={'novelty':2*novelty,'verification':4*verify,'freshness':3*age,'value':3*val,'cost':-x['cost'],'risk':-2*x['risk']}
            d['ranking'].append(dict(candidate_id=x['candidate_id'],expected_key_novelty=novelty,observable_verification_value=verify,
                freshness_value=age,value_update_value=val,estimated_cost=x['cost'],risk=x['risk'],confidence_status=x['feature_status'],terms=terms,score=sum(terms.values())))
        d['feature_unknown'].sort();d['ranking'].sort(key=lambda x:(-x['score'],x['candidate_id']))
        if not d['ranking']:d.update(action='INCONCLUSIVE',reason='UTILITY_FEATURES_UNKNOWN')
        elif d['ranking'][0]['score']<=0:d['reason']='NONPOSITIVE_VISIBLE_UTILITY'
        else:d.update(action='SELECT',reason='MAX_VISIBLE_UTILITY',candidate_id=d['ranking'][0]['candidate_id'])
    else:
        for x in allowed:
            gain=sum(k not in facts for k in x['effect_keys'])
            terms={'gain':10*gain,'priority':2*x['priority'],'cost':-x['cost'],'risk':-x['risk']}
            d['ranking'].append(dict(candidate_id=x['candidate_id'],gain=gain,terms=terms,score=sum(terms.values()),order=x['order']))
        d['ranking'].sort(key=(lambda x:(x['order'],x['candidate_id'])) if policy==c.POLICIES[2] else lambda x:(-x['score'],x['candidate_id']))
        if policy!=c.POLICIES[2] and all(x['gain']==0 for x in d['ranking']):d['reason']='ESTIMATED_ZERO_GAIN'
        else:d.update(action='SELECT',reason='FIXED_ORDER' if policy==c.POLICIES[2] else 'MAX_SCORE',candidate_id=d['ranking'][0]['candidate_id'])
    if d['action']=='SELECT':d['cost']=next(x['cost'] for x in allowed if x['candidate_id']==d['candidate_id'])
    return d,oracle


def measurements(run):
    names='decisions selects eligible_selects total_stop correct_stop stop_not_determinable missed_opportunity unsafe_select appropriate_inconclusive inconclusive over_exploration wasted_simulated_cost verified_facts simulated_cost risk_guard_violation repeated redundant safety_rejections'.split()
    m=dict.fromkeys(names,0);seen=set();attempted=set()
    for row in run['rows']:
        d,o=row['decision'],row['oracle'];m['decisions']+=1;m['safety_rejections']+=len(d['filtered'])
        if d['action']=='SELECT':
            cid=d['candidate_id'];m['selects']+=1;m['simulated_cost']+=d['cost']
            safe=cid in o['eligible'] and o['safety_barrier'] is None;m['eligible_selects']+=int(safe);m['unsafe_select']+=int(not safe)
            x=next(x for x in run['snapshot']['candidates'] if x['candidate_id']==cid)
            m['risk_guard_violation']+=int(x['risk']>run['snapshot']['risk_cap'])
            waste=cid in run['evaluation']['no_benefit_ids'] or (cid in run['evaluation']['worthwhile_ids'] and cid in attempted)
            if waste:m['over_exploration']+=1;m['wasted_simulated_cost']+=d['cost']
            m['repeated']+=int(cid in attempted);attempted.add(cid)
            actual=set(row['outcome']['facts'].items()) if row['outcome']['status']=='VERIFIED' else set()
            m['redundant']+=int(not (actual-seen));seen|=actual
        elif d['action']=='STOP':
            m['total_stop']+=1
            if o['verdict']=='MUST_STOP':m['correct_stop']+=1
            elif o['verdict']=='SHOULD_SELECT':m['missed_opportunity']+=1
            else:m['stop_not_determinable']+=1
        else:
            m['inconclusive']+=1
            if o['verdict']=='SHOULD_SELECT':m['missed_opportunity']+=1
            if o['verdict'] in ('NOT_DETERMINABLE','INCONCLUSIVE_ALLOWED'):m['appropriate_inconclusive']+=1
    m['verified_facts']=len(seen)
    return m


def compare(runs):
    table=[dict(split=r['split'],case_id=r['case_id'],policy=r['policy'],**measurements(r)) for r in runs]
    summaries={}
    for split in sorted({r['split'] for r in runs}):
        summaries[split]={}
        for policy in c.POLICIES:
            part=[r for r in table if r['split']==split and r['policy']==policy]
            t={k:sum(r[k] for r in part) for k in part[0] if k not in ('split','case_id','policy')}
            t['stop_correctness']=dict(numerator=t['correct_stop'],denominator=t['total_stop']-t['stop_not_determinable'])
            t['legal_selection_rate']=dict(numerator=t['eligible_selects'],denominator=t['selects'])
            t['inconclusive_appropriateness']=dict(numerator=t['appropriate_inconclusive'],denominator=t['inconclusive'])
            t['cost_per_verified_fact']=dict(numerator=t['simulated_cost'],denominator=t['verified_facts'],
                ratio=t['simulated_cost']/t['verified_facts'] if t['verified_facts'] else None,status='DEFINED' if t['verified_facts'] else 'ZERO_FACTS')
            summaries[split][policy]=t
    pairs=[]
    for split,cid in sorted({(r['split'],r['case_id']) for r in table}):
        p=next(r for r in table if r['case_id']==cid and r['split']==split and r['policy']==c.POLICIES[0])
        for base in c.POLICIES[1:]:
            b=next(r for r in table if r['case_id']==cid and r['split']==split and r['policy']==base)
            fd,cd=p['verified_facts']-b['verified_facts'],p['simulated_cost']-b['simulated_cost']
            label='TIE' if fd==cd==0 else 'FAVORABLE' if fd>=0 and cd<=0 else 'UNFAVORABLE' if fd<=0 and cd>=0 else 'TRADEOFF'
            pairs.append(dict(split=split,case_id=cid,baseline=base,label=label,facts_delta=fd,cost_delta=cd,
                missed_delta=p['missed_opportunity']-b['missed_opportunity'],over_delta=p['over_exploration']-b['over_exploration']))
    return dict(table=table,summaries=summaries,pairs=pairs,definitions=c.DEFINITIONS)


def verify(value):
    c.keys(value,'schema owner level source_sha256 splits input_sha256 exposure runs comparison limitations result_sha256','TRACE_SCHEMA')
    c.require(value['schema']==c.ABI and value['owner']==c.OWNER and value['level']==c.LEVEL,'TRACE_ID')
    c.require(value['source_sha256']==c.source_identity(),'SOURCE_IDENTITY')
    c.require(value['splits'] in (['development'],['development','challenge','diagnostic76']),'SPLIT_SET')
    c.require(c.equal(value['input_sha256'],{p:c.sha((c.ROOT/p).read_bytes()) for p in c.INPUTS}),'INPUT_RAW_ANCHOR')
    c.require(value['exposure']=='CHALLENGE_AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND','EXPOSURE')
    c.require(c.equal(value['limitations'],['SYNTHETIC_ONLY','NORMATIVE_LABEL_NOT_AUTHORITY','NO_REAL_AGENT','NO_L2_OR_CAUSAL_PROOF',
                  'NO_CROSS_PLATFORM_PROOF','RPF74_PAUSED','DIAGNOSTIC76_EXPOSED_SEPARATE']),'CLAIM_BOUNDARY')
    c.require(value['result_sha256']==c.digest({k:v for k,v in value.items() if k!='result_sha256'}),'RESULT_HASH')
    cases=[]
    for split in value['splits']:cases.extend(diagnostic76() if split=='diagnostic76' else load(split)['cases'])
    expected=[(case,policy) for case in cases for policy in c.POLICIES]
    c.require(type(value['runs']) is list and len(value['runs'])==len(expected),'RUN_COUNT')
    for run,(case,policy) in zip(value['runs'],expected):
        c.keys(run,'case_id split policy snapshot evaluation rows','RUN_SCHEMA');v=case['view']
        c.require(run['case_id']==v['case_id'] and run['split']==v['split'] and run['policy']==policy,'RUN_SCOPE')
        c.require(c.equal(run['snapshot'],v),'FROZEN_SNAPSHOT')
        c.require(c.equal(run['evaluation'],case['evaluation']),'FROZEN_EVALUATION_LABELS')
        state=c.initial(v);previous='0'*64;terminal=False
        c.require(type(run['rows']) is list and 1<=len(run['rows'])<=v['max_steps']+1,'ROW_COUNT')
        for index,row in enumerate(run['rows']):
            c.require(not terminal,'AFTER_TERMINAL')
            c.keys(row,'seq state snapshot_sha256 records roster roster_sha256 decision oracle outcome previous_sha256 sha256','ROW_SCHEMA')
            c.require(type(row['seq']) is int and row['seq']==index+1,'ROW_SEQ')
            c.require(c.equal(row['state'],state),'STATE_CHAIN');c.state_valid(v,row['state'])
            c.require(row['snapshot_sha256']==c.snapshot_sha(v),'SNAPSHOT_ANCHOR')
            c.require(c.equal(row['roster'],case['roster']) and row['roster_sha256']==case['roster_sha256'],'FROZEN_ROSTER')
            records=sorted([r for r in case['records'] if r['visible_at']<=state['step']],key=lambda x:x['evidence_id'])
            c.require(c.equal(row['records'],records),'FROZEN_VISIBLE_RECORDS')
            c.require(row['previous_sha256']==previous and row['sha256']==c.digest({k:v for k,v in row.items() if k!='sha256'}),'ROW_HASH_ORDER')
            d,o=adjudicate(case,records,state,policy)
            c.require(c.equal(row['decision'],d),'POLICY_UTILITY_SEMANTICS')
            c.require(c.equal(row['oracle'],o),'ORACLE_SEMANTICS')
            if d['action']=='SELECT':
                outcome=case['outcomes'][d['candidate_id']];c.require(c.equal(row['outcome'],outcome),'FROZEN_OUTCOME')
                unknown=set(state['unknown_domains'])|({v['domain']} if outcome['status']=='UNKNOWN' else set())
                state=dict(step=state['step']+1,remaining=state['remaining']-d['cost'],elapsed=state['elapsed']+1,
                    attempted=state['attempted']+[d['candidate_id']],unknown_domains=sorted(unknown))
            else:c.require(row['outcome'] is None,'TERMINAL_OUTCOME');terminal=True
            previous=row['sha256']
        c.require(terminal,'MISSING_TERMINAL')
    c.require(c.equal(value['comparison'],compare(value['runs'])),'METRIC_DENOMINATOR_REPLAY')
    return dict(status='PASS',reason='INDEPENDENT_UTILITY_EVALUATION',runs=len(expected),decisions=sum(len(r['rows']) for r in value['runs']),level=c.LEVEL)


def verify_file(path,anchor):
    if not anchor:return 2,dict(status='NOT_RUN',reason='ANCHOR_REQUIRED')
    try:
        path=c.allowed_file(path)
        if not path.is_file():return 2,dict(status='NOT_RUN',reason='FILE_REQUIRED')
        raw=path.read_bytes();c.require(c.sha(raw)==anchor,'RAW_ANCHOR')
        return 0,verify(c.strict(raw))
    except (c.Invalid,OSError,KeyError,TypeError,IndexError,AttributeError) as exc:
        return 3,dict(status='FAIL',reason=str(exc) if isinstance(exc,c.Invalid) else 'MALFORMED_INPUT')
