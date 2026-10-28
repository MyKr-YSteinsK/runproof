"""RPF76 mathematical scoring/stopping reference on the same new projection."""


def rank(allowed, facts, policy):
    rows = []
    for x in allowed:
        gain = len(set(x['effect_keys']) - set(facts))
        terms = dict(gain=10*gain, priority=2*x['priority'], cost=-x['cost'], risk=-x['risk'])
        rows.append(dict(candidate_id=x['candidate_id'], gain=gain, terms=terms,
                         score=sum(terms.values()), order=x['order']))
    rows.sort(key=(lambda r: (r['order'], r['candidate_id'])) if policy == 'B0-fixed' else
              lambda r: (-r['score'], r['candidate_id']))
    return rows
