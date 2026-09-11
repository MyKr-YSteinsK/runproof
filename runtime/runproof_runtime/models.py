"""Small, explicit contracts shared by the RPF-03 runtime modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


OUTCOMES = {"PASS", "FAIL", "ERROR", "INVALID", "INCONCLUSIVE", "CANCELLED"}
INITIAL_STATE = {
    "release": "release-v1",
    "revision": 0,
    "mutation_count": 0,
    "operation_id": None,
}
TARGET_STATE = {
    "release": "release-v2",
    "revision": 1,
    "mutation_count": 1,
    "operation_id": "change-001",
}


class RuntimeFailure(Exception):
    """A classified failure that can be represented without raw exception text."""

    def __init__(self, domain: str, code: str, outcome: str | None = None) -> None:
        self.domain = domain
        self.code = code
        self.outcome = outcome or {
            "AGENT": "FAIL",
            "PROVIDER": "ERROR",
            "ENVIRONMENT": "ERROR",
            "HARNESS": "INVALID",
        }.get(domain, "ERROR")
        super().__init__(code)


def failure_record(error: RuntimeFailure) -> dict[str, Any]:
    return {
        "domain": error.domain,
        "code": error.code,
        "outcome": error.outcome,
    }


def state_diff(expected: dict[str, Any] | None, actual: dict[str, Any] | None) -> list[dict[str, Any]]:
    expected = expected or {}
    actual = actual or {}
    return [
        {
            "path": key,
            "before": expected.get(key),
            "after": actual.get(key),
            "changed": expected.get(key) != actual.get(key),
        }
        for key in sorted(set(expected) | set(actual))
    ]


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]
