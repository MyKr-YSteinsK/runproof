"""Four fair policies; one terminal abstention per decision window."""
from . import pge_r78_contracts as c
from .pge_r78_provenance import project,eligibility
from .pge_r78_forecast import estimate
from .pge_r78_baselines import ranking


def decide(v,records,s,roster,anchor,model,policy):
    c.validate(v);c.state_valid(v,s);c.require(policy in c.POLICIES,'POLICY_ID')
    ev=project(v,records,roster,anchor,s);barrier,allowed,filtered=eligibility(v,s,ev)
    d=dict(policy=policy,action='STOP',candidate_id=None,reason=None,cost=0,evidence=ev,filtered=filtered,ranking=[],unsupported=[])
    if barrier:d['reason']=barrier
    elif ev['conflict'] or not ev['accepted']:d.update(action='INCONCLUSIVE',reason='CONFLICT' if ev['conflict'] else 'NO_TRUSTED_SOURCE')
    elif not allowed:d['reason']='NO_ELIGIBLE'
    elif policy in c.POLICIES[:2]:
        for x in allowed:
            row=estimate(x,model,s,ev)
            if row['status']!='SUPPORTED':d['unsupported'].append(dict(candidate_id=x['candidate_id'],status=row['status']));continue
            d['ranking'].append(dict(candidate_id=x['candidate_id'],**row))
        d['unsupported'].sort(key=lambda z:z['candidate_id'])
        score='lower_net' if policy==c.POLICIES[0] else 'point_net'
        d['ranking'].sort(key=lambda z:(-z[score],z['candidate_id']))
        if d['ranking'] and d['ranking'][0][score]>0:
            d.update(action='SELECT',reason='POSITIVE_LOWER_NET' if score=='lower_net' else 'POSITIVE_POINT_NET',candidate_id=d['ranking'][0]['candidate_id'])
        elif d['unsupported']:d.update(action='INCONCLUSIVE',reason='UNSUPPORTED_FORECAST')
        elif policy==c.POLICIES[0] and any(z['upper_net']>0 for z in d['ranking']):d.update(action='INCONCLUSIVE',reason='INTERVAL_CROSSES_ZERO')
        else:d['reason']='NONPOSITIVE_UPPER_NET' if policy==c.POLICIES[0] else 'NONPOSITIVE_POINT_NET'
    else:
        d['ranking'],unknown=ranking(allowed,ev['facts'],s,policy)
        d['unsupported']=[dict(candidate_id=cid,status='UNKNOWN_FEATURE') for cid in unknown]
        if not d['ranking']:d.update(action='INCONCLUSIVE',reason='UTILITY_FEATURES_UNKNOWN')
        elif policy=='PGE-v3-utility' and d['ranking'][0]['score']<=0:d['reason']='NONPOSITIVE_VISIBLE_UTILITY'
        else:d.update(action='SELECT',reason='FIXED_ORDER' if policy=='B0-fixed' else 'MAX_VISIBLE_UTILITY',candidate_id=d['ranking'][0]['candidate_id'])
    if d['action']=='SELECT':d['cost']=next(x['cost'] for x in allowed if x['candidate_id']==d['candidate_id'])
    return d
