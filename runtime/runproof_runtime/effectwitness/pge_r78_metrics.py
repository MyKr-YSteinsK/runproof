"""Prediction error and decision value have separate denominators."""
from . import pge_r78_contracts as c


def measure(run):
    m=dict.fromkeys(c.COUNTERS,0);facts=set();attempted=set()
    for row in run['rows']:
        d,o=row['decision'],row['oracle'];m['decisions']+=1;m['safety_rejections']+=len(d['filtered'])
        m['unsupported_forecast']+=len(d['unsupported'])
        m['unknown_bucket']+=sum(z['status']=='UNSUPPORTED_BUCKET' for z in d['unsupported'])
        if d['action']=='SELECT':
            cid=d['candidate_id'];m['selects']+=1;m['simulated_cost']+=d['cost']
            safe=cid in o['eligible'] and o['safety_barrier'] is None;m['eligible_selects']+=int(safe);m['unsafe_select']+=int(not safe)
            x=next(x for x in run['snapshot']['candidates'] if x['candidate_id']==cid)
            m['risk_guard_violation']+=int(x['risk']>run['snapshot']['risk_cap'])
            net=o['net_units'][cid];m['realized_synthetic_net_utility']+=net
            over=net<=0;m['over_exploration']+=int(over);m['wasted_simulated_cost']+=x['cost'] if over else 0
            m['repeated']+=int(cid in attempted);attempted.add(cid)
            actual=set(row['outcome']['facts'].items()) if row['outcome']['status']=='VERIFIED' else set()
            m['redundant']+=int(not(actual-facts));facts|=actual
        else:
            if o['verdict']=='SHOULD_SELECT':m['missed_opportunity']+=1;m['opportunity_cost']+=max(o['net_units'].values())
            if d['action']=='STOP':
                m['total_stop']+=1;m['correct_stop']+=int(o['verdict']=='MUST_STOP')
                m['stop_not_determinable']+=int(o['verdict'] in ('INCONCLUSIVE_ALLOWED','NOT_DETERMINABLE'))
            else:
                m['abstention_count']+=1;m['appropriate_abstention']+=int(o['verdict'] in ('INCONCLUSIVE_ALLOWED','NOT_DETERMINABLE'))
    m['verified_facts']=len(facts)
    return m


def ratios(t):
    return dict(coverage=dict(numerator=t['decisions']-t['abstention_count'],denominator=t['decisions']),
        abstention_appropriateness=dict(numerator=t['appropriate_abstention'],denominator=t['abstention_count']),
        legal_selection_rate=dict(numerator=t['eligible_selects'],denominator=t['selects']),
        stop_correctness=dict(numerator=t['correct_stop'],denominator=t['total_stop']-t['stop_not_determinable']),
        cost_per_verified_fact=dict(numerator=t['simulated_cost'],denominator=t['verified_facts'],ratio=round(t['simulated_cost']/t['verified_facts'],12) if t['verified_facts'] else None,status='DEFINED' if t['verified_facts'] else 'ZERO_FACTS'))


def prediction_quality(rows):
    groups={}
    for split in sorted({r['split'] for r in rows}):
        part=[r for r in rows if r['split']==split];supported=[r for r in part if r['forecast']['status']=='SUPPORTED'];n=len(supported)
        brier=round(sum((r['forecast']['p_hat']-r['observed_useful'])**2 for r in supported),12)
        bins=[]
        for i in range(4):
            subset=[r for r in supported if min(3,int(r['forecast']['p_hat']*4))==i];count=len(subset)
            bins.append(dict(bin=i,n=count,predicted_sum=round(sum(r['forecast']['p_hat'] for r in subset),12),positive_sum=sum(r['observed_useful'] for r in subset)))
        ece=round(sum(abs(z['predicted_sum']-z['positive_sum']) for z in bins)/n,12) if n else None
        groups[split]=dict(eligible_forecasts=len(part),supported=n,unsupported=len(part)-n,brier=dict(numerator=brier,denominator=n,value=round(brier/n,12) if n else None),
            ece=ece,bins=bins,mean_predicted=round(sum(r['forecast']['p_hat'] for r in supported)/n,12) if n else None,
            observed_rate=round(sum(r['observed_useful'] for r in supported)/n,12) if n else None,
            status='DESCRIPTIVE_ONLY' if n>=c.MIN_N else 'INSUFFICIENT_SUPPORT')
    return groups


def comparison(runs,predictions):
    table=[dict(split=r['split'],case_id=r['case_id'],policy=r['policy'],**measure(r)) for r in runs];summary={}
    for split in sorted({r['split'] for r in runs}):
        summary[split]={}
        for policy in c.POLICIES:
            part=[r for r in table if r['split']==split and r['policy']==policy]
            totals={k:sum(r[k] for r in part) for k in c.COUNTERS};summary[split][policy]=dict(**totals,**ratios(totals))
    pairs=[]
    for split,cid in sorted({(r['split'],r['case_id']) for r in table}):
        p=next(r for r in table if r['split']==split and r['case_id']==cid and r['policy']==c.POLICIES[0])
        for baseline in c.POLICIES[1:]:
            b=next(r for r in table if r['split']==split and r['case_id']==cid and r['policy']==baseline)
            net=p['realized_synthetic_net_utility']-b['realized_synthetic_net_utility'];cost=p['simulated_cost']-b['simulated_cost']
            label='TIE' if net==cost==0 else 'FAVORABLE' if net>=0 and cost<=0 else 'UNFAVORABLE' if net<=0 and cost>=0 else 'TRADEOFF'
            pairs.append(dict(split=split,case_id=cid,baseline=baseline,label=label,net_delta=net,cost_delta=cost,
                missed_delta=p['missed_opportunity']-b['missed_opportunity']))
    return dict(table=table,summaries=summary,pairs=pairs,prediction_quality=prediction_quality(predictions),
        definitions=dict(net='benefit_units*useful_effect-cost-risk; frozen synthetic truth even for UNKNOWN delivery',
          over='SELECT normative net <=0',missed='SHOULD_SELECT but STOP/INCONCLUSIVE',opportunity_cost='best current eligible positive net at terminal refusal; local, not sequential regret',
          coverage='non-abstaining decision windows / all decision windows',brier='sum squared prediction error / supported initial eligible forecasts',ece='fixed four bins; unsupported excluded and separately counted',
          interval='descriptive Wilson sensitivity, synthetic non-iid; no coverage guarantee',value='normative units, not real business risk or information gain'))
