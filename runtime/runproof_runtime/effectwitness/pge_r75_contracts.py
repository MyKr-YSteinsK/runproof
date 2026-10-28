"""Independent offline ABI; no executable adapters or external resource locators."""
import hashlib
import json
from pathlib import Path

OWNER = 'rpf-75-rev-1'
ABI = 'rpf75-offline-policy-v1'
POLICIES = ('PGE-v1', 'B0-fixed-v1', 'B1-no-feedback-v1')
LEVEL = 'OFFLINE_POLICY_SIMULATION_ONLY'
METRIC_DEFINITIONS = dict(legal_selection_rate='legal SELECT / all SELECT; verifier validates each guard',
                    stop_correctness='correct terminal decisions / terminal decisions, independently replayed',
                    rejected_candidates='candidate evaluations failing shared guard, not adversarial rejection rate',
                    verified_facts='distinct (key,value) from selected VERIFIED synthetic outcomes, excludes feedback',
                    redundant_selections='SELECT yielding zero new verified facts, includes unknown/inconclusive',
                    failure='invalid replay; valid inconclusive is not failure',
                    fairness='same frozen pool, budget, seed, exogenous feedback schedule and outcome oracle',
                    limitations='Hand-constructed synthetic cases; no population inference or L2/L3 causal claim')
MAX_UNITS = 1_000_000
ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / '.local/rpf-75'
CATALOG = ROOT / 'spikes/rpf-75/feedback-fixture-catalog.json'
SOURCE_PATHS = tuple('runtime/runproof_runtime/effectwitness/pge_r75_' + x + '.py'
                     for x in ('contracts', 'policy', 'feedback', 'baselines', 'replay', 'verify')) + (
    'runtime/tests/test_effectwitness_pge_r75.py', 'spikes/rpf-75/probe.py',
    'spikes/rpf-75/feedback-fixture-catalog.json')
REFERENCES = ('runtime/runproof_runtime/effectwitness/pge_r68_contracts.py',
              'runtime/runproof_runtime/effectwitness/pge_r68_explorer.py',
              'runtime/runproof_runtime/effectwitness/pge_r74r2_session.py', 'AGENTS.md')
DOMAINS = {'config-java-http': ('normal', 'local-delivery-suppressed-after-http200'),
           'order-sqlite': ('normal-full-refund', 'response-lost-after-sqlite-commit')}


class Invalid(ValueError):
    """Machine-readable rejection; no payload or free-form model text."""


