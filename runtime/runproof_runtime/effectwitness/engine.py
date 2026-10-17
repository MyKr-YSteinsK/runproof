"""Bounded orchestration ports; no provider, business oracle or release authority."""

from __future__ import annotations

import time
from typing import Callable, Protocol, Any

from ..models import RuntimeFailure
from .contracts import FrozenContracts, require


class DomainPort(Protocol):
    def invoke(self, name: str, arguments: dict) -> dict: ...
    def tool_definitions(self) -> list[dict]: ...


class AuthorityPort(Protocol):
    def read(self) -> Any: ...
    def validate(self, snapshot: Any) -> dict: ...
    def reconcile(self, operation_id: str) -> dict: ...


class Budget:
    """Reservations precede I/O. Unknown usage closes the request gate."""
    def __init__(self, limits: dict, clock: Callable[[], float] = time.monotonic):
        self.limits, self.clock, self.started = dict(limits), clock, clock()
        self.requests = self.steps = self.tokens = self.input_tokens = self.output_tokens = 0
        self.reserved = 0
        self.fault_trials = 0
        self.usage_known = True
        self.cost_cny = 0.0

    def check_time(self) -> None:
        require(self.clock() - self.started < self.limits["seconds"], "BUDGET_TIME_EXHAUSTED")

    def step(self) -> None:
        self.check_time()
        require(self.steps < self.limits["steps"], "BUDGET_STEPS_EXHAUSTED")
        self.steps += 1

    def fault_trial(self) -> None:
        self.check_time()
        require(self.fault_trials < self.limits["fault_trials"], "BUDGET_FAULT_TRIALS_EXHAUSTED")
        self.fault_trials += 1

    def reserve_request(self, input_ceiling: int, output_ceiling: int) -> None:
        self.check_time()
        require(self.usage_known and self.reserved == 0, "PROVIDER_USAGE_UNKNOWN", "PROVIDER")
        require(self.requests < self.limits["provider_requests"], "BUDGET_REQUESTS_EXHAUSTED")
        require(self.tokens + input_ceiling + output_ceiling <= self.limits["tokens"],
                "BUDGET_TOKENS_EXHAUSTED")
        # Conservative peak tariff: all input at cache-miss; USD->CNY ceiling 10.
        reserve_cost = (input_ceiling * 0.30 + output_ceiling * 1.20) / 1_000_000 * 10
        require(self.cost_cny + reserve_cost <= self.limits["cost_cny"], "BUDGET_COST_EXHAUSTED")
        self.step()
        self.requests += 1
        self.reserved = input_ceiling + output_ceiling
        self.usage_known = False

    def record_usage(self, usage: dict) -> None:
        require(type(usage) is dict, "PROVIDER_USAGE_MISSING", "PROVIDER")
        values = [usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")]
        require(all(type(v) is int and v >= 0 for v in values)
                and values[0] + values[1] == values[2], "PROVIDER_USAGE_INVALID", "PROVIDER")
        self.input_tokens += values[0]
        self.output_tokens += values[1]
        self.tokens += values[2]
        self.cost_cny = (self.input_tokens * 0.30 + self.output_tokens * 1.20) / 1_000_000 * 10
        ceiling = self.reserved
        self.reserved = 0
        self.usage_known = True
        require(values[2] <= ceiling and self.tokens <= self.limits["tokens"]
                and self.cost_cny <= self.limits["cost_cny"], "PROVIDER_USAGE_OVER_RESERVATION", "PROVIDER")

    def public(self) -> dict:
        return {"provider_requests": self.requests, "steps": self.steps,
                "tokens": self.tokens if self.usage_known else None, "confirmed_tokens": self.tokens,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "estimated_cost_cny_upper": round(self.cost_cny, 8) if self.usage_known else None,
                "usage_known": self.usage_known, "fault_trials": self.fault_trials,
                "pending_token_reservation": self.reserved,
                "elapsed_seconds": round(self.clock() - self.started, 3), "automatic_retries": 0}


class Orchestrator:
    def __init__(self, contracts: FrozenContracts, domain: DomainPort, authority: AuthorityPort,
                 budget: Budget):
        contracts.validate()
        self.contracts, self.domain, self.authority, self.budget = contracts, domain, authority, budget
        require(budget.limits == contracts.execution["budgets"], "BUDGET_CONTRACT_MISMATCH")
        if contracts.experiment["fault"] != "none":
            budget.fault_trial()
        self.before = authority.read()
        authority.validate(self.before)
        self.pending: str | None = None
        self.calls: list[dict] = []
        self.reconciled = False

    def dispatch(self, name: str, arguments: dict) -> dict:
        require(self.pending is None, "RECONCILE_REQUIRED_BEFORE_TOOL", "ENVIRONMENT")
        require(name in self.contracts.execution["tools"], "TOOL_NOT_ALLOWLISTED", "AGENT")
        self.budget.step()
        result = self.domain.invoke(name, arguments)
        self.calls.append({"name": name, "arguments": dict(arguments), "result": dict(result)})
        if result.get("status") == "UNKNOWN_OUTCOME":
            self.pending = self.contracts.effect["operation_id"]
        return result

    def reconcile(self) -> dict:
        require(self.pending is not None, "NO_PENDING_OPERATION")
        receipt = self.authority.reconcile(self.pending)
        self.pending = None
        self.reconciled = True
        return {"status": "RECONCILED_COMMITTED", "receipt_id": receipt["receipt_id"],
                "operation_id": receipt["operation_id"]}

    def effect_result(self, verifier: Callable) -> dict:
        if self.pending is not None:
            return {"contract_outcome": "INCONCLUSIVE", "violated_rules": [],
                    "evidence_gaps": ["UNRESOLVED_UNKNOWN_OUTCOME"]}
        try:
            after = self.authority.read()
        except RuntimeFailure as failure:
            return {"contract_outcome": "INCONCLUSIVE", "violated_rules": [],
                    "evidence_gaps": [failure.code]}
        return verifier(self.before, after)
