"""Independent read-only verifier. No policy/replay/metrics/oracle imports."""
from . import pge_r76_contracts as c
from .pge_r76_fixtures import load


def adjudicate(case, records, state, policy):
    """Recompute provenance, ranking and normative labels from frozen inputs."""
    v = case['view']
    facts, accepted, rejected, conflict = {}, [], [], False
    for r in sorted(records, key=lambda x: x['evidence_id']):
        c.require(case['roster']['entries'].get(r['evidence_id']) == c.digest(r), 'ROSTER_MEMBER')
        if r['visible_at'] > state['step'] or r['seq'] > state['step'] + 1:
            reason = 'FUTURE_RECORD'
        elif r['seq'] < r['visible_at'] + 1:
            reason = 'LATE_RECORD'
        elif r['case_id'] != v['case_id']:
            reason = 'CROSS_CASE'
        elif r['domain'] != v['domain']:
            reason = 'CROSS_DOMAIN'
        elif r['contract_sha256'] != c.snapshot_sha(v):
            reason = 'WRONG_CONTRACT'
        elif r['source_kind'] != 'FROZEN_SYNTHETIC':
            reason = 'UNTRUSTED_SOURCE'
        elif r['status'] != 'VERIFIED':
            reason = 'UNVERIFIED_STATUS'
        else:
            reason = None
        if reason:
            rejected.append(dict(evidence_id=r['evidence_id'], reason=reason))
        else:
            for key, value in r['facts'].items():
                conflict = conflict or (key in facts and facts[key] != value)
                facts[key] = value
            accepted.append(dict(evidence_id=r['evidence_id'], sha256=c.digest(r)))
    evidence = dict(facts=facts, accepted=accepted, rejected=rejected, conflict=conflict)
    barrier = ('UNKNOWN_STOP' if v['domain'] in state['unknown_domains'] else
               'TIME_STOP' if state['elapsed'] >= v['deadline'] else
               'STEP_STOP' if state['step'] >= v['max_steps'] else None)
    eligible, blocked = [], []
    if not barrier and not conflict and accepted:
        for x in v['candidates']:
            reason = ('REPEAT' if not x['repeat'] and x['candidate_id'] in state['attempted'] else
                      'BUDGET' if x['cost'] > state['remaining'] else 'RISK' if x['risk'] > v['risk_cap'] else
                      'PERMISSION' if x['permission'] not in v['permissions'] else
                      'PRECONDITION' if not set(x['requires']) <= facts.keys() else None)
            if reason:
                blocked.append(dict(candidate_id=x['candidate_id'], reason=reason))
            else:
                eligible.append(x)
    opportunities = sorted(x['candidate_id'] for x in eligible if x['candidate_id'] in case['oracle']['worthwhile_ids']
                           and x['candidate_id'] not in state['attempted'])
    oracle = dict(verdict='MUST_STOP' if barrier else 'INCONCLUSIVE_ALLOWED' if conflict or not accepted else
                  'MUST_STOP' if not eligible else 'SHOULD_SELECT' if opportunities else 'INCONCLUSIVE_ALLOWED',
                  eligible=sorted(x['candidate_id'] for x in eligible), opportunities=opportunities,
                  reason='SAFETY_LIMIT' if barrier else 'EVIDENCE_UNCERTAIN' if conflict or not accepted else
                  'NO_ELIGIBLE' if not eligible else 'FROZEN_FRESH_UTILITY' if opportunities else 'UTILITY_UNDETERMINED')
    d = dict(policy=policy, action='STOP', candidate_id=None, reason=None, cost=0,
             estimated_gain=0, ranking=[], rejected=[], evidence=evidence)
    if barrier:
        d['reason'] = barrier
    elif conflict or not accepted:
        d.update(action='INCONCLUSIVE', reason='CONFLICT' if conflict else 'NO_TRUSTED_EVIDENCE')
    else:
        d['rejected'] = sorted(blocked, key=lambda x: x['candidate_id'])
        for x in eligible:
            gain = sum(key not in (set() if policy == 'B1-score-ablation-v2' else facts.keys()) for key in x['effects'])
            w = v['weights']
            terms = {'gain': w['gain'] * gain, 'priority': w['priority'] * x['priority'],
                     'cost': -w['cost'] * x['cost'], 'risk': -w['risk'] * x['risk']}
            d['ranking'].append(dict(candidate_id=x['candidate_id'], gain=gain, terms=terms,
                                     score=sum(terms.values()), order=x['order']))
        d['ranking'].sort(key=(lambda r: (r['order'], r['candidate_id'])) if policy == 'B0-fixed-v2'
                          else lambda r: (-r['score'], r['candidate_id']))
        if not eligible:
            d['reason'] = 'NO_ELIGIBLE'
        elif policy != 'B0-fixed-v2' and max(x['gain'] for x in d['ranking']) == 0:
            d['reason'] = 'ESTIMATED_ZERO_GAIN'
        else:
            x = next(x for x in eligible if x['candidate_id'] == d['ranking'][0]['candidate_id'])
            d.update(action='SELECT', reason='FIXED_ORDER' if policy == 'B0-fixed-v2' else 'MAX_SCORE',
                     candidate_id=x['candidate_id'], cost=x['cost'], estimated_gain=d['ranking'][0]['gain'])
    return d, oracle


