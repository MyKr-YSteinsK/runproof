"""RPF76 independent abstract offline ABI. No executable tool/URI fields."""
import hashlib
import json
from pathlib import Path
import re

OWNER = 'rpf-76-rev-1'
ABI = 'rpf76-offline-generalization-v1'
LEVEL = 'OFFLINE_GENERALIZATION_AND_METRIC_EVALUATION_ONLY'
POLICIES = ('PGE-v2', 'B0-fixed-v2', 'B1-score-ablation-v2')
ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / '.local/rpf-76'
INPUTS = ('spikes/rpf-76/fixture-catalog.json', 'spikes/rpf-76/holdout-catalog.json')
SOURCES = tuple('runtime/runproof_runtime/effectwitness/pge_r76_' + name + '.py' for name in (
    'contracts', 'provenance', 'policy', 'oracle', 'replay', 'metrics', 'verify', 'fixtures')) + (
    'runtime/tests/test_effectwitness_pge_r76.py', 'spikes/rpf-76/probe.py') + INPUTS
REFERENCES = tuple('runtime/runproof_runtime/effectwitness/pge_r75_' + name + '.py' for name in (
    'contracts', 'policy', 'feedback', 'replay', 'verify')) + ('AGENTS.md',)
RULES = dict(version='stop-utility-v1', opportunity='fresh eligible candidate in frozen worthwhile_ids',
             must_stop='domain UNKNOWN, time/step cap, empty pool, or no eligible candidate',
             uncertainty='conflict, no trustworthy records, or no prescribed fresh utility',
             unknown_scope='DOMAIN_ONLY', weak_trust='CLOSED_WORLD_SYNTHETIC_ROSTER_NOT_ATTESTATION')
DEFINITIONS = dict(correct_stop='STOP with MUST_STOP oracle', total_stop='all STOP actions only',
    missed_opportunity='STOP or INCONCLUSIVE with SHOULD_SELECT oracle',
    unsafe_select='SELECT outside independent eligible set or under MUST_STOP',
    appropriate_inconclusive='INCONCLUSIVE with INCONCLUSIVE_ALLOWED',
    stop_not_determinable='STOP with INCONCLUSIVE_ALLOWED; not counted correct',
    stop_correctness='correct_stop / determinate_stop; determinate excludes stop_not_determinable',
    verified_facts='distinct key/value pairs in selected VERIFIED synthetic outcomes',
    simulated_cost='integer cost of selected candidates',
    redundancy='selection adds no verified outcome fact, including UNKNOWN/INCONCLUSIVE',
    fairness='same pool, state rules, budget, visibility schedule and outcome oracle for three policies',
    limitation='Hand-constructed exposed holdout; no statistical, causal or real Agent benefit')


