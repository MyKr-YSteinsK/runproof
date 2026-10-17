"""Order-domain oracle over authenticated observations from the authority port."""

from __future__ import annotations

from ..models import RuntimeFailure
from .contracts import FrozenContracts
from .effect_oracle import evaluate_order_effect
from .orders import AuthorityReader, AuthoritySnapshot


class OrderEffectVerifier:
    def __init__(self, contracts: FrozenContracts, reader: AuthorityReader):
        contracts.validate()
        self.contracts, self.reader = contracts, reader

    def __call__(self, before: AuthoritySnapshot | None, after: AuthoritySnapshot | None) -> dict:
        try:
            b, a = self.reader.validate(before), self.reader.validate(after)
        except (RuntimeFailure, KeyError, TypeError, ValueError) as failure:
            return {"contract_outcome": "INCONCLUSIVE", "verifier_id": "rpf41-order-effect-verifier",
                    "verifier_version": "1", "violated_rules": [],
                    "evidence_gaps": [getattr(failure, "code", "AUTHORITY_MALFORMED")]}
        result = evaluate_order_effect(self.contracts.effect, self.contracts.experiment["environment_id"], b, a)
        result.update(before=before.public(), after=after.public())
        return result
