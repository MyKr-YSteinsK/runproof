"""Versioned offline observable-feature contract; no executable adapters."""
import hashlib
import json
from pathlib import Path
import re

OWNER = 'rpf-77-rev-1'
ABI = 'rpf77-offline-utility-v1'
LEVEL = 'OFFLINE_UTILITY_POLICY_EVALUATION_ONLY'
POLICIES = ('PGE-v3-utility', 'PGE-v2-estimated-key-gain', 'B0-fixed')
ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / '.local/rpf-77'
INPUTS = ('spikes/rpf-77/dev-catalog.json', 'spikes/rpf-77/challenge-catalog.json')
SOURCES = tuple('runtime/runproof_runtime/effectwitness/pge_r77_' + n + '.py' for n in (
    'contracts', 'projection', 'utility', 'policy', 'oracle', 'baselines', 'replay', 'verify', 'fixtures')) + (
    'runtime/tests/test_effectwitness_pge_r77.py', 'spikes/rpf-77/probe.py') + INPUTS
REFERENCES = ('AGENTS.md', 'runtime/runproof_runtime/effectwitness/pge_r76_policy.py',
    'runtime/runproof_runtime/effectwitness/pge_r76_oracle.py', 'spikes/rpf-76/fixture-catalog.json',
    'spikes/rpf-76/holdout-catalog.json')
RULES = dict(version='normative-utility-v1', opportunity='fresh eligible worthwhile ID',
    over_exploration='eligible no-benefit ID or repeated completed worthwhile ID',
    stop='safety barrier, no eligible, or no residual normative benefit',
    undetermined='ambiguous labels; not authority truth', unknown='DOMAIN_ONLY')
DEFINITIONS = dict(correct_stop='STOP with MUST_STOP', total_stop='all STOP',
    stop_not_determinable='STOP with INCONCLUSIVE_ALLOWED or NOT_DETERMINABLE',
    missed_opportunity='STOP/INCONCLUSIVE with SHOULD_SELECT',
    unsafe_select='SELECT outside eligibility or under safety barrier',
    appropriate_inconclusive='INCONCLUSIVE with INCONCLUSIVE_ALLOWED or NOT_DETERMINABLE',
    over_exploration=RULES['over_exploration'], wasted_simulated_cost='cost of over-exploration SELECT',
    verified_facts='unique (key,value) in selected VERIFIED synthetic outcomes',
    simulated_cost='selected integer costs', risk_guard_violation='SELECT risk exceeds cap',
    repeated='SELECT already attempted ID', redundant='SELECT adds zero verified outcome facts',
    cost_per_verified_fact='cost / facts; null ratio and ZERO_FACTS if denominator zero',
    stop_correctness='correct_stop / (total_stop - stop_not_determinable)',
    scope='SYNTHETIC_OFFLINE_NORMATIVE_LABEL_NOT_AUTHORITY')


