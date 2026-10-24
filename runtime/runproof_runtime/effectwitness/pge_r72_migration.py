"""Responsibility boundaries, deliberately independent of legacy Issuers."""
from . import pge_r72_contracts as c

def matrix():
    return dict(schema=c.VERSION, owner_source='VERSIONED_V1_2_R72',
                parent_child='CONTROLLER_PRELAUNCH_GATE_AND_NATIVE_SDK_EXECUTION',
                child_attestation='NOT_ESTABLISHED',
                budget_policy='VERSIONED_PRE_RESERVE_AND_PRE_SETTLE_GATE',
                budget='NATIVE_R68_SINGLE_WAL_AND_REPLAY_RETAINED', sdk_guard='LEGACY_R68_CHILD_UNCHANGED',
                business='LEGACY_HTTP_SQL_ALGORITHMS', verifier='TASK_OWNED_LOCAL_ONLY',
                historical='ORIGINAL_NATIVE_CLI_ONLY', flags=c.FLAGS,
                evidence_accepted='ARCHITECT_DECISION_REQUIRED', stage_advanced='ARCHITECT_DECISION_REQUIRED')
