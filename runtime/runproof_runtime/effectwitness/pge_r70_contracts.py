"""Versioned local compatibility contracts. No signing or Provider authority."""
import hashlib
import json

OWNER = 'rpf-70'
VERSION = 'rpf70-owner-source-v1'
KIND = 'RPF70_LOCAL_COMPATIBILITY_ONLY'
BASE = '86b033b94556c0931aa590c79e69fda672a4915e'
BRANCH = 'codex/rpf-70-owner-source-runtime-seam'
DOMAINS = ('config-java-http', 'order-sqlite')
ROLES = ('TARGET', 'CONTROLLER', 'EXPLORER')
PHASES = ('prepare', 'allowed', 'invoke', 'business', 'authority', 'cleanup', 'select')
FLAGS = dict(FULL_COMMON_CORE_MIGRATED='NO', CORE_FULLY_MIGRATED='NO',
             BUDGET_EXECUTION_MIGRATED='NO', SDK_GUARD_EXECUTION_MIGRATED='NO',
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