class Invalid(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise Invalid(reason)


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(x):
    return sha(canonical(x))


def equal(a, b):
    return canonical(a) == canonical(b)


def strict(raw):
    def pairs(rows):
        value = {}
        for k, v in rows:
            require(k not in value, 'DUPLICATE_JSON')
            value[k] = v
        return value
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, 'NONFINITE'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Invalid('JSON_STRUCTURE') from exc


def keys(x, expected, reason):
    require(type(x) is dict and set(x) == set(expected.split()), reason)


def integer(x, reason, low=0, high=1_000_000):
    require(type(x) is int and low <= x <= high, reason)


def ident(x, reason):
    require(type(x) is str and re.fullmatch('[a-z][a-z0-9-]{1,63}', x) is not None, reason)


def normalize(v):
    return dict(v, candidates=sorted(v['candidates'], key=lambda x: x['candidate_id']),
                fact_keys=sorted(v['fact_keys']), permissions=sorted(v['permissions']))


def snapshot_sha(v):
    return digest(normalize(v))


def validate(v):
    keys(v, 'schema case_id split snapshot_id domain fact_keys candidates budget risk_cap permissions deadline max_steps initial_elapsed initial_unknown', 'VIEW_SCHEMA')
    require(v['schema'] == ABI and v['split'] in ('development', 'challenge', 'diagnostic76'), 'VIEW_ID')
    for name in ('case_id', 'snapshot_id', 'domain'):
        ident(v[name], 'ID_' + name)
    require(v['domain'].startswith('lab-'), 'ABSTRACT_DOMAIN')
    require(type(v['fact_keys']) is list and 10 <= len(v['fact_keys']) <= 32 and len(set(v['fact_keys'])) == len(v['fact_keys']), 'FACT_SPACE')
    for key in v['fact_keys']:
        ident(key, 'FACT_ID')
    require(type(v['permissions']) is list and len(set(v['permissions'])) == len(v['permissions'])
            and set(v['permissions']) <= {'observe', 'simulate'}, 'PERMISSIONS')
    for field in ('budget', 'risk_cap', 'deadline', 'max_steps', 'initial_elapsed'):
        integer(v[field], field.upper(), high=dict(risk_cap=3, deadline=100, max_steps=4, initial_elapsed=100).get(field, 1_000_000))
    require(v['deadline'] >= 1 and v['max_steps'] >= 1, 'POSITIVE_LIMIT')
    require(type(v['initial_unknown']) is list and len(set(v['initial_unknown'])) == len(v['initial_unknown']), 'UNKNOWN_SCOPE')
    for domain in v['initial_unknown']:
        ident(domain, 'UNKNOWN_DOMAIN')
    require(type(v['candidates']) is list and len(v['candidates']) <= 6, 'POOL_SIZE')
    ids = []
    for x in v['candidates']:
        keys(x, 'candidate_id snapshot_id domain cost risk permission requires effect_keys priority order repeat verification_need freshness_need value_update_kind feature_status feature_visible_at source_kind source_sha256 contract_sha256', 'CANDIDATE_SCHEMA')
        ident(x['candidate_id'], 'CANDIDATE_ID')
        require(x['domain'] == v['domain'] and x['snapshot_id'] == v['snapshot_id']
                and x['candidate_id'].startswith(v['domain'] + '-'), 'CANDIDATE_SCOPE')
        for field in ('cost', 'risk', 'priority', 'order', 'verification_need', 'freshness_need', 'feature_visible_at'):
            integer(x[field], 'FEATURE_' + field, low=1 if field == 'cost' else 0,
                    high=dict(risk=3, priority=100, order=6, verification_need=2, freshness_need=2, feature_visible_at=0).get(field, 1_000_000))
        require(type(x['repeat']) is bool and x['permission'] in ('observe', 'simulate'), 'CANDIDATE_MODE')
        require(x['feature_status'] in ('KNOWN', 'UNKNOWN') and x['value_update_kind'] in ('NONE', 'REVALIDATE', 'UPDATE'), 'UTILITY_ENUM')
        require(x['source_kind'] == 'SYNTHETIC_CONTRACT'
                and type(x['source_sha256']) is str and re.fullmatch('[0-9a-f]{64}', x['source_sha256']), 'FEATURE_SOURCE')
        for field in ('requires', 'effect_keys'):
            require(type(x[field]) is list and len(set(x[field])) == len(x[field]) and set(x[field]) <= set(v['fact_keys']), 'FACT_REFERENCE')
        require(x['contract_sha256'] == digest({k: z for k, z in x.items() if k != 'contract_sha256'}), 'CANDIDATE_ANCHOR')
        ids.append(x['candidate_id'])
    require(len(ids) == len(set(ids)), 'DUPLICATE_CANDIDATE')


def initial(v):
    return dict(step=0, remaining=v['budget'], elapsed=v['initial_elapsed'], attempted=[], unknown_domains=sorted(v['initial_unknown']))


def state_valid(v, s):
    keys(s, 'step remaining elapsed attempted unknown_domains', 'STATE_SCHEMA')
    integer(s['step'], 'STATE_STEP', high=v['max_steps'])
    integer(s['remaining'], 'STATE_BUDGET', high=v['budget'])
    integer(s['elapsed'], 'STATE_TIME', high=104)
    require(type(s['attempted']) is list and len(s['attempted']) == s['step'] and set(s['attempted']) <= {x['candidate_id'] for x in v['candidates']}, 'STATE_ATTEMPTED')
    require(type(s['unknown_domains']) is list and len(set(s['unknown_domains'])) == len(s['unknown_domains']), 'STATE_UNKNOWN')
    for name in s['unknown_domains']:
        ident(name, 'STATE_UNKNOWN_ID')


def allowed_file(value):
    path = Path(value).absolute()
    require(path.suffix == '.json' and (path == ROOT/'spikes/rpf-77/decision-traces.json' or path.is_relative_to(WORK)), 'FILE_SCOPE')
    for part in (path,) + tuple(path.parents):
        require(not part.is_symlink() and not (hasattr(part, 'is_junction') and part.is_junction()), 'FILE_LINK')
        if part == ROOT:
            break
    require(path.resolve() == path, 'FILE_SCOPE')
    return path


def source_map():
    rows = []
    for rel in SOURCES + REFERENCES:
        raw = (ROOT/rel).read_bytes()
        lf = raw.replace(b'\r\n', b'\n')
        rows.append(dict(path=rel, bytes=len(raw), raw_sha256=sha(raw), lf_sha256=sha(lf),
                         git_blob=hashlib.sha1(b'blob '+str(len(lf)).encode()+b'\0'+lf).hexdigest()))
    return dict(owner=OWNER, abi=ABI, files=rows)


def source_identity():
    return digest(source_map())
