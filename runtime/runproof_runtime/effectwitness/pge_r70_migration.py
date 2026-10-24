"""Responsibility boundaries, deliberately independent of legacy Issuers."""
from . import pge_r70_contracts as c

def matrix():
    return dict(schema=c.VERSION, owner_source='TASK_OWNED_V1_EXECUTION',
                budget='LEGACY_R68_LEDGER_AND_REPLAY', sdk_guard='LEGACY_R68_CHILD_UNCHANGED',
                business='LEGACY_HTTP_SQL_ALGORITHMS', verifier='TASK_OWNED_LOCAL_ONLY',
                historical='ORIGINAL_NATIVE_CLI_ONLY', flags=c.FLAGS,
                evidence_accepted='ARCHITECT_DECISION_REQUIRED', stage_advanced='ARCHITECT_DECISION_REQUIRED')
