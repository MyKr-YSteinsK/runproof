"""Synthetic scheduler and descriptive evaluation; no tool execution."""
from . import pge_r77_contracts as c
from .pge_r77_fixtures import load, diagnostic76
from .pge_r77_policy import decide
from .pge_r77_oracle import evaluate


def replay_case(case, policy, reverse=False):
    v=case['view'];state=c.initial(v);rows=[];previous='0'*64
    for _ in range(v['max_steps']+1):
        records=sorted([r for r in case['records'] if r['visible_at']<=state['step']],key=lambda r:r['evidence_id'])
        supplied=dict(v,candidates=list(reversed(v['candidates']))) if reverse else v
        d=decide(supplied,list(reversed(records)) if reverse else records,state,case['roster'],case['roster_sha256'],policy)
        oracle=evaluate(case,records,state)
        outcome=case['outcomes'][d['candidate_id']] if d['action']=='SELECT' else None
        row=dict(seq=len(rows)+1,state=state,snapshot_sha256=c.snapshot_sha(v),records=records,roster=case['roster'],
                 roster_sha256=case['roster_sha256'],decision=d,oracle=oracle,outcome=outcome,previous_sha256=previous)
        row['sha256']=c.digest(row);previous=row['sha256'];rows.append(row)
        if outcome is None:
            break
        unknown=set(state['unknown_domains'])|({v['domain']} if outcome['status']=='UNKNOWN' else set())
        state=dict(step=state['step']+1,remaining=state['remaining']-d['cost'],elapsed=state['elapsed']+1,
                   attempted=state['attempted']+[d['candidate_id']],unknown_domains=sorted(unknown))
    return dict(case_id=v['case_id'],split=v['split'],policy=policy,snapshot=v,evaluation=case['evaluation'],rows=rows)


def measure(run):
    names='decisions selects eligible_selects total_stop correct_stop stop_not_determinable missed_opportunity unsafe_select appropriate_inconclusive inconclusive over_exploration wasted_simulated_cost verified_facts simulated_cost risk_guard_violation repeated redundant safety_rejections'.split()
    m=dict.fromkeys(names,0);facts=set();attempts=[]
    for row in run['rows']:
        m['decisions']+=1
        d,o=row['decision'],row['oracle'];m['safety_rejections']+=len(d['filtered'])
        if d['action']=='SELECT':
            cid=d['candidate_id'];m['selects']+=1;m['simulated_cost']+=d['cost']
            safe=cid in o['eligible'] and o['safety_barrier'] is None
            m['eligible_selects']+=int(safe);m['unsafe_select']+=int(not safe)
            candidate=next(x for x in run['snapshot']['candidates'] if x['candidate_id']==cid)
            m['risk_guard_violation']+=int(candidate['risk']>run['snapshot']['risk_cap'])
            over=cid in run['evaluation']['no_benefit_ids'] or (cid in run['evaluation']['worthwhile_ids'] and cid in attempts)
            m['over_exploration']+=int(over);m['wasted_simulated_cost']+=d['cost'] if over else 0
            m['repeated']+=int(cid in attempts);attempts.append(cid)
            actual=set(row['outcome']['facts'].items()) if row['outcome']['status']=='VERIFIED' else set()
            m['redundant']+=int(not actual-facts);facts|=actual
        else:
            m['missed_opportunity']+=int(o['verdict']=='SHOULD_SELECT')
            if d['action']=='STOP':
                m['total_stop']+=1;m['correct_stop']+=int(o['verdict']=='MUST_STOP')
                m['stop_not_determinable']+=int(o['verdict'] in ('NOT_DETERMINABLE','INCONCLUSIVE_ALLOWED'))
            else:
                m['inconclusive']+=1;m['appropriate_inconclusive']+=int(o['verdict'] in ('NOT_DETERMINABLE','INCONCLUSIVE_ALLOWED'))
    m['verified_facts']=len(facts)
    return m


def rates(totals):
    return dict(stop_correctness=dict(numerator=totals['correct_stop'],denominator=totals['total_stop']-totals['stop_not_determinable']),
                legal_selection_rate=dict(numerator=totals['eligible_selects'],denominator=totals['selects']),
                inconclusive_appropriateness=dict(numerator=totals['appropriate_inconclusive'],denominator=totals['inconclusive']),
                cost_per_verified_fact=dict(numerator=totals['simulated_cost'],denominator=totals['verified_facts'],
                    ratio=totals['simulated_cost']/totals['verified_facts'] if totals['verified_facts'] else None,
                    status='DEFINED' if totals['verified_facts'] else 'ZERO_FACTS'))


def comparison(runs):
    table=[dict(split=r['split'],case_id=r['case_id'],policy=r['policy'],**measure(r)) for r in runs]
    summaries={}
    for split in sorted({r['split'] for r in runs}):
        summaries[split]={}
        for policy in c.POLICIES:
            part=[r for r in table if r['split']==split and r['policy']==policy]
            totals={k:sum(r[k] for r in part) for k in part[0] if k not in ('split','case_id','policy')}
            summaries[split][policy]=dict(**totals,**rates(totals))
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


def cases(splits):
    result=[]
    for split in splits:
        result.extend(diagnostic76() if split=='diagnostic76' else load(split)['cases'])
    return result


def run(splits=('development','challenge','diagnostic76'),reverse=False):
    runs=[replay_case(case,policy,reverse) for case in cases(splits) for policy in c.POLICIES]
    value=dict(schema=c.ABI,owner=c.OWNER,level=c.LEVEL,source_sha256=c.source_identity(),splits=list(splits),
        input_sha256={p:c.sha((c.ROOT/p).read_bytes()) for p in c.INPUTS},exposure='CHALLENGE_AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND',
        runs=runs,comparison=comparison(runs),limitations=['SYNTHETIC_ONLY','NORMATIVE_LABEL_NOT_AUTHORITY','NO_REAL_AGENT',
            'NO_L2_OR_CAUSAL_PROOF','NO_CROSS_PLATFORM_PROOF','RPF74_PAUSED','DIAGNOSTIC76_EXPOSED_SEPARATE'])
    value['result_sha256']=c.digest(value)
    return value
