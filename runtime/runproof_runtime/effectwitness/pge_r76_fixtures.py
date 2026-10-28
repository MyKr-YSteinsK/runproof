"""Deterministic hand-constructed cases; exposed holdout, no blind-test claim."""
from . import pge_r76_contracts as c


def make(split):
    c.require(split in ('development', 'holdout'), 'SPLIT_ID')
    domains = ('lab-amber', 'lab-bronze', 'lab-cobalt') if split == 'development' else ('lab-quartz', 'lab-nova', 'lab-opal')
    cases = []
    for index in range(24 if split == 'development' else 12):
        variant = index % 12
        domain = domains[index % 3]
        cid = ('dev-' if split == 'development' else 'hold-') + str(index).zfill(2)
        size = 1 + index % 4 if split == 'development' else 5 + index % 2
        candidates = []
        for i in range(size):
            x = dict(candidate_id=domain + '-c' + str(i), domain=domain, cost=2 + i,
                     risk=2 if variant == 6 else i % 3, permission='simulate', requires=['fact-00'],
                     effects=['fact-01', 'fact-02'] if i == 0 else ['fact-' + str(i + 2).zfill(2)],
                     repeat=index % 2 == 0, order=i, priority=size - i,
                     source_sha256=c.digest(dict(owner=c.OWNER, domain=domain, source='SYNTHETIC_DESCRIPTION')))
            x['contract_sha256'] = c.digest(x)
            candidates.append(x)
        v = dict(schema=c.ABI, case_id=cid, split=split, domain=domain,
                 fact_keys=['fact-' + str(i).zfill(2) for i in range(12)], candidates=candidates,
                 permissions=[] if variant == 4 else ['observe', 'simulate'], budget=0 if variant == 5 else 18,
                 risk_cap=0 if variant == 6 else 2, deadline=1 if variant == 9 else 6,
                 max_steps=3, weights=dict(gain=10, priority=2, cost=1, risk=1),
                 initial_unknown=[domain] if variant == 2 else ['lab-unrelated'] if variant == 3 else [])
        records = []

        def record(label, at, facts, status='VERIFIED', source='FROZEN_SYNTHETIC', **changes):
            r = dict(evidence_id=cid + '-' + label, case_id=cid, domain=domain, source_kind=source,
                     contract_sha256=c.snapshot_sha(v), visible_at=at, seq=at + 1, status=status, facts=facts)
            r.update(changes)
            records.append(r)

        seed = {'fact-00': 'ready'}
        if variant == 1:
            seed.update({name: 'already-observed' for x in candidates for name in x['effects']})
        record('initial', 0, seed, status='OBSERVED' if variant == 7 else 'VERIFIED',
               source='MODEL_ASSERTION' if variant == 10 else 'FROZEN_SYNTHETIC')
        if variant == 8:
            record('contradiction', 0, {'fact-00': 'not-ready'})
        record('update', 1, {'fact-01': 'seen', 'fact-02': 'seen'},
               status='INCONCLUSIVE' if variant == 7 else 'VERIFIED',
               contract_sha256='0' * 64 if variant == 11 else c.snapshot_sha(v))
        # Frozen diagnostic records whose independent refusal reason is observable.
        record('cross-domain', 1, {}, domain='lab-foreign')
        record('cross-case', 1, {}, case_id='other-case')
        record('late', 9, {'fact-11': 'late'})
        roster = dict(schema=c.ABI, case_id=cid, entries={r['evidence_id']: c.digest(r) for r in records})
        outcomes = {x['candidate_id']: dict(status='UNKNOWN' if variant == 11 and i == 0 else
            'INCONCLUSIVE' if variant == 10 else 'VERIFIED',
            facts={} if variant in (10, 11) else {name: 'outcome-' + str(i) for name in x['effects']})
            for i, x in enumerate(candidates)}
        case = dict(view=c.normalize(v), records=records, roster=roster, roster_sha256=c.digest(roster),
                    outcomes=outcomes, oracle=dict(rules=c.RULES, worthwhile_ids=[] if variant == 10 else sorted(outcomes)),
                    design_variant=variant)
        cases.append(case)
    return dict(schema=c.ABI, owner=c.OWNER, split=split, seed=7601 if split == 'development' else 7602,
                exposure='HOLDOUT_EXPOSED_NOT_BLIND' if split == 'holdout' else 'DEVELOPMENT', cases=cases)


def load(split):
    c.require(split in ('development', 'holdout'), 'SPLIT_ID')
    path = c.ROOT / c.INPUTS[0 if split == 'development' else 1]
    data = c.strict(path.read_bytes())
    c.keys(data, 'schema owner split seed exposure cases', 'CATALOG_SCHEMA')
    c.require(data['schema'] == c.ABI and data['owner'] == c.OWNER and data['split'] == split, 'CATALOG_ID')
    c.require(data['exposure'] == ('DEVELOPMENT' if split == 'development' else 'HOLDOUT_EXPOSED_NOT_BLIND'), 'EXPOSURE_LABEL')
    c.require(len(data['cases']) == (24 if split == 'development' else 12), 'CASE_COUNT')
    ids = []
    for case in data['cases']:
        c.keys(case, 'view records roster roster_sha256 outcomes oracle design_variant', 'CASE_SCHEMA')
        v = case['view']
        c.validate_view(v)
        c.require(v['split'] == split, 'SPLIT_SCOPE')
        c.keys(case['oracle'], 'rules worthwhile_ids', 'ORACLE_SCHEMA')
        pool = {x['candidate_id'] for x in v['candidates']}
        c.require(c.equal(case['oracle']['rules'], c.RULES) and set(case['oracle']['worthwhile_ids']) <= pool, 'ORACLE_LABEL')
        c.require(case['roster_sha256'] == c.digest(case['roster']) and set(case['outcomes']) == pool, 'CASE_ANCHOR')
        c.require(case['roster']['entries'] == {r['evidence_id']: c.digest(r) for r in case['records']}
                  and len(case['records']) == len(case['roster']['entries']), 'ROSTER_FROZEN')
        for outcome in case['outcomes'].values():
            c.keys(outcome, 'status facts', 'OUTCOME_SCHEMA')
            c.require(outcome['status'] in ('OBSERVED', 'VERIFIED', 'UNKNOWN', 'INCONCLUSIVE')
                      and type(outcome['facts']) is dict and set(outcome['facts']) <= set(v['fact_keys'])
                      and all(type(x) is str for x in outcome['facts'].values()), 'OUTCOME_VALUE')
        ids.append(v['case_id'])
    c.require(len(set(ids)) == len(ids), 'DUPLICATE_CASE')
    return data
