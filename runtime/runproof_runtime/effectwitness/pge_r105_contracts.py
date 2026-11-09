"""Frozen candidate directory and bounded Explorer admission inputs."""
from .product_sdk_contracts import freeze, hex_id
from .sdk_presend_contracts import canonical, check, sha

CANDIDATE = "rpf105-candidate-v1"
PROPOSAL = "rpf105-proposal-v1"
FEEDBACK = "rpf105-feedback-ref-v1"
LEDGER = "rpf105-ledger-view-v1"
DECISION = "rpf105-admission-v1"
NORMAL, UNKNOWN, STOP = "rpf104/NORMAL", "rpf104/UNKNOWN", "STOP"
FIXTURE = "SYNTHETIC_SELECTION_TEST"
LIVE = "LIVE_SAME_RUN"
LIMIT = {"cases": 2, "writes": 3, "forwards": 4}
ZERO = dict.fromkeys(LIMIT, 0)
FEEDBACK_AUTHORITY = "SQLITE_RO_QUERY_ONLY"
FEEDBACK_ORACLE = "RPF104_INDEPENDENT_ORACLE"


def digest(row):
    return sha(canonical(row))


def fields(row, *keys):
    check(type(row) is dict and set(row) == set(keys), "FIELDS")
    return row


def frozen_case(scope, case):
    fields(scope, "origin", "source_git_sha", "run_id", "owner")
    return freeze(scope["source_git_sha"], scope["run_id"], scope["owner"], case, origin=scope["origin"])


def candidate_catalog(scope):
    rows = {}
    for candidate_id, case in ((NORMAL, "NORMAL"), (UNKNOWN, "UNKNOWN")):
        frozen = frozen_case(scope, case)
        budget = frozen["budget"]
        rows[candidate_id] = {"schema": CANDIDATE, "candidate_id": candidate_id, "scope": dict(scope),
                              "case": case, "domains": list(frozen["contracts"]),
                              "contract_sha256": digest(frozen),
                              "cost": {"cases": 1, "writes": budget["writes"], "forwards": budget["forwards"]}}
    rows[STOP] = {"schema": CANDIDATE, "candidate_id": STOP, "scope": dict(scope),
                  "case": None, "domains": [], "contract_sha256": None, "cost": dict(ZERO)}
    return {name: {**row, "candidate_sha256": digest(row)} for name, row in rows.items()}


def validate_ledger(row):
    fields(row, "schema", "scope", "mode", "revision", "seed", "completed", "consumed_proposals",
           "remaining", "latched", "reconciliation", "expected_feedback_sha256")
    check(row["schema"] == LEDGER and type(row["revision"]) is int and 0 <= row["revision"] < 2**53
          and row["seed"] == NORMAL and type(row["latched"]) is bool
          and row["reconciliation"] in ("NONE", "COMMITTED", "NOT_COMMITTED", "UNAVAILABLE", "INCONCLUSIVE")
          and row["completed"] in ([], [NORMAL], [NORMAL, UNKNOWN]), "LEDGER_IDENTITY")
    catalog = candidate_catalog(row["scope"])
    check((row["mode"] == FIXTURE and row["scope"]["origin"] == "LOCAL")
          or (row["mode"] == LIVE and row["scope"]["origin"] == "GITHUB"), "LEDGER_MODE")
    seen = row["consumed_proposals"]
    check(type(seen) is list and len(seen) <= 64 and all(hex_id(value, 32) for value in seen)
          and len(set(seen)) == len(seen) and len(seen) >= len(row["completed"])
          and row["revision"] >= len(seen), "LEDGER_HISTORY")
    fields(row["remaining"], *LIMIT)
    for key, maximum in LIMIT.items():
        used = sum(catalog[name]["cost"][key] for name in row["completed"])
        actual = row["remaining"][key]
        check(type(actual) is int and 0 <= actual <= maximum - used, "LEDGER_BUDGET")
    anchor = row["expected_feedback_sha256"]
    check(anchor is None or (len(row["completed"]) == 1 and hex_id(anchor, 64)), "LEDGER_FEEDBACK")
    return catalog


def validate_proposal(row):
    fields(row, "schema", "proposal_id", "candidate_id", "candidate_sha256", "ledger_sha256")
    check(row["schema"] == PROPOSAL and hex_id(row["proposal_id"], 32)
          and row["candidate_id"] in (NORMAL, UNKNOWN, STOP)
          and hex_id(row["candidate_sha256"], 64) and hex_id(row["ledger_sha256"], 64), "PROPOSAL_IDENTITY")


def validate_feedback(row, ledger, prior):
    fields(row, "schema", "evidence_origin", "scope", "ledger_revision", "candidate_id",
           "case", "contract_sha256", "operation_id", "environment_id", "effect_contract_sha256",
           "oracle", "authority", "outcome", "evidence_sha256")
    expected = frozen_case(ledger["scope"], prior["case"])["contracts"]["order"]
    check(row["schema"] == FEEDBACK and row["evidence_origin"] == ledger["mode"]
          and canonical(row["scope"]) == canonical(ledger["scope"]) and type(row["ledger_revision"]) is int
          and row["ledger_revision"] == ledger["revision"] and row["candidate_id"] == prior["candidate_id"]
          and row["case"] == prior["case"] and row["contract_sha256"] == prior["contract_sha256"]
          and row["operation_id"] == expected["execution"]["operation_id"]
          and row["environment_id"] == expected["execution"]["environment_id"]
          and row["effect_contract_sha256"] == expected["sha256"] and row["oracle"] == FEEDBACK_ORACLE
          and row["authority"] == FEEDBACK_AUTHORITY and hex_id(row["evidence_sha256"], 64)
          and row["outcome"] in ("CONTRACT_SATISFIED_IN_RUN", "UNKNOWN_OUTCOME", "INCONCLUSIVE"),
          "FEEDBACK_IDENTITY")
