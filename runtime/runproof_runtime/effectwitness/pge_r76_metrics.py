"""Observable counts against normative labels, not decisions certifying themselves."""
from . import pge_r76_contracts as c


def row_metrics(rows):
    m = dict(decisions=len(rows), selects=0, legal_selects=0, total_stop=0, correct_stop=0,
             stop_not_determinable=0, missed_opportunity=0, unsafe_select=0, appropriate_inconclusive=0,
             inconclusive=0, simulated_cost=0, verified_facts=0, repeated=0, redundant=0, rejected=0)
    facts, attempted = set(), []
    for row in rows:
        d, oracle = row['decision'], row['oracle']
        m['rejected'] += len(d['rejected'])
        if d['action'] == 'SELECT':
            m['selects'] += 1
            safe = d['candidate_id'] in oracle['eligible'] and oracle['verdict'] != 'MUST_STOP'
            m['legal_selects'] += int(safe)
            m['unsafe_select'] += int(not safe)
            m['simulated_cost'] += d['cost']
            m['repeated'] += int(d['candidate_id'] in attempted)
            attempted.append(d['candidate_id'])
            outcome = row['outcome']
            new = set(outcome['facts'].items()) - facts if outcome['status'] == 'VERIFIED' else set()
            m['redundant'] += int(not new)
            if outcome['status'] == 'VERIFIED':
                facts.update(outcome['facts'].items())
        elif d['action'] == 'STOP':
            m['total_stop'] += 1
            m['correct_stop'] += int(oracle['verdict'] == 'MUST_STOP')
            m['stop_not_determinable'] += int(oracle['verdict'] == 'INCONCLUSIVE_ALLOWED')
            m['missed_opportunity'] += int(oracle['verdict'] == 'SHOULD_SELECT')
        else:
            m['inconclusive'] += 1
            m['appropriate_inconclusive'] += int(oracle['verdict'] == 'INCONCLUSIVE_ALLOWED')
            m['missed_opportunity'] += int(oracle['verdict'] == 'SHOULD_SELECT')
    m['verified_facts'] = len(facts)
    return m


def comparison(runs):
    table = [dict(split=r['split'], case_id=r['case_id'], policy=r['policy'], **row_metrics(r['rows'])) for r in runs]
    summaries = {}
    for split in sorted({r['split'] for r in runs}):
        summaries[split] = {}
        for policy in c.POLICIES:
            subset = [r for r in table if r['split'] == split and r['policy'] == policy]
            totals = {key: sum(r[key] for r in subset) for key in subset[0] if key not in ('split', 'case_id', 'policy')}
            totals['stop_correctness'] = dict(numerator=totals['correct_stop'],
                denominator=totals['total_stop'] - totals['stop_not_determinable'])
            totals['inconclusive_appropriateness'] = dict(numerator=totals['appropriate_inconclusive'], denominator=totals['inconclusive'])
            totals['legal_selection_rate'] = dict(numerator=totals['legal_selects'], denominator=totals['selects'])
            summaries[split][policy] = totals
    pairs = []
    for split, cid in sorted({(r['split'], r['case_id']) for r in table}):
        p, b = [next(r for r in table if r['case_id'] == cid and r['split'] == split and r['policy'] == policy)
                for policy in ('PGE-v2', 'B0-fixed-v2')]
        fd, cd = p['verified_facts'] - b['verified_facts'], p['simulated_cost'] - b['simulated_cost']
        label = 'TIE' if fd == cd == 0 else 'FAVORABLE' if fd >= 0 and cd <= 0 else 'UNFAVORABLE' if fd <= 0 and cd >= 0 else 'TRADEOFF'
        pairs.append(dict(split=split, case_id=cid, label=label, facts_delta=fd, cost_delta=cd,
                          missed_opportunity_delta=p['missed_opportunity'] - b['missed_opportunity']))
    return dict(table=table, summaries=summaries, pairs=pairs, definitions=c.DEFINITIONS)
