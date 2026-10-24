"""Versioned local compatibility contracts. No signing or Provider authority."""
import hashlib
import json

OWNER = 'rpf-71'
VERSION = 'rpf71-owner-source-v1.1'
KIND = 'RPF71_BUDGET_COMPATIBILITY_ONLY'
BASE = 'ef95f0965ad8f2325892f6800a4528112f1a6e52'
BRANCH = 'codex/rpf-71-budget-policy-execution-seam'
DOMAINS = ('config-java-http', 'order-sqlite')
ROLES = ('TARGET', 'CONTROLLER', 'EXPLORER')
PHASES = ('session', 'trial', 'driver', 'prepare', 'allowed', 'invoke', 'business', 'authority', 'cleanup', 'select')
FLAGS = dict(FULL_COMMON_CORE_MIGRATED='NO', CORE_FULLY_MIGRATED='NO',
             NATIVE_R68_BUDGET_CORE_REPLACED='NO', SDK_GUARD_EXECUTION_MIGRATED='NO',
             NATIVE_R68_SHARED_SESSION_RERUN='NO', REAL_PROVIDER_THIS_TASK='NOT_RUN',
             REAL_FAULT_THIS_TASK='NOT_RUN', ISSUER='NOT_ESTABLISHED', L2='NOT_ESTABLISHED',
             THIRD_DOMAIN='NOT_RUN', WEB='NOT_RUN')

def require(value, reason):
    if not value:
        raise ValueError(reason)

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def digest(value):
    return sha(canonical(value))

def strict(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            require(key not in out, 'DUPLICATE_JSON_KEY')
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: require(False, 'NONFINITE_JSON'))

def equal(actual, expected, reason):
    require(canonical(actual) == canonical(expected), reason)