def require(condition, code):
    if not condition:
        raise Invalid(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def strict(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Invalid('JSON_STRUCTURE') from exc


def keys(value, expected, code):
    require(type(value) is dict and set(value) == set(expected.split()), code)


def units(value, code, low=0, high=MAX_UNITS):
    require(type(value) is int and low <= value <= high, code)


def view(case):
    return normalize({key: case[key] for key in ('case_id', 'domain', 'candidates', 'budget', 'risk_cap',
            'permissions', 'weights', 'repeat', 'max_steps', 'deadline', 'initial_unknown')})


def normalize(v):
    return dict(v, candidates=sorted(v['candidates'], key=lambda r: (r['order'], r['candidate_id'])),
                permissions=sorted(v['permissions']))


def validate_view(v):
    keys(v, 'case_id domain candidates budget risk_cap permissions weights repeat max_steps deadline initial_unknown', 'VIEW_SCHEMA')
    require(type(v['case_id']) is str and v['case_id'].startswith('case-'), 'CASE_ID')
    require(v['domain'] in DOMAINS, 'DOMAIN')
    units(v['budget'], 'BUDGET_RANGE')
    units(v['risk_cap'], 'RISK_RANGE', high=3)
    units(v['max_steps'], 'STEP_RANGE', low=1, high=8)
    units(v['deadline'], 'TIME_RANGE', low=1, high=100)
    require(type(v['repeat']) is bool and type(v['initial_unknown']) is bool, 'MODE_BOOL')
    require(type(v['permissions']) is list and len(set(v['permissions'])) == len(v['permissions'])
            and set(v['permissions']) <= {'simulate-read', 'simulate-change'}, 'PERMISSIONS')
    keys(v['weights'], 'gain priority cost risk', 'WEIGHTS')
    for x in v['weights'].values():
        units(x, 'WEIGHT_RANGE', high=100)
    require(type(v['candidates']) is list and len(v['candidates']) <= 8, 'CANDIDATE_POOL')
    seen = set()
    for candidate in v['candidates']:
        keys(candidate, 'candidate_id domain order cost risk permission requires effects priority', 'CANDIDATE_SCHEMA')
        cid = candidate['candidate_id']
        require(cid in DOMAINS[v['domain']] and candidate['domain'] == v['domain'], 'CANDIDATE_DOMAIN')
        require(cid not in seen, 'DUPLICATE_CANDIDATE')
        seen.add(cid)
        units(candidate['order'], 'ORDER_RANGE', high=8)
        units(candidate['cost'], 'COST_RANGE', low=1)
        units(candidate['risk'], 'RISK_RANGE', high=3)
        units(candidate['priority'], 'PRIORITY_RANGE', high=100)
        require(candidate['permission'] in ('simulate-read', 'simulate-change'), 'CANDIDATE_PERMISSION')
        for field in ('requires', 'effects'):
            require(type(candidate[field]) is list and len(candidate[field]) <= 8
                    and all(type(x) is str and x in ('seed', 'version', 'receipt', 'recovery') for x in candidate[field])
                    and len(set(candidate[field])) == len(candidate[field]), 'FACT_KEYS')


def initial(v):
    return dict(step=0, remaining=v['budget'], attempted=[], unknown=v['initial_unknown'], elapsed=0)


def validate_state(v, state):
    keys(state, 'step remaining attempted unknown elapsed', 'STATE_SCHEMA')
    units(state['step'], 'STATE_STEP', high=8)
    units(state['remaining'], 'STATE_BUDGET', high=v['budget'])
    units(state['elapsed'], 'STATE_TIME', high=100)
    require(type(state['unknown']) is bool, 'STATE_UNKNOWN')
    require(type(state['attempted']) is list and len(state['attempted']) == state['step']
            and all(x in {r['candidate_id'] for r in v['candidates']} for x in state['attempted']), 'STATE_ATTEMPTED')
    require(v['repeat'] or len(set(state['attempted'])) == len(state['attempted']), 'STATE_REPEAT')


def source_map():
    rows = []
    for rel in SOURCE_PATHS + REFERENCES:
        path = ROOT / rel
        require(not path.is_symlink(), 'SOURCE_LINK')
        raw = path.read_bytes()
        lf = raw.replace(b'\r\n', b'\n')
        rows.append(dict(path=rel, bytes=len(raw), raw_sha256=sha(raw), lf_sha256=sha(lf),
                         raw_git_blob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
                         lf_git_blob=hashlib.sha1(b'blob ' + str(len(lf)).encode() + b'\0' + lf).hexdigest()))
    return dict(schema=ABI, owner=OWNER, files=rows)


def source_identity():
    return digest(source_map())


def catalog():
    value = strict(CATALOG.read_bytes())
    keys(value, 'schema owner seed level cases', 'CATALOG_SCHEMA')
    require(value['schema'] == ABI and value['owner'] == OWNER and value['level'] == LEVEL, 'CATALOG_ID')
    require(type(value['cases']) is list and 12 <= len(value['cases']) <= 24, 'CATALOG_COUNT')
    ids = []
    for case in value['cases']:
        keys(case, 'case_id domain candidates budget risk_cap permissions weights repeat max_steps deadline initial_unknown feedback outcomes description', 'CASE_SCHEMA')
        validate_view(view(case))
        require(type(case['description']) is str and type(case['feedback']) is list and type(case['outcomes']) is dict, 'CASE_DATA')
        require(set(case['outcomes']) == {x['candidate_id'] for x in case['candidates']}, 'ORACLE_CANDIDATES')
        for outcome in case['outcomes'].values():
            keys(outcome, 'status facts', 'ORACLE_SCHEMA')
            require(outcome['status'] in ('VERIFIED', 'INCONCLUSIVE', 'UNKNOWN'), 'ORACLE_STATUS')
            require(type(outcome['facts']) is dict and set(outcome['facts']) <= {'version', 'receipt', 'recovery'}
                    and all(type(x) is str for x in outcome['facts'].values()), 'ORACLE_FACTS')
        ids.append(case['case_id'])
    require(len(set(ids)) == len(ids), 'CATALOG_DUPLICATE')
    return value


def allowed_file(path):
    path = Path(path).absolute()
    require(path.suffix == '.json', 'FILE_TYPE')
    require(path == ROOT / 'spikes/rpf-75/decision-traces.json' or path.is_relative_to(WORK), 'FILE_SCOPE')
    for parent in (path,) + tuple(path.parents):
        require(not parent.is_symlink() and not (hasattr(parent, 'is_junction') and parent.is_junction()), 'FILE_LINK')
        if parent == ROOT:
            break
    resolved = path.resolve()
    require(resolved == path and (resolved == ROOT / 'spikes/rpf-75/decision-traces.json'
            or resolved.is_relative_to(WORK)), 'FILE_SCOPE')
    return resolved