class Invalid(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Invalid(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def equal(a, b):
    return canonical(a) == canonical(b)


def strict(raw):
    def pairs(rows):
        result = {}
        for k, v in rows:
            require(k not in result, 'DUPLICATE_JSON')
            result[k] = v
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, 'NONFINITE'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Invalid('JSON_STRUCTURE') from exc


def keys(value, names, code):
    require(type(value) is dict and set(value) == set(names.split()), code)


def units(value, code, low=0, high=1_000_000):
    require(type(value) is int and low <= value <= high, code)


def ident(value, code):
    require(type(value) is str and re.fullmatch('[a-z][a-z0-9-]{1,63}', value) is not None, code)


def hexsha(value, code):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, code)


def view(case):
    return case['view']


def normalize(v):
    return dict(v, candidates=sorted(v['candidates'], key=lambda x: x['candidate_id']),
                permissions=sorted(v['permissions']), fact_keys=sorted(v['fact_keys']))


def snapshot_sha(v):
    return digest(normalize(v))


def validate_view(v):
    keys(v, 'schema case_id split domain fact_keys candidates permissions budget risk_cap deadline max_steps weights initial_unknown', 'VIEW_SCHEMA')
    require(v['schema'] == ABI and v['split'] in ('development', 'holdout'), 'VIEW_ID')
    ident(v['case_id'], 'CASE_ID')
    ident(v['domain'], 'DOMAIN_ID')
    require(v['domain'].startswith('lab-'), 'ABSTRACT_DOMAIN')
    require(type(v['fact_keys']) is list and 8 <= len(v['fact_keys']) <= 32
            and len(set(v['fact_keys'])) == len(v['fact_keys']), 'FACT_SPACE')
    for name in v['fact_keys']:
        ident(name, 'FACT_ID')
    require(type(v['permissions']) is list and set(v['permissions']) <= {'observe', 'simulate'}
            and len(set(v['permissions'])) == len(v['permissions']), 'PERMISSIONS')
    require(type(v['initial_unknown']) is list and len(set(v['initial_unknown'])) == len(v['initial_unknown']), 'UNKNOWN_DOMAINS')
    for domain in v['initial_unknown']:
        ident(domain, 'UNKNOWN_DOMAIN_ID')
    for name in ('budget', 'risk_cap', 'deadline', 'max_steps'):
        units(v[name], name.upper(), high={'risk_cap': 3, 'deadline': 100, 'max_steps': 5}.get(name, 1_000_000))
    require(v['deadline'] >= 1 and v['max_steps'] >= 1, 'POSITIVE_LIMIT')
    keys(v['weights'], 'gain priority cost risk', 'WEIGHTS')
    for weight in v['weights'].values():
        units(weight, 'WEIGHT_RANGE', high=100)
    require(type(v['candidates']) is list and len(v['candidates']) <= 6, 'POOL_SIZE')
    ids = []
    for x in v['candidates']:
        keys(x, 'candidate_id domain cost risk permission requires effects repeat order priority source_sha256 contract_sha256', 'CANDIDATE_SCHEMA')
        ident(x['candidate_id'], 'CANDIDATE_ID')
        require(x['domain'] == v['domain'] and x['candidate_id'].startswith(v['domain'] + '-'), 'CANDIDATE_SCOPE')
        units(x['cost'], 'COST_RANGE', low=1)
        units(x['risk'], 'RISK_RANGE', high=3)
        units(x['order'], 'ORDER_RANGE', high=6)
        units(x['priority'], 'PRIORITY_RANGE', high=100)
        require(type(x['repeat']) is bool and x['permission'] in ('observe', 'simulate'), 'CANDIDATE_MODE')
        for name in ('requires', 'effects'):
            require(type(x[name]) is list and len(set(x[name])) == len(x[name])
                    and set(x[name]) <= set(v['fact_keys']), 'CANDIDATE_FACTS')
        hexsha(x['source_sha256'], 'CANDIDATE_SOURCE')
        require(x['contract_sha256'] == digest({k: value for k, value in x.items() if k != 'contract_sha256'}), 'CANDIDATE_ANCHOR')
        ids.append(x['candidate_id'])
    require(len(ids) == len(set(ids)), 'DUPLICATE_CANDIDATE')


def initial(v):
    return dict(step=0, remaining=v['budget'], elapsed=0, attempted=[], unknown_domains=sorted(v['initial_unknown']))


def validate_state(v, state):
    keys(state, 'step remaining elapsed attempted unknown_domains', 'STATE_SCHEMA')
    units(state['step'], 'STATE_STEP', high=v['max_steps'])
    units(state['remaining'], 'STATE_BUDGET', high=v['budget'])
    units(state['elapsed'], 'STATE_TIME', high=100)
    require(type(state['attempted']) is list and len(state['attempted']) == state['step']
            and set(state['attempted']) <= {x['candidate_id'] for x in v['candidates']}, 'STATE_ATTEMPTED')
    require(type(state['unknown_domains']) is list and len(set(state['unknown_domains'])) == len(state['unknown_domains']), 'STATE_UNKNOWN')
    for name in state['unknown_domains']:
        ident(name, 'STATE_UNKNOWN_ID')


def allowed_file(value):
    path = Path(value).absolute()
    public = ROOT / 'spikes/rpf-76/decision-traces.json'
    require(path.suffix == '.json' and (path == public or path.is_relative_to(WORK)), 'FILE_SCOPE')
    for part in (path,) + tuple(path.parents):
        require(not part.is_symlink() and not (hasattr(part, 'is_junction') and part.is_junction()), 'FILE_LINK')
        if part == ROOT:
            break
    require(path.resolve() == path, 'FILE_SCOPE')
    return path


def source_map():
    rows = []
    for rel in SOURCES + REFERENCES:
        raw = (ROOT / rel).read_bytes()
        lf = raw.replace(b'\r\n', b'\n')
        rows.append(dict(path=rel, bytes=len(raw), raw_sha256=sha(raw), lf_sha256=sha(lf),
                         git_blob=hashlib.sha1(b'blob ' + str(len(lf)).encode() + b'\0' + lf).hexdigest()))
    return dict(schema=ABI, owner=OWNER, files=rows)


def source_identity():
    return digest(source_map())
