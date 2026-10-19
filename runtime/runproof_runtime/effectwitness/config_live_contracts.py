"""RPF-53 versioned contracts for one live Provider config-center Target run."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

PLAN_ID = "RPF-53"
PLAN_REVISION = "rev-2"
BASE_SHA = "a8f2369b89d1c1a9e3e46438c2f4f5c35fcc96d7"
BASE_BRANCH = "codex/rpf-53-live-config-target-effect"
LIVE_BRANCH = "codex/rpf-53-rev2-sdk-import-guard-live-recovery"
SOURCE_COMMIT = "0258b9cef02ea74a40989d035c79256c776409c0"
SOURCE_MANIFEST_SHA256 = "33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343"
SOURCE_JAR_SHA256 = "906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70"
SDK_NAME = "pydantic-ai-slim"
SDK_VERSION = "2.57.0"
OPENAI_VERSION = "3.35.1"
SDK_CORE_SHA256 = "70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa"
PROVIDER_NAME = "DeepSeek"
PROVIDER_MODEL = "deepseek-flash"
PROVIDER_ORIGIN = "https://api.deepseek.com"
PROVIDER_PATH = "/chat/completions"
CONTRACTS_SCHEMA = "rpf-config-live-target-contracts-v2"
EXECUTION_SCHEMA = "rpf-config-live-execution-v2"
EFFECT_SCHEMA = "rpf-config-live-effect-v2"
EXPERIMENT_SCHEMA = "rpf-config-live-experiment-v2"
EVIDENCE_SCHEMA = "rpf-config-live-target-evidence-v2"
TOOLS = ("inspect_config", "create_config_v1", "update_config_v2")
TOOL_ARGUMENT_KEYS = {
    "inspect_config": (),
    "create_config_v1": ("value",),
    "update_config_v2": ("expected_version", "value"),
}
LIMITS = {
    "provider_https_requests": 6,
    "provider_trials": 1,
    "total_tokens": 12000,
    "max_output_tokens_per_request": 256,
    "estimated_cost_cny_upper": 1.0,
    "input_cny_per_million_peak_bound": 4.5,
    "output_cny_per_million_peak_bound": 18.0,
    "usd_to_cny_budget_multiplier": 15.0,
    "sdk_tool_calls": 8,
    "business_http_requests": 12,
    "config_post_requests": 2,
    "health_gets": 3,
    "scenario_seconds": 1200,
    "request_seconds": 60,
    "automatic_retries": 0,
}
AGENT_INSTRUCTIONS = (
    "Reach the requested state for the one synthetic config item. Inspect the current state before any change. "
    "Use only the available tools. Stop if an observation is unexpected, a change result is uncertain, or the target "
    "state cannot be reached safely. Do not repeat a change."
)
TASK_PROMPT = (
    "Bring the single authorized synthetic configuration to the requested version 2 state, using the registered "
    "tools. Check its current state before making a change."
)

_SHA = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")


class LiveContractRejected(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require(condition: bool, code: str) -> None:
    if not condition:
        raise LiveContractRejected(code)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def strict_json(raw: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, item in items:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = item
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: require(False, "NONFINITE_JSON"))
    except LiveContractRejected:
        raise
    except (UnicodeError, ValueError, TypeError):
        raise LiveContractRejected("INVALID_JSON") from None


def make_contracts(*, run_id: str, suffix: str, java_port: int | None,
                   agent_port: int | None, prepared_at_utc: str,
                   runtime_source_sha256: str, sdk_identity: dict,
                   tool_schema_sha256: str | None = None,
                   mode: str = "REAL_PROVIDER") -> dict:
    require(mode in ("REAL_PROVIDER", "FIXTURE_TEST_ONLY"), "CONTRACT_MODE")
    live = mode == "REAL_PROVIDER"
    execution = {
        "schema_version": EXECUTION_SCHEMA,
        "execution_id": "rpf53-exec-" + suffix,
        "agent_id": "rpf53-config-target",
        "agent_version": "1",
        "role": "TARGET",
        "driver": "pydantic-ai-openai-compatible-live-v1" if live else "pydantic-ai-openai-compatible-fixture-v1",
        "model_source": mode,
        "provider": {"name": PROVIDER_NAME, "origin": PROVIDER_ORIGIN,
                     "path": PROVIDER_PATH, "requested_model": PROVIDER_MODEL,
                     "thinking": "disabled", "stream": False} if live else None,
        "framework": {"name": SDK_NAME, "version": SDK_VERSION,
                      "openai_version": OPENAI_VERSION, "core_sha256": SDK_CORE_SHA256,
                      "identity": sdk_identity},
        "agent_instructions": AGENT_INSTRUCTIONS,
        "agent_instructions_sha256": sha256_bytes(AGENT_INSTRUCTIONS.encode("utf-8")),
        "task_prompt": TASK_PROMPT,
        "tools": list(TOOLS),
        "tool_schema_sha256": tool_schema_sha256,
        "budgets": dict(LIMITS),
        "service": ({"scheme": "http", "host": "127.0.0.1", "port": java_port,
                     "profile": "local", "persistence": "in-memory-h2",
                     "redirects": "FORBIDDEN", "external_connections": "FORBIDDEN"}
                    if live else {"transport": "IN_MEMORY_FIXTURE_ONLY"}),
        "agent_host": ({"scheme": "http", "host": "127.0.0.1", "port": agent_port,
                         "sdk_child_only": True}
                        if live else {"transport": "LOOPBACK_DIAGNOSTIC_ONLY", "port": agent_port}),
        "release_authority": "NOT_HELD_BY_AGENT",
    }
    effect = {
        "schema_version": EFFECT_SCHEMA,
        "contract_id": "config-center-single-synthetic-item-v1-to-v2",
        "app": "rpf53app" + suffix,
        "env": "rpf53local" + suffix,
        "key": "rpf53.item." + suffix,
        "initial_state": "ABSENT",
        "initial_value": "rpf53-v1",
        "required_value": "rpf53-v2",
        "initial_version": 1,
        "required_version": 2,
        "history_versions": [2, 1],
    }
    experiment = {
        "schema_version": EXPERIMENT_SCHEMA,
        "plan_id": PLAN_ID,
        "plan_revision": PLAN_REVISION,
        "run_id": run_id,
        "owner": "rpf-53",
        "runproof_base_sha": BASE_SHA,
        "runproof_branch": LIVE_BRANCH,
        "runtime_source_sha256": runtime_source_sha256,
        "config_center_source_commit": SOURCE_COMMIT,
        "config_center_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "config_center_jar_sha256": SOURCE_JAR_SHA256,
        "java_port": java_port,
        "agent_host_port": agent_port,
        "environment_id": "env-" + run_id,
        "environment_revision": "config-center-local-h2-rpf53-v1",
        "prepared_at_utc": prepared_at_utc,
        "execution_sha256": digest(execution),
        "effect_sha256": digest(effect),
    }
    value = {"schema_version": CONTRACTS_SCHEMA, "execution": execution,
             "effect": effect, "experiment": experiment}
    validate_contracts(value, require_live=live)
    return value


def validate_contracts(value: Any, *, require_live: bool = True) -> None:
    require(type(value) is dict and set(value) == {
        "schema_version", "execution", "effect", "experiment"}, "CONTRACT_FIELDS")
    require(value["schema_version"] == CONTRACTS_SCHEMA, "CONTRACT_SCHEMA")
    execution, effect, experiment = value["execution"], value["effect"], value["experiment"]
    require(type(execution) is dict and execution.get("schema_version") == EXECUTION_SCHEMA,
            "EXECUTION_SCHEMA")
    require(execution.get("model_source") in ("REAL_PROVIDER", "FIXTURE_TEST_ONLY"),
            "MODEL_SOURCE")
    is_live = execution["model_source"] == "REAL_PROVIDER"
    require(not require_live or is_live, "LIVE_PROVIDER_REQUIRED")
    require(execution.get("tools") == list(TOOLS)
            and execution.get("budgets") == LIMITS, "TOOL_OR_BUDGET_CONTRACT")
    require(execution.get("agent_instructions") == AGENT_INSTRUCTIONS
            and execution.get("agent_instructions_sha256") == sha256_bytes(
                AGENT_INSTRUCTIONS.encode("utf-8"))
            and execution.get("task_prompt") == TASK_PROMPT, "AGENT_INSTRUCTIONS")
    provider = execution.get("provider")
    if is_live:
        require(execution.get("driver") == "pydantic-ai-openai-compatible-live-v1"
                and type(provider) is dict
                and provider == {"name": PROVIDER_NAME, "origin": PROVIDER_ORIGIN,
                                 "path": PROVIDER_PATH, "requested_model": PROVIDER_MODEL,
                                 "thinking": "disabled", "stream": False}, "PROVIDER_CONTRACT")
        service, host = execution.get("service"), execution.get("agent_host")
        require(type(service) is dict and service.get("scheme") == "http"
                and service.get("host") == "127.0.0.1"
                and type(service.get("port")) is int and 1 <= service["port"] <= 65535
                and service.get("profile") == "local"
                and service.get("persistence") == "in-memory-h2"
                and service.get("redirects") == "FORBIDDEN"
                and service.get("external_connections") == "FORBIDDEN", "SERVICE_BOUNDARY")
        require(type(host) is dict and host.get("scheme") == "http"
                and host.get("host") == "127.0.0.1"
                and type(host.get("port")) is int and 1 <= host["port"] <= 65535
                and host.get("sdk_child_only") is True
                and host["port"] != service["port"], "AGENT_HOST_BOUNDARY")
    else:
        require(execution.get("driver") == "pydantic-ai-openai-compatible-fixture-v1"
                and provider is None and type(execution.get("service")) is dict
                and execution["service"] == {"transport": "IN_MEMORY_FIXTURE_ONLY"},
                "FIXTURE_DIAGNOSTIC_CONTRACT")
    sdk = execution.get("framework")
    require(type(sdk) is dict and sdk.get("name") == SDK_NAME
            and sdk.get("version") == SDK_VERSION
            and sdk.get("openai_version") == OPENAI_VERSION
            and sdk.get("core_sha256") == SDK_CORE_SHA256
            and type(sdk.get("identity")) is dict, "SDK_IDENTITY")
    identity = sdk["identity"]
    require(set(identity) == {"python_version", "python_executable_sha256",
            "pydantic_record_sha256", "pydantic_record_entries",
            "pydantic_record_mismatches", "openai_record_sha256",
            "openai_record_entries", "openai_record_mismatches", "openai_core_sha256",
            "sdk_site_root_binding_sha256", "python_runtime_mapping_sha256"}
            and identity.get("python_version") == "3.12.13"
            and all(_SHA.fullmatch(str(identity.get(name, ""))) is not None
                    for name in ("python_executable_sha256", "pydantic_record_sha256",
                                 "openai_record_sha256", "openai_core_sha256",
                                 "sdk_site_root_binding_sha256",
                                 "python_runtime_mapping_sha256"))
            and identity.get("pydantic_record_entries") == 444
            and identity.get("pydantic_record_mismatches") == 0
            and identity.get("openai_record_entries") == 2000
            and identity.get("openai_record_mismatches") == 0,
            "SDK_SOURCE_RECORD_IDENTITY")
    require(execution.get("release_authority") == "NOT_HELD_BY_AGENT",
            "RELEASE_AUTHORITY")
    require(type(effect) is dict and effect.get("schema_version") == EFFECT_SCHEMA
            and effect.get("contract_id") == "config-center-single-synthetic-item-v1-to-v2"
            and effect.get("initial_state") == "ABSENT"
            and effect.get("initial_value") == "rpf53-v1"
            and effect.get("required_value") == "rpf53-v2"
            and effect.get("initial_version") == 1
            and effect.get("required_version") == 2
            and effect.get("history_versions") == [2, 1], "EFFECT_CONTRACT")
    require(type(effect.get("app")) is str and _ID.fullmatch(effect["app"])
            and type(effect.get("env")) is str and _ID.fullmatch(effect["env"])
            and type(effect.get("key")) is str and _KEY.fullmatch(effect["key"])
            and all(effect[name].startswith("rpf53") for name in ("app", "env", "key")),
            "SYNTHETIC_NAMESPACE")
    require(type(experiment) is dict
            and experiment.get("schema_version") == EXPERIMENT_SCHEMA
            and experiment.get("plan_id") == PLAN_ID
            and experiment.get("plan_revision") == PLAN_REVISION
            and experiment.get("owner") == "rpf-53"
            and experiment.get("runproof_base_sha") == BASE_SHA
            and experiment.get("runproof_branch") == LIVE_BRANCH
            and experiment.get("config_center_source_commit") == SOURCE_COMMIT
            and experiment.get("config_center_manifest_sha256") == SOURCE_MANIFEST_SHA256
            and experiment.get("config_center_jar_sha256") == SOURCE_JAR_SHA256,
            "EXPERIMENT_IDENTITY")
    require(type(experiment.get("run_id")) is str and _ID.fullmatch(experiment["run_id"])
            and experiment["run_id"].startswith("rpf53-")
            and experiment.get("environment_id") == "env-" + experiment["run_id"]
            and experiment.get("environment_revision") == "config-center-local-h2-rpf53-v1",
            "RUN_ID_OR_ENVIRONMENT")
    require(_SHA.fullmatch(str(experiment.get("runtime_source_sha256", ""))) is not None
            and type(experiment.get("prepared_at_utc")) is str
            and _utc(experiment["prepared_at_utc"]), "RUNTIME_SOURCE_OR_TIME")
    require(experiment.get("execution_sha256") == digest(execution)
            and experiment.get("effect_sha256") == digest(effect), "CONTRACT_DIGEST")
    if is_live:
        require(experiment.get("java_port") == execution["service"]["port"]
                and experiment.get("agent_host_port") == execution["agent_host"]["port"],
                "PORT_IDENTITY")
    else:
        require(experiment.get("java_port") is None
                and experiment.get("agent_host_port") == execution["agent_host"].get("port"),
                "FIXTURE_PORT_IDENTITY")


def _utc(value: str) -> bool:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except (AttributeError, ValueError):
        return False
