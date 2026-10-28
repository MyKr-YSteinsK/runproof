"""Offline scheduler owns frozen outcomes; policy receives only visible inputs."""
from . import pge_r75_contracts as c
from .pge_r75_policy import decide


def replay_case(case, policy, source, *, reverse=False):
    v = c.view(case)
    c.validate_view(v)
    state, rows, previous = c.initial(v), [], '0' * 64
    for _ in range(v['max_steps'] + 1):
        records = [r for r in case['feedback'] if r['visible_at'] <= state['step']]
        projected = dict(v, candidates=list(reversed(v['candidates']))) if reverse else v
        # Contract anchor always describes the frozen view, not container iteration order.
        decision = decide(v, list(reversed(records)) if reverse else records, state,
                          trusted_records={r['evidence_id']: c.digest(r) for r in records}, policy=policy)
        if reverse:
            # Test order invariance with canonically equivalent candidate input.
            projected['candidates'].sort(key=lambda r: (r['order'], r['candidate_id']))
            c.require(decide(projected, records, state, trusted_records={r['evidence_id']: c.digest(r) for r in records}, policy=policy)
                      == decision, 'INPUT_ORDER_DEPENDENCE')
        outcome = case['outcomes'][decision['candidate_id']] if decision['action'] == 'SELECT' else None
        row = dict(seq=len(rows) + 1, case_id=case['case_id'], policy=policy, step=state['step'],
                   contract_sha256=c.digest(v), visible_ids=sorted(r['evidence_id'] for r in records),
                   visible_sha256=c.digest(sorted(records, key=lambda r: r['evidence_id'])),
                   state=dict(state, attempted=list(state['attempted'])), decision=decision,
                   outcome=outcome, previous_sha256=previous)
        row['sha256'] = c.digest(row)
        rows.append(row)
        previous = row['sha256']
        if outcome is None:
            break
        state = dict(step=state['step'] + 1, remaining=state['remaining'] - decision['cost'],
                     attempted=state['attempted'] + [decision['candidate_id']],
                     unknown=outcome['status'] == 'UNKNOWN', elapsed=state['elapsed'] + 1)
    return dict(case_id=case['case_id'], policy=policy, source_sha256=source, rows=rows)


def comparison(runs):
    table = []
    for run in runs:
        facts, attempted, cost, redundant, selections, stops, inconclusive = set(), [], 0, 0, 0, 0, 0
        rejections = 0
        for row in run['rows']:
            decision = row['decision']
            rejections += len(decision['rejected'])
            if decision['action'] == 'SELECT':
                selections += 1
                cost += decision['cost']
                outcome = row['outcome']
                new = set(outcome['facts'].items()) - facts if outcome['status'] == 'VERIFIED' else set()
                redundant += int(not new)
                if outcome['status'] == 'VERIFIED':
                    facts.update(outcome['facts'].items())
                attempted.append(decision['candidate_id'])
            else:
                stops += 1
                inconclusive += int(decision['action'] == 'INCONCLUSIVE')
        table.append(dict(case_id=run['case_id'], policy=run['policy'], selections=selections,
                          legal_selections=selections, simulated_cost=cost, verified_facts=len(facts),
                          redundant_selections=redundant, repeated_selections=len(attempted) - len(set(attempted)),
                          stops=stops, correct_stops=stops, inconclusive=inconclusive,
                          rejected_candidates=rejections, failures=0))
    summaries = {}
    for policy in c.POLICIES:
        subset = [r for r in table if r['policy'] == policy]
        sums = {key: sum(r[key] for r in subset) for key in table[0] if key not in ('case_id', 'policy')}
        sums['legal_selection_rate'] = dict(numerator=sums['legal_selections'], denominator=sums['selections'])
        sums['stop_correctness'] = dict(numerator=sums['correct_stops'], denominator=sums['stops'])
        summaries[policy] = sums
    paired = []
    for cid in sorted({r['case_id'] for r in table}):
        p, b = (next(r for r in table if r['case_id'] == cid and r['policy'] == pid)
                for pid in ('PGE-v1', 'B0-fixed-v1'))
        # Descriptive fact/cost Pareto comparison, not significance or causal gain.
        better = p['verified_facts'] >= b['verified_facts'] and p['simulated_cost'] <= b['simulated_cost']
        worse = p['verified_facts'] <= b['verified_facts'] and p['simulated_cost'] >= b['simulated_cost']
        equal = (p['verified_facts'], p['simulated_cost']) == (b['verified_facts'], b['simulated_cost'])
        label = 'TIE' if equal else 'FAVORABLE' if better else 'UNFAVORABLE' if worse else 'TRADEOFF'
        paired.append(dict(case_id=cid, label=label, facts_delta=p['verified_facts'] - b['verified_facts'],
                           cost_delta=p['simulated_cost'] - b['simulated_cost']))
    return dict(table=table, summaries=summaries, paired=paired,
                definitions=c.METRIC_DEFINITIONS)


def run(*, reverse=False):
    fixture, source = c.catalog(), c.source_identity()
    runs = [replay_case(case, policy, source, reverse=reverse)
            for case in fixture['cases'] for policy in c.POLICIES]
    result = dict(schema=c.ABI, owner=c.OWNER, level=c.LEVEL, source_sha256=source,
                  fixture_sha256=c.sha(c.CATALOG.read_bytes()), seed=fixture['seed'],
                  policies=list(c.POLICIES), runs=runs, comparison=comparison(runs),
                  limitations=['REAL_EXPLORER_NOT_RUN', 'TARGET_NOT_RUN', 'AUTHORITY_NOT_RUN',
                               'PROVIDER_TOKENS_ZERO', 'L2_NOT_ESTABLISHED', 'RPF74_NOT_REPAIRED'])
    result['result_sha256'] = c.digest(result)
    return result