def recompute_metrics(rows):
    names = 'decisions selects legal_selects total_stop correct_stop stop_not_determinable missed_opportunity unsafe_select appropriate_inconclusive inconclusive simulated_cost verified_facts repeated redundant rejected'.split()
    result = dict.fromkeys(names, 0)
    seen, attempted = set(), set()
    for row in rows:
        result['decisions'] += 1
        d, o = row['decision'], row['oracle']
        result['rejected'] += len(d['rejected'])
        if d['action'] == 'SELECT':
            result['selects'] += 1
            legal = d['candidate_id'] in o['eligible'] and o['verdict'] != 'MUST_STOP'
            result['legal_selects'] += int(legal)
            result['unsafe_select'] += int(not legal)
            result['simulated_cost'] += d['cost']
            result['repeated'] += int(d['candidate_id'] in attempted)
            attempted.add(d['candidate_id'])
            actual = set(row['outcome']['facts'].items()) if row['outcome']['status'] == 'VERIFIED' else set()
            result['redundant'] += int(not (actual - seen))
            seen |= actual
        elif d['action'] == 'STOP':
            result['total_stop'] += 1
            if o['verdict'] == 'MUST_STOP':
                result['correct_stop'] += 1
            elif o['verdict'] == 'SHOULD_SELECT':
                result['missed_opportunity'] += 1
            else:
                result['stop_not_determinable'] += 1
        else:
            result['inconclusive'] += 1
            if o['verdict'] == 'SHOULD_SELECT':
                result['missed_opportunity'] += 1
            if o['verdict'] == 'INCONCLUSIVE_ALLOWED':
                result['appropriate_inconclusive'] += 1
    result['verified_facts'] = len(seen)
    return result


