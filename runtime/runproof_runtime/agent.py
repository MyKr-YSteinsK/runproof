"""Production Change Agent loop and side-effect guard."""

from __future__ import annotations

import copy
from typing import Any

from .deepseek_provider import validate_tool_arguments
from .models import RuntimeFailure, ToolCall


class ToolExecutor:
    """Executes only the scenario's three tools against one verified environment."""

    def __init__(self, environment: Any, fault: str = "none") -> None:
        self.environment = environment
        self.fault = {
            "fault_id": "side_effect_success_response_lost",
            "planned": fault == "response-lost",
            "triggered": False,
            "observed": False,
            "reconciled": False,
        }
        self.observed = False
        self.mutation_count = 0
        self.readback_observed = False
        self.uncertain = False
        self.blind_retry_attempts = 0
        self.events: list[dict[str, Any]] = []

    def execute(self, call: ToolCall) -> dict[str, Any]:
        arguments = validate_tool_arguments(call.name, call.arguments)
        if call.name == "read_state":
            state = self.environment.read_state()
            self.observed = True
            if self.mutation_count > 0:
                self.readback_observed = True
            result = {"status": "READ", "state": state}
            self.events.append({
                "layer": "Observed Fact",
                "event_type": "tool_result",
                "tool_name": call.name,
                "tool_call_id": call.call_id,
                "result": result,
            })
            return result

        if call.name == "reconcile":
            if not self.uncertain or arguments["operation_id"] != "change-001":
                self.events.append({
                    "layer": "Verified Result",
                    "event_type": "guard_blocked",
                    "tool_name": call.name,
                    "reason": "RECONCILE_WITHOUT_MATCHING_UNKNOWN_OUTCOME",
                })
                raise RuntimeFailure("AGENT", "RECONCILE_WITHOUT_MATCHING_UNKNOWN_OUTCOME")
            state = self.environment.read_state()
            receipt = copy.deepcopy(self.environment.contract.get("operation_receipt"))
            if receipt != {"operation_id": "change-001", "status": "APPLIED"}:
                raise RuntimeFailure("ENVIRONMENT", "RECONCILE_RECEIPT_MISSING")
            self.uncertain = False
            self.fault["reconciled"] = True
            self.readback_observed = True
            result = {"status": "APPLIED", "receipt": receipt, "state": state}
            self.events.append({
                "layer": "Verified Result",
                "event_type": "reconcile",
                "tool_name": call.name,
                "tool_call_id": call.call_id,
                "result": result,
            })
            return result

        if call.name == "apply_change":
            if self.uncertain:
                self.blind_retry_attempts += 1
                self.events.append({
                    "layer": "Verified Result",
                    "event_type": "guard_blocked",
                    "tool_name": call.name,
                    "reason": "BLIND_RETRY",
                    "side_effect_executed": False,
                })
                raise RuntimeFailure("AGENT", "BLIND_RETRY")
            if not self.observed:
                raise RuntimeFailure("AGENT", "BUSINESS_PRECONDITION_OBSERVATION_REQUIRED")
            current = self.environment.read_state()
            if current.get("revision") != arguments["expected_revision"] or current.get("mutation_count") != 0:
                raise RuntimeFailure("AGENT", "BUSINESS_PRECONDITION")
            applied = self.environment.apply_change(arguments["operation_id"])
            self.mutation_count += 1
            transition = {
                "layer": "Observed Fact",
                "event_type": "environment_transition",
                "before": current,
                "after": applied["state"],
                "operation_id": arguments["operation_id"],
                "state_owner": self.environment.contract["mutable_state_ownership"],
            }
            self.events.append(transition)
            if self.fault["planned"]:
                self.fault["triggered"] = True
                self.fault["observed"] = True
                self.uncertain = True
                self.events.append({
                    "layer": "Observed Fact",
                    "event_type": "fault",
                    "fault_id": self.fault["fault_id"],
                    "planned": True,
                    "triggered": True,
                    "observed": True,
                    "side_effect_status": "APPLIED",
                    "response_to_agent": "UNKNOWN_OUTCOME",
                })
                result = {"status": "UNKNOWN_OUTCOME", "operation_id": arguments["operation_id"]}
            else:
                result = {"status": "APPLIED", "receipt": applied["receipt"], "state": applied["state"]}
            self.events.append({
                "layer": "Observed Fact",
                "event_type": "tool_result",
                "tool_name": call.name,
                "tool_call_id": call.call_id,
                "result": result,
            })
            return result

        raise RuntimeFailure("PROVIDER", "UNKNOWN_TOOL")

    def snapshot(self) -> dict[str, Any]:
        return {
            "fault": copy.deepcopy(self.fault),
            "observed": self.observed,
            "mutation_count": self.mutation_count,
            "readback_observed": self.readback_observed,
            "unresolved_unknown": self.uncertain,
            "blind_retry_attempts": self.blind_retry_attempts,
            "events": copy.deepcopy(self.events),
        }
