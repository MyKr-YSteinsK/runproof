"""The narrow cross-Agent integration contract used by RPF-16.

This is deliberately a registry of the two reviewed adapters, not a plugin
system.  It keeps identity, scenario/tool/environment/verifier compatibility,
and execution-profile requirements explicit while leaving the existing
Production Change implementation intact.
"""

from __future__ import annotations

import copy
import os
from typing import Any

from .agent import AGENT_PROFILES, agent_profile
from .models import EVIDENCE_SCHEMA_VERSION, RuntimeFailure


INTEGRATION_CONTRACT_SCHEMA_VERSION = "rpf-agent-integration-contract-v1"
INTEGRATION_CONTRACT_VERSION = "1.0.0"
PRODUCTION_CHANGE_CONTRACT_ID = "production-change-agent-contract"
INCIDENT_REMEDIATION_CONTRACT_ID = "incident-remediation-agent-contract"

INCIDENT_KNOWN_BAD_AGENT_PROFILE = "incident-remediation-agent-v1-known-bad"
INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE = "incident-remediation-agent-v1-fixed"
INCIDENT_KNOWN_BAD_AGENT_VERSION = "1.0.0-known-bad-symptom-driven"
INCIDENT_FIXED_CANDIDATE_AGENT_VERSION = "1.0.1-evidence-supported-remediation"
INCIDENT_AGENT_ID = "incident-remediation-agent"


INCIDENT_AGENT_PROFILES: dict[str, dict[str, str]] = {
    INCIDENT_KNOWN_BAD_AGENT_PROFILE: {
        "agent_id": INCIDENT_AGENT_ID,
        "agent_version": INCIDENT_KNOWN_BAD_AGENT_VERSION,
        "mode": "known-bad-deterministic-policy",
        "prompt_id": "incident-remediation-agent-system-known-bad-symptom-driven-v1",
        "configuration_id": INCIDENT_KNOWN_BAD_AGENT_PROFILE,
        "defect_id": "incident-symptom-driven-remediation-v1",
        "defect_description": "Remediates on a service symptom without disambiguating dependency health.",
    },
    INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE: {
        "agent_id": INCIDENT_AGENT_ID,
        "agent_version": INCIDENT_FIXED_CANDIDATE_AGENT_VERSION,
        "mode": "deterministic-repaired-policy",
        "prompt_id": "incident-remediation-agent-system-evidence-supported-v1",
        "configuration_id": INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE,
        "fix_id": "incident-evidence-supported-remediation-v1",
        "fix_description": "Inspects dependency and change evidence before a bounded local remediation.",
    },
}


def _contract(
    *,
    contract_id: str,
    agent_id: str,
    agent_domain: str,
    agent_type: str,
    scenario_id: str,
    scenario_version: str,
    tool_contract_id: str,
    environment_contract_id: str,
    verifier_id: str,
    verifier_version: str,
    supported_profiles: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": INTEGRATION_CONTRACT_SCHEMA_VERSION,
        "contract_id": contract_id,
        "contract_version": INTEGRATION_CONTRACT_VERSION,
        "contract_identity": f"{contract_id}@{INTEGRATION_CONTRACT_VERSION}",
        "agent_id": agent_id,
        "agent_domain": agent_domain,
        "agent_type": agent_type,
        "scenario_ref": {
            "kind": "Scenario",
            "scenario_id": scenario_id,
            "scenario_version": scenario_version,
        },
        "tool_contract_ref": {
            "kind": "Tool Contract",
            "contract_id": tool_contract_id,
            "contract_version": "1.0.0",
        },
        "environment_contract_ref": {
            "kind": "Environment Contract",
            "contract_id": environment_contract_id,
            "contract_version": "1.0.0",
        },
        "verifier_ref": {
            "kind": "Verifier",
            "verifier_id": verifier_id,
            "verifier_version": verifier_version,
        },
        "supported_execution_profile": "local-sequential-fresh-per-member",
        "evidence_schema_compatibility": [EVIDENCE_SCHEMA_VERSION],
        "supported_profiles": list(supported_profiles),
        "dynamic_loading": False,
    }


AGENT_CONTRACTS: dict[str, dict[str, Any]] = {
    PRODUCTION_CHANGE_CONTRACT_ID: _contract(
        contract_id=PRODUCTION_CHANGE_CONTRACT_ID,
        agent_id="production-change-agent",
        agent_domain="Production Change Agent",
        agent_type="STATEFUL_CHANGE",
        scenario_id="production-change-release",
        scenario_version="1.0.0",
        tool_contract_id="production-change-tools",
        environment_contract_id="docker-controlled-release-simulation",
        verifier_id="rpf-deterministic-state-verifier",
        verifier_version="1.0.0",
        supported_profiles=list(AGENT_PROFILES),
    ),
    INCIDENT_REMEDIATION_CONTRACT_ID: _contract(
        contract_id=INCIDENT_REMEDIATION_CONTRACT_ID,
        agent_id=INCIDENT_AGENT_ID,
        agent_domain="Incident Remediation Agent",
        agent_type="INCIDENT_REMEDIATION",
        scenario_id="incident-remediation",
        scenario_version="1.0.0",
        tool_contract_id="incident-remediation-tools",
        environment_contract_id="controlled-incident-simulation",
        verifier_id="rpf-incident-remediation-verifier",
        verifier_version="1.0.0",
        supported_profiles=list(INCIDENT_AGENT_PROFILES),
    ),
}

