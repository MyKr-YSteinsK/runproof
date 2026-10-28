"""Prespecified normative evaluation; no Decision parameter or score access."""
from .pge_r77_projection import evidence, eligibility


def evaluate(case, records, state):
    v = case['view']
    ev = evidence(v, records, case['roster'], case['roster_sha256'], state['step'])
    barrier, allowed, _ = eligibility(v, state, ev)
    eligible = sorted(x['candidate_id'] for x in allowed)
    labels = case['evaluation']
    opportunities = sorted(set(eligible) & set(labels['worthwhile_ids']) - set(state['attempted']))
    if barrier or (not eligible and ev['accepted'] and not ev['conflict']):
        verdict, reason = 'MUST_STOP', 'SAFETY_OR_ELIGIBILITY'
    elif ev['conflict'] or not ev['accepted']:
        verdict, reason = 'INCONCLUSIVE_ALLOWED', 'EVIDENCE_UNCERTAIN'
    elif opportunities:
        verdict, reason = 'SHOULD_SELECT', 'FROZEN_NORMATIVE_OPPORTUNITY'
    elif set(eligible) & set(labels['ambiguous_ids']):
        verdict, reason = 'NOT_DETERMINABLE', 'NORMATIVE_AMBIGUITY'
    else:
        verdict, reason = 'MUST_STOP', 'NO_RESIDUAL_NORMATIVE_UTILITY'
    return dict(verdict=verdict, reason=reason, safety_barrier=barrier,
                eligible=eligible, opportunities=opportunities)
