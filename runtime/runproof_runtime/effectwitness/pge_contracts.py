"""Frozen RPF-42 catalog, pre-registration and per-trial v2 references."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .contracts import (ENV_REVISION, ROOT, FrozenContracts, canonical, digest, fields,
                        identifier, make_contracts, require)

PGE_ROOT = ROOT / ".local" / "rpf-42"
LIMITS = {"provider_requests": 4, "steps": 16, "tokens": 12000, "cost_cny": 1.5,
          "seconds": 1200, "request_seconds": 90, "fault_trials": 4}
TARGET = "DETERMINISTIC_CONTROLLED_TARGET"
ADAPTER_REVISION = "rpf42-order-trial-v1"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def catalog() -> list[dict]:
    common = {"environment_revision": ENV_REVISION, "tool": "refund_order",
              "precondition": "fresh-paid-order-generation-0", "physical_trials": 1,
              "permission": "owned-fictional-sqlite-only", "parameters": "frozen-order-operation-2500-CNY"}
    return [
        {**common, "candidate_id": "normal", "fault": "none", "trigger": "disabled"},
        {**common, "candidate_id": "planned-untriggered", "fault": "planned-not-triggered",
         "trigger": "intentionally-inhibited-negative-control"},
        {**common, "candidate_id": "response-lost", "fault": "response-lost",
         "trigger": "drop-refund-response-after-transaction-commit"},
    ]


@dataclass(frozen=True)
class SessionPlan:
    payload: bytes

    @property
    def document(self) -> dict:
        return json.loads(self.payload)

    @property
    def sha256(self) -> str:
        return digest(self.document)

    @classmethod
    def freeze(cls, document: dict) -> "SessionPlan":
        fields(document, {"schema_version", "session_id", "preregistered_at", "catalog",
                          "baseline_order", "limits", "trials_per_policy", "target_driver",
                          "adapter_revision", "objective", "metric_version", "source_digest"}, "SESSION_FIELDS")
        require(document["schema_version"] == "rpf-exploration-session-v1", "SESSION_VERSION")
        require(identifier(document["session_id"]), "SESSION_ID")
        stamp = document["preregistered_at"]
        try:
            valid_stamp = isinstance(stamp, str) and datetime.fromisoformat(stamp).tzinfo is not None
        except ValueError:
            valid_stamp = False
        require(valid_stamp, "PREREGISTRATION_TIMESTAMP")
        require(canonical(document["catalog"]) == canonical(catalog()), "CATALOG_NOT_FROZEN")
        require(document["baseline_order"] == ["normal", "planned-untriggered"], "BASELINE_PREREGISTRATION")
        require(canonical(document["limits"]) == canonical(LIMITS)
                and type(document["trials_per_policy"]) is int and document["trials_per_policy"] == 2,
                "SESSION_BUDGET")
        require(document["target_driver"] == TARGET and document["adapter_revision"] == ADAPTER_REVISION,
                "TRIAL_DRIVER_REVISION")
        require(document["objective"] == "verified-activation-provenance-coverage"
                and document["metric_version"] == "observable-fact-set-v1", "SESSION_METRICS")
        require(isinstance(document["source_digest"], str)
                and re.fullmatch(r"[0-9a-f]{64}", document["source_digest"]) is not None,
                "SESSION_SOURCE_DIGEST")
        return cls(canonical(document))

    @classmethod
    def create(cls) -> "SessionPlan":
        from .contracts import source_identity
        return cls.freeze({"schema_version": "rpf-exploration-session-v1",
            "session_id": "session-" + uuid.uuid4().hex, "preregistered_at": utc(),
            "catalog": catalog(), "baseline_order": ["normal", "planned-untriggered"],
            "limits": dict(LIMITS), "trials_per_policy": 2, "target_driver": TARGET,
            "adapter_revision": ADAPTER_REVISION, "objective": "verified-activation-provenance-coverage",
            "metric_version": "observable-fact-set-v1", "source_digest": source_identity()})

    def validate(self) -> None:
        require(self == self.freeze(self.document), "SESSION_NOT_CANONICAL")

    def candidate(self, candidate_id: str) -> dict:
        self.validate()
        require(type(candidate_id) is str, "CANDIDATE_TYPE", "AGENT")
        choices = [c for c in self.document["catalog"] if c["candidate_id"] == candidate_id]
        require(len(choices) == 1, "CANDIDATE_NOT_ALLOWLISTED", "AGENT")
        return choices[0]

    def trial_contracts(self, policy: str, candidate_id: str) -> FrozenContracts:
        candidate = self.candidate(candidate_id)
        require(policy in ("PGE", "B0"), "POLICY_NOT_ALLOWLISTED")
        old = make_contracts("trial-" + uuid.uuid4().hex, fault=candidate["fault"])
        experiment = {**old.experiment, "schema_version": "rpf-experiment-v2", "owner": "rpf-42",
                      "session_id": self.document["session_id"], "session_digest": self.sha256,
                      "candidate_id": candidate_id, "policy": policy}
        return FrozenContracts.freeze(old.execution, old.effect, experiment)

    def validate_trial(self, contracts: FrozenContracts, policy: str, candidate_id: str) -> None:
        contracts.validate()
        x = contracts.experiment
        require(x["schema_version"] == "rpf-experiment-v2" and x["owner"] == "rpf-42"
                and x["session_id"] == self.document["session_id"] and x["session_digest"] == self.sha256
                and x["policy"] == policy and x["candidate_id"] == candidate_id
                and x["fault"] == self.candidate(candidate_id)["fault"], "TRIAL_SESSION_MISMATCH")
