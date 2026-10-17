"""New frozen contracts; legacy v1/v2/v3 validation is unchanged."""
import json
from dataclasses import dataclass

from .contracts import canonical, digest
from .cross_core import LIMITS, effect_template, spec_for, validate_contracts
from .witness_verify import _reject


@dataclass(frozen=True)
class CrossContracts:
    execution_bytes: bytes
    effect_bytes: bytes
    experiment_bytes: bytes

    @property
    def execution(self):
        return json.loads(self.execution_bytes)

    @property
    def effect(self):
        return json.loads(self.effect_bytes)

    @property
    def experiment(self):
        return json.loads(self.experiment_bytes)

    @property
    def hashes(self):
        return {k: digest(getattr(self, k)) for k in ("execution", "effect", "experiment")}

    def document(self):
        return {**{k: getattr(self, k) for k in ("execution", "effect", "experiment")}, "sha256": self.hashes}

    def validate(self):
        x = self.experiment
        validate_contracts(self.document(), x["domain"], x["capture_id"])
        _reject(all(getattr(self, k + "_bytes") == canonical(getattr(self, k))
                    for k in ("execution", "effect", "experiment")), "CONTRACT_NOT_CANONICAL")

    @classmethod
    def create(cls, domain, run_id, fault="response-lost"):
        spec = spec_for(domain)
        e = {"schema_version": "rpf-cross-execution-v1", "agent_id": "rpf44-bounded-agent",
             "driver": "deterministic", "tools": [spec["inspect"], spec["tool"]], "budgets": LIMITS}
        f = effect_template(domain, run_id)
        x = {"schema_version": "rpf-cross-experiment-v1", "domain": domain, "run_id": run_id,
             "scenario_id": "single-" + domain + "-effect", "environment_id": "env-" + run_id,
             "environment_revision": spec["revision"], "owner": "rpf-44", "reset_generation": 0,
             "fault": fault, "execution_digest": digest(e), "effect_digest": digest(f),
             "capture_id": "capture-" + run_id, "capture_mode": "DETERMINISTIC_CAPTURE"}
        result = cls(canonical(e), canonical(f), canonical(x))
        result.validate()
        return result
