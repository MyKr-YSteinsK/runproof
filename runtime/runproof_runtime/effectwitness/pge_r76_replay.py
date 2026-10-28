"""Pure offline replay; the policy never receives outcome or utility labels."""
from . import pge_r76_contracts as c
from .pge_r76_fixtures import load
from .pge_r76_policy import decide
from .pge_r76_oracle import evaluate
from .pge_r76_metrics import comparison


def replay_case(case, policy, *, reverse=False):
    v = case['view']
    state, rows, previous = c.initial(v), [], '0' * 64
    for _ in range(v['max_steps'] + 1):
        records = sorted([r for r in case['records'] if r['visible_at'] <= state['step']], key=lambda x: x['evidence_id'])
        supplied = dict(v, candidates=list(reversed(v['candidates']))) if reverse else v
        d = decide(supplied, list(reversed(records)) if reverse else records, state,
                   case['roster'], case['roster_sha256'], policy)
        # Oracle gets frozen case and pre-decision state only, never the Decision.
        oracle = evaluate(case, records, state)
        outcome = case['outcomes'][d['candidate_id']] if d['action'] == 'SELECT' else None
        row = dict(seq=len(rows) + 1, state=state, snapshot_sha256=c.snapshot_sha(v),
                   visible_records=records, roster=case['roster'], roster_sha256=case['roster_sha256'],
                   decision=d, oracle=oracle, outcome=outcome, previous_sha256=previous)
        row['sha256'] = c.digest(row)
        previous = row['sha256']
        rows.append(row)
        if outcome is None:
            break
        unknown = set(state['unknown_domains'])
        if outcome['status'] == 'UNKNOWN':
            unknown.add(v['domain'])
        state = dict(step=state['step'] + 1, remaining=state['remaining'] - d['cost'],
                     elapsed=state['elapsed'] + 1, attempted=state['attempted'] + [d['candidate_id']],
                     unknown_domains=sorted(unknown))
    return dict(split=v['split'], case_id=v['case_id'], policy=policy, snapshot=v,
                oracle_labels=case['oracle'], rows=rows)


def run(splits=('development', 'holdout'), *, reverse=False):
    datasets = [load(split) for split in splits]
    runs = [replay_case(case, policy, reverse=reverse) for data in datasets for case in data['cases'] for policy in c.POLICIES]
    value = dict(schema=c.ABI, owner=c.OWNER, level=c.LEVEL, source_sha256=c.source_identity(),
                 inputs={split: c.sha((c.ROOT / c.INPUTS[0 if split == 'development' else 1]).read_bytes()) for split in splits},
                 exposure='HOLDOUT_EXPOSED_NOT_BLIND', policies=list(c.POLICIES), runs=runs,
                 evaluation=comparison(runs), limitations=['NO_REAL_AGENT', 'NO_AUTHORITY_ATTESTATION',
                     'NO_CAUSAL_GENERALIZATION', 'NO_CROSS_PLATFORM_PROOF', 'RPF74_PAUSED'])
    value['result_sha256'] = c.digest(value)
    return value