PROFILE_TO_CONTRACT: dict[str, str] = {
    **{profile_id: PRODUCTION_CHANGE_CONTRACT_ID for profile_id in AGENT_PROFILES},
    **{profile_id: INCIDENT_REMEDIATION_CONTRACT_ID for profile_id in INCIDENT_AGENT_PROFILES},
}


def agent_contract_for_profile(profile_id: str) -> dict[str, Any]:
    contract_id = PROFILE_TO_CONTRACT.get(profile_id)
    if contract_id is None:
        raise RuntimeFailure("HARNESS", "UNKNOWN_AGENT_PROFILE")
    return copy.deepcopy(AGENT_CONTRACTS[contract_id])


def agent_profile_for(profile_id: str) -> dict[str, Any]:
    if profile_id in AGENT_PROFILES:
        profile = agent_profile(profile_id)
    elif profile_id in INCIDENT_AGENT_PROFILES:
        profile = dict(INCIDENT_AGENT_PROFILES[profile_id])
    else:
        raise RuntimeFailure("HARNESS", "UNKNOWN_AGENT_PROFILE")
    contract = agent_contract_for_profile(profile_id)
    profile.update(
        {
            "agent_domain": contract["agent_domain"],
            "agent_type": contract["agent_type"],
            "agent_contract_id": contract["contract_id"],
            "agent_contract_version": contract["contract_version"],
        }
    )
    return profile


def contract_for_agent(agent_id: str, agent_domain: str | None = None) -> dict[str, Any]:
    for contract in AGENT_CONTRACTS.values():
        if contract["agent_id"] == agent_id and (agent_domain is None or contract["agent_domain"] == agent_domain):
            return copy.deepcopy(contract)
    raise RuntimeFailure("HARNESS", "UNKNOWN_AGENT_CONTRACT")


def fixed_profile_for(profile_id: str) -> str:
    contract = agent_contract_for_profile(profile_id)
    if contract["contract_id"] == PRODUCTION_CHANGE_CONTRACT_ID:
        from .agent import FIXED_CANDIDATE_AGENT_PROFILE

        return FIXED_CANDIDATE_AGENT_PROFILE
    return INCIDENT_FIXED_CANDIDATE_AGENT_PROFILE


def known_bad_profile_for(profile_id: str) -> str:
    contract = agent_contract_for_profile(profile_id)
    if contract["contract_id"] == PRODUCTION_CHANGE_CONTRACT_ID:
        from .agent import KNOWN_BAD_AGENT_PROFILE

        return KNOWN_BAD_AGENT_PROFILE
    return INCIDENT_KNOWN_BAD_AGENT_PROFILE


def run_agent_slice(
    profile_id: str,
    *,
    fault_profile: str = "none",
    api_key: str | None = None,
    model: str | None = None,
    scenario_case_id: str | None = None,
    environment_failure: str | None = None,
) -> dict[str, Any]:
    """Execute one of the explicitly registered Agent adapters."""

    contract = agent_contract_for_profile(profile_id)
    if contract["contract_id"] == INCIDENT_REMEDIATION_CONTRACT_ID:
        from .incident import run_incident_slice

        return run_incident_slice(
            scenario_case_id or "local-recoverable",
            fault_profile=fault_profile,
            agent_profile_id=profile_id,
        )
    from .runner import run_slice

    return run_slice(
        fault_profile=fault_profile,
        api_key=api_key,
        model=model,
        agent_profile_id=profile_id,
        environment_failure=environment_failure,
    )


def regression_contract_for_case(case: dict[str, Any]) -> dict[str, Any] | None:
    agent = case.get("agent") if isinstance(case.get("agent"), dict) else {}
    if agent.get("agent_id") != INCIDENT_AGENT_ID:
        return None
    from .incident import build_incident_regression_contract

    return build_incident_regression_contract(case)


def validate_integration_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != INTEGRATION_CONTRACT_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION")
    for key in ("contract_id", "contract_version", "contract_identity", "agent_id", "agent_domain", "agent_type", "scenario_ref", "tool_contract_ref", "environment_contract_ref", "verifier_ref", "supported_execution_profile", "evidence_schema_compatibility", "supported_profiles"):
        if not contract.get(key):
            errors.append(f"MISSING_{key.upper()}")
    if contract.get("contract_identity") != f"{contract.get('contract_id')}@{contract.get('contract_version')}":
        errors.append("CONTRACT_IDENTITY")
    if contract.get("dynamic_loading") is not False:
        errors.append("DYNAMIC_LOADING_FORBIDDEN")
    return errors


def contract_document() -> dict[str, Any]:
    return {
        "schema_version": INTEGRATION_CONTRACT_SCHEMA_VERSION,
        "contract_type": "NARROW_CROSS_AGENT_RELIABILITY_CONTRACT",
        "registry_policy": "explicit-reviewed-adapters-only",
        "agents": [copy.deepcopy(contract) for contract in AGENT_CONTRACTS.values()],
        "no_dynamic_loading": True,
        "no_plugin_or_marketplace_boundary": True,
        "evidence_schema": EVIDENCE_SCHEMA_VERSION,
        "runtime_version": os.environ.get("RPF_RUNTIME_VERSION", "rpf-08.v1"),
    }