def verify(value):
    c.keys(value, 'schema owner level source_sha256 inputs exposure policies runs evaluation limitations result_sha256', 'TRACE_SCHEMA')
    c.require(value['schema'] == c.ABI and value['owner'] == c.OWNER and value['level'] == c.LEVEL, 'TRACE_ID')
    c.require(value['source_sha256'] == c.source_identity(), 'SOURCE_IDENTITY')
    c.require(type(value['inputs']) is dict and set(value['inputs']) in ({'development'}, {'development', 'holdout'}), 'SPLIT_SET')
    splits = ('development', 'holdout') if 'holdout' in value['inputs'] else ('development',)
    data = {split: load(split) for split in splits}
    for split in splits:
        c.require(value['inputs'][split] == c.sha((c.ROOT / c.INPUTS[0 if split == 'development' else 1]).read_bytes()), 'INPUT_RAW_ANCHOR')
    c.require(value['exposure'] == 'HOLDOUT_EXPOSED_NOT_BLIND' and c.equal(value['policies'], list(c.POLICIES)), 'EXPOSURE_POLICY')
    c.require(c.equal(value['limitations'], ['NO_REAL_AGENT', 'NO_AUTHORITY_ATTESTATION', 'NO_CAUSAL_GENERALIZATION',
                                           'NO_CROSS_PLATFORM_PROOF', 'RPF74_PAUSED']), 'CLAIM_BOUNDARY')
    c.require(value['result_sha256'] == c.digest({k: v for k, v in value.items() if k != 'result_sha256'}), 'RESULT_HASH')
    expected = [(split, case, policy) for split in splits for case in data[split]['cases'] for policy in c.POLICIES]
    c.require(type(value['runs']) is list and len(value['runs']) == len(expected), 'RUN_COUNT')
    table = []
    for run, (split, case, policy) in zip(value['runs'], expected):
        c.keys(run, 'split case_id policy snapshot oracle_labels rows', 'RUN_SCHEMA')
        v = case['view']
        c.require(run['split'] == split and run['case_id'] == v['case_id'] and run['policy'] == policy, 'RUN_SCOPE')
        c.require(c.equal(run['snapshot'], v), 'FROZEN_SNAPSHOT')
        c.require(c.equal(run['oracle_labels'], case['oracle']), 'FROZEN_ORACLE_LABELS')
        state, previous, terminal = c.initial(v), '0' * 64, False
        c.require(type(run['rows']) is list and 1 <= len(run['rows']) <= v['max_steps'] + 1, 'ROW_COUNT')
        for index, row in enumerate(run['rows']):
            c.require(not terminal, 'AFTER_TERMINAL')
            c.keys(row, 'seq state snapshot_sha256 visible_records roster roster_sha256 decision oracle outcome previous_sha256 sha256', 'ROW_SCHEMA')
            c.require(type(row['seq']) is int and row['seq'] == index + 1, 'ROW_SEQ')
            c.require(c.equal(row['state'], state), 'STATE_CHAIN')
            c.validate_state(v, row['state'])
            c.require(row['snapshot_sha256'] == c.snapshot_sha(v), 'SNAPSHOT_ANCHOR')
            c.require(c.equal(row['roster'], case['roster']) and row['roster_sha256'] == case['roster_sha256'], 'FROZEN_ROSTER')
            records = sorted([r for r in case['records'] if r['visible_at'] <= state['step']], key=lambda x: x['evidence_id'])
            c.require(c.equal(row['visible_records'], records), 'FROZEN_VISIBLE_RECORDS')
            c.require(row['previous_sha256'] == previous and row['sha256'] == c.digest({k: v for k, v in row.items() if k != 'sha256'}), 'ROW_HASH_ORDER')
            decision, oracle = adjudicate(case, records, state, policy)
            c.require(c.equal(row['decision'], decision), 'POLICY_SEMANTICS')
            c.require(c.equal(row['oracle'], oracle), 'STOP_ORACLE_SEMANTICS')
            if decision['action'] == 'SELECT':
                outcome = case['outcomes'][decision['candidate_id']]
                c.require(c.equal(row['outcome'], outcome), 'FROZEN_OUTCOME')
                unknown = set(state['unknown_domains']) | ({v['domain']} if outcome['status'] == 'UNKNOWN' else set())
                state = dict(step=state['step'] + 1, remaining=state['remaining'] - decision['cost'],
                             elapsed=state['elapsed'] + 1, attempted=state['attempted'] + [decision['candidate_id']],
                             unknown_domains=sorted(unknown))
            else:
                c.require(row['outcome'] is None, 'TERMINAL_OUTCOME')
                terminal = True
            previous = row['sha256']
        c.require(terminal, 'MISSING_TERMINAL')
        table.append(dict(split=split, case_id=v['case_id'], policy=policy, **recompute_metrics(run['rows'])))
    ev = value['evaluation']
    c.keys(ev, 'table summaries pairs definitions', 'METRIC_SCHEMA')
    c.require(c.equal(ev['table'], table), 'METRIC_REPLAY')
    summaries = {}
    for split in splits:
        summaries[split] = {}
        for policy in c.POLICIES:
            part = [r for r in table if r['split'] == split and r['policy'] == policy]
            totals = {k: sum(r[k] for r in part) for k in part[0] if k not in ('split', 'case_id', 'policy')}
            totals['stop_correctness'] = dict(numerator=totals['correct_stop'], denominator=totals['total_stop'] - totals['stop_not_determinable'])
            totals['inconclusive_appropriateness'] = dict(numerator=totals['appropriate_inconclusive'], denominator=totals['inconclusive'])
            totals['legal_selection_rate'] = dict(numerator=totals['legal_selects'], denominator=totals['selects'])
            summaries[split][policy] = totals
    c.require(c.equal(ev['summaries'], summaries), 'METRIC_DENOMINATORS')
    pairs = []
    for split, cid in sorted({(r['split'], r['case_id']) for r in table}):
        p, b = [next(r for r in table if r['split'] == split and r['case_id'] == cid and r['policy'] == policy)
                for policy in ('PGE-v2', 'B0-fixed-v2')]
        fd, cd = p['verified_facts'] - b['verified_facts'], p['simulated_cost'] - b['simulated_cost']
        label = 'TIE' if fd == cd == 0 else 'FAVORABLE' if fd >= 0 and cd <= 0 else 'UNFAVORABLE' if fd <= 0 and cd >= 0 else 'TRADEOFF'
        pairs.append(dict(split=split, case_id=cid, label=label, facts_delta=fd, cost_delta=cd,
                          missed_opportunity_delta=p['missed_opportunity'] - b['missed_opportunity']))
    c.require(c.equal(ev['pairs'], pairs) and c.equal(ev['definitions'], c.DEFINITIONS), 'PAIRED_DEFINITIONS')
    return dict(status='PASS', reason='INDEPENDENT_OFFLINE_EVALUATION', runs=len(expected),
                decisions=sum(len(r['rows']) for r in value['runs']), level=c.LEVEL)


def verify_file(path, anchor):
    if not anchor:
        return 2, dict(status='NOT_RUN', reason='ANCHOR_REQUIRED')
    try:
        path = c.allowed_file(path)
        if not path.is_file():
            return 2, dict(status='NOT_RUN', reason='FILE_REQUIRED')
        raw = path.read_bytes()
        c.require(c.sha(raw) == anchor, 'RAW_ANCHOR')
        return 0, verify(c.strict(raw))
    except (c.Invalid, OSError, KeyError, TypeError, IndexError, AttributeError) as exc:
        return 3, dict(status='FAIL', reason=str(exc) if isinstance(exc, c.Invalid) else 'MALFORMED_INPUT')
