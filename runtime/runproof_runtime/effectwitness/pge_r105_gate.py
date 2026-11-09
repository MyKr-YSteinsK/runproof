"""Pure admission decision. The trusted controller owns feedback pins and ledger CAS."""
from . import pge_r105_contracts as c
from .sdk_presend_contracts import canonical

INPUT_ERRORS = (ValueError, TypeError, KeyError, AttributeError, RecursionError)


def admit(proposal, catalog, feedback, ledger_view):
    """Evaluate a proposal. The receipt grants no capability until consumed by the Host."""
    context = {"ledger_sha256": None, "catalog_sha256": None, "proposal_sha256": None,
               "feedback_sha256": None, "candidate_id": None, "candidate_sha256": None,
               "contract_sha256": None}

    def decide(status, reason, cost=None):
        permission = ("FIXTURE_ONLY" if ledger_view["mode"] == c.FIXTURE else "HOST_RECHECK_AND_CAS"
                      ) if status == "ACCEPT" else "NONE"
        result = {"schema": c.DECISION, **context, "status": status, "reason": reason,
                  "requested_debit": dict(cost if cost is not None else c.ZERO),
                  "next_permission": permission, "effect_execution": "NOT_RUN"}
        return {**result, "decision_sha256": c.digest(result)}

    try:
        expected = c.validate_ledger(ledger_view)
        context["ledger_sha256"] = c.digest(ledger_view)
        if type(catalog) is not dict or canonical(catalog) != canonical(expected):
            return decide("INCONCLUSIVE", "CATALOG_NOT_FROZEN")
        context["catalog_sha256"] = c.digest(expected)
    except INPUT_ERRORS:
        return decide("INCONCLUSIVE", "LEDGER_NOT_TRUSTED")
    try:
        c.validate_proposal(proposal)
    except INPUT_ERRORS:
        return decide("REJECT", "PROPOSAL_SCHEMA")
    name = proposal["candidate_id"]
    candidate = expected[name]
    context.update(proposal_sha256=c.digest(proposal), candidate_id=name,
                   candidate_sha256=candidate["candidate_sha256"], contract_sha256=candidate["contract_sha256"])
    if (ledger_view["latched"] or ledger_view["reconciliation"] != "NONE"
            or c.UNKNOWN in ledger_view["completed"]):
        return decide("MUST_STOP", "UNKNOWN_OR_RECONCILIATION_LATCH")
    if proposal["proposal_id"] in ledger_view["consumed_proposals"]:
        return decide("REJECT", "DUPLICATE_PROPOSAL")
    if proposal["ledger_sha256"] != context["ledger_sha256"]:
        return decide("REJECT", "STALE_LEDGER")
    if proposal["candidate_sha256"] != candidate["candidate_sha256"]:
        return decide("REJECT", "CANDIDATE_ANCHOR")
    if name == c.STOP:
        return decide("MUST_STOP", "EXPLORER_STOP")
    completed = ledger_view["completed"]
    if not completed:
        if name != ledger_view["seed"] or ledger_view["consumed_proposals"]:
            return decide("REJECT", "FROZEN_SEED_REQUIRED")
        if feedback is not None:
            return decide("REJECT", "UNEXPECTED_SEED_FEEDBACK")
        reason = "INITIAL_FROZEN_SEED"
    else:
        if name != c.UNKNOWN:
            return decide("REJECT", "CONTINUATION_SCOPE")
        if len(ledger_view["consumed_proposals"]) != len(completed):
            return decide("MUST_STOP", "PRIOR_ADMISSION_UNSETTLED")
        if feedback is None or ledger_view["expected_feedback_sha256"] is None:
            return decide("MUST_STOP", "MISSING_CONTINUATION_FEEDBACK")
        try:
            c.validate_feedback(feedback, ledger_view, expected[completed[-1]])
            anchor = c.digest(feedback)
        except INPUT_ERRORS:
            return decide("REJECT", "FEEDBACK_SCOPE_OR_PROVENANCE")
        if anchor != ledger_view["expected_feedback_sha256"]:
            return decide("REJECT", "UNANCHORED_FEEDBACK")
        context["feedback_sha256"] = anchor
        if feedback["outcome"] != "CONTRACT_SATISFIED_IN_RUN":
            return decide("MUST_STOP", "FEEDBACK_EFFECT_UNCONFIRMED")
        reason = "VERIFIED_CONTINUATION"
    if any(amount > ledger_view["remaining"][key] for key, amount in candidate["cost"].items()):
        return decide("REJECT", "BUDGET_EXCEEDED")
    return decide("ACCEPT", reason, candidate["cost"])
