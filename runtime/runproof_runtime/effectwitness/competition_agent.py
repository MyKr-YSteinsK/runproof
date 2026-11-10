"""Offline reference policy. It receives attestations and proposes tool intents."""
from ..models import AGENT_OBSERVE_BEFORE_MUTATION, NO_BLIND_RETRY_AFTER_UNKNOWN_OUTCOME
from .product_local_contracts import SUCCESS, digest

MODE = "OFFLINE_REFERENCE_AGENT"
PROFILE = "effectwitness-reference/1"
TOOLS = {"order": "refund_order", "ops": "apply_config"}
LIMITS = {"sessions": 1, "steps": 2, "writes_per_domain": 1, "provider_reservations": 0}
INVARIANTS = (AGENT_OBSERVE_BEFORE_MUTATION, NO_BLIND_RETRY_AFTER_UNKNOWN_OUTCOME)


def attestation_matches(envelope, candidate, session_id, source_sha256):
    if not isinstance(envelope, dict) or set(envelope) != {"value", "sha256"}:
        return False
    value = envelope["value"]
    return (isinstance(value, dict) and value.get("session_id") == session_id
            and value.get("source_sha256") == source_sha256
            and value.get("contract_sha256") == candidate["sha256"]
            and value.get("contract_outcome") == SUCCESS
            and value.get("domain") == candidate["candidate"]
            and digest(value) == envelope["sha256"])


def tool_intent(candidate, step, observation_sha, feedback_sha=None):
    domain = candidate["candidate"]
    operation = candidate["execution"]["operation_id"]
    return {"candidate_id": domain, "action_id": operation, "tool": TOOLS[domain],
            "arguments": {"operation_id": operation}, "step": step,
            "contract_sha256": candidate["sha256"], "observation_sha256": observation_sha,
            "input_feedback_sha256": feedback_sha}


class AgentPolicy:
    def propose(self, observation):
        candidates = {item["candidate"]: item for item in observation["candidates"]}
        step = observation["step"]
        trusted = observation["feedback"]
        if step == 1 and trusted is None and "order" in candidates:
            domain = "order"
        elif (step == 2 and {"order", "ops"} <= candidates.keys()
              and attestation_matches(trusted, candidates["order"], observation["session_id"],
                                      observation["source_sha256"])):
            domain = "ops"
        else:
            return None
        if TOOLS[domain] not in observation["tool_allowlist"] or domain not in observation["available"]:
            return None
        return tool_intent(candidates[domain], step, digest(observation), trusted["sha256"] if trusted else None)
