"""RPF-74 versioned, finite local-integration contracts."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / '.local' / 'rpf-74-rev-2'
OWNER = 'rpf-74-rev-2'
ABI = 'rpf74r2-controlled-factory-v1'
SOURCE_KIND = 'SYNTHETIC_TEST_ONLY'
DOMAINS = ('config-java-http', 'order-sqlite')
WRITES = frozenset(('create_config_v1', 'update_config_v2', 'refund_order'))
READS = frozenset(('inspect_config', 'inspect_order', 'reconcile_order'))
SCENARIOS = frozenset(('N', 'F'))
BASE = '15f82aeb33bd828cf40fe0accba07dc6fb9ecbc1'
SOURCE_NAMES = tuple('runtime/runproof_runtime/effectwitness/pge_r74r2_' + x + '.py' for x in (
    'contracts', 'owner_source', 'budget_gate', 'launch_contract', 'launch_factory',
    'sdk_harness', 'domain_ports', 'session', 'verify', 'fault', 'slot_contract')) + (
    'runtime/tests/test_effectwitness_pge_r74r2.py', 'runtime/tests/test_effectwitness_pge_r74r2_components.py', 'spikes/rpf-74/rev-2/probe.py',
    'spikes/rpf-74/rev-2/runner.py')

def require(condition, code):
    if not condition:
        raise ValueError(code)

def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

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
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, 'NONFINITE_JSON'))

def run_id(value):
    require(type(value) is str and re.fullmatch(r'rpf74r2-[a-f0-9]{16}', value), 'RUN_ID')
    return value
