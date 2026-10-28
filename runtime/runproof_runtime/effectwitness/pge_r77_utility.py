"""Observable utility is an estimate, not an outcome or normative label."""


def features(candidate, facts, attempted):
    fresh = candidate['candidate_id'] not in attempted
    value = {'NONE': 0, 'REVALIDATE': 1, 'UPDATE': 2}[candidate['value_update_kind']] if fresh else 0
    novelty = len(set(candidate['effect_keys']) - set(facts))
    verification = candidate['verification_need'] if fresh else 0
    freshness = candidate['freshness_need'] if fresh else 0
    terms = dict(novelty=2*novelty, verification=4*verification, freshness=3*freshness,
                 value=3*value, cost=-candidate['cost'], risk=-2*candidate['risk'])
    return dict(expected_key_novelty=novelty, observable_verification_value=verification,
                freshness_value=freshness, value_update_value=value, estimated_cost=candidate['cost'],
                risk=candidate['risk'], confidence_status=candidate['feature_status'],
                terms=terms, score=sum(terms.values()))
