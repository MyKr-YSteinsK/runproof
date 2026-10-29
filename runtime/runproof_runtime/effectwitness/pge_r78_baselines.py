"""Frozen RPF77 v3 score semantics and B0 on the same eligible projection."""


def ranking(allowed,facts,state,policy):
    rows=[];unknown=[]
    for x in allowed:
        if policy=='PGE-v3-utility' and (x['feature_status']=='UNKNOWN' or x['visible_at']>state['elapsed'] or x['valid_until']<state['elapsed']):unknown.append(x['candidate_id']);continue
        fresh=x['candidate_id'] not in state['attempted'];novelty=len(set(x['effect_keys'])-set(facts))
        value={'NONE':0,'REVALIDATE':1,'UPDATE':2}[x['value_update_kind']] if fresh else 0
        terms=dict(novelty=2*novelty,verification=4*x['verification_need'] if fresh else 0,
                   freshness=3*x['freshness_need'] if fresh else 0,value=3*value,cost=-x['cost'],risk=-2*x['risk'])
        rows.append(dict(candidate_id=x['candidate_id'],score=sum(terms.values()),terms=terms,order=x['order']))
    rows.sort(key=(lambda x:(x['order'],x['candidate_id'])) if policy=='B0-fixed' else lambda x:(-x['score'],x['candidate_id']))
    return rows,sorted(unknown)
