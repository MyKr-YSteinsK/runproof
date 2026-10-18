"""RPF-50's bounded local SQLite control and pre-registered defect service."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .contracts import ROOT, owned_path, require
from .effect_oracle import digest, evaluate_order_effect
from .orders import AuthorityReader, OrderSandbox
from .target_contracts import TargetContracts
from .violation_witness import (DEFECT_PROFILE, SOURCE_FILES, SOURCE_LEVEL, WitnessRejected,
                                issue, canonical)

TASK = "rpf-50"
NORMAL_PROFILE = "NORMAL_CONTROL_ORDER_SANDBOX_V1"
REFERENCE_BUDGETS = {"provider_requests": 1, "tokens": 1, "cost_cny": 0.000001,
                     "steps": 8, "seconds": 300, "request_seconds": 60, "fault_trials": 1}
TASK_ROOT = ROOT / ".local" / TASK
PREFLIGHT_PATH = TASK_ROOT / "preflight.json"
STARTED_PATH = TASK_ROOT / "pair-started.json"
PAIR_STATE_PATH = TASK_ROOT / "pair-state.json"
SPIKE_ROOT = ROOT / "spikes" / TASK
CONTROL_ARTIFACT = SPIKE_ROOT / "control-summary.json"
WITNESS_ARTIFACT = SPIKE_ROOT / "violation-witness.json"


class LabStopped(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _strict_object(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: require(False, "NONFINITE_JSON"))
    except Exception as error:
        if getattr(error, "code", None):
            raise
        raise LabStopped("PREFLIGHT_JSON_INVALID") from None
    require(type(value) is dict, "PREFLIGHT_OBJECT_REQUIRED")
    return value


def _write_exclusive(path: Path, raw: bytes, *, task_local: bool) -> None:
    if task_local:
        checked = owned_path(path, task=TASK)
    else:
        checked = path.resolve()
        require(path in (CONTROL_ARTIFACT, WITNESS_ARTIFACT)
                and checked.parent == SPIKE_ROOT.resolve(), "SPIKE_OUTPUT_PATH_REJECTED")
    require(not checked.exists(), "OUTPUT_ALREADY_EXISTS")
    checked.parent.mkdir(parents=True, exist_ok=True)
    with checked.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _write_state(path: Path, value: dict) -> None:
    path = owned_path(path, task=TASK)
    temp = path.with_name(path.name + ".write-" + uuid.uuid4().hex)
    with temp.open("xb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def _source_hashes() -> dict[str, str]:
    hashes = {}
    for relative in SOURCE_FILES:
        path = ROOT / relative
        require(path.is_file() and not path.is_symlink(), "SOURCE_FILE_UNAVAILABLE")
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _make_trial(profile_id: str, run_id: str, frozen_at: str) -> dict:
    require(profile_id in (NORMAL_PROFILE, DEFECT_PROFILE), "SERVICE_PROFILE_REJECTED")
    contracts = TargetContracts.create(run_id, driver="deterministic-reference", fault="none",
                                       budgets=REFERENCE_BUDGETS)
    return {"profile_id": profile_id, "registered_before_run": True,
            "profile_frozen_at": frozen_at, "storage_task": TASK,
            "contracts": contracts.document(), "contract_hashes": contracts.hashes,
            "run_directory": f".local/{TASK}/runs/{run_id}"}


def _unique_run_id(prefix: str) -> str:
    return prefix + "-" + uuid.uuid4().hex


def prepare_pair() -> dict:
    root = TASK_ROOT
    owned_path(PREFLIGHT_PATH, task=TASK)
    root.mkdir(parents=True, exist_ok=True)
    require(not PREFLIGHT_PATH.exists() and not STARTED_PATH.exists() and not PAIR_STATE_PATH.exists(),
            "RPF50_PAIR_ALREADY_PREPARED_OR_STARTED")
    require(not CONTROL_ARTIFACT.exists() and not WITNESS_ARTIFACT.exists(), "SPIKE_ARTIFACT_ALREADY_EXISTS")
    runs_root = root / "runs"
    if runs_root.exists():
        require(not any(runs_root.iterdir()), "PREEXISTING_RPF50_RUN_DATA")
    else:
        runs_root.mkdir()
    observations = root / "observations"
    if observations.exists():
        require(not any(observations.iterdir()), "PREEXISTING_RPF50_OBSERVATIONS")
    else:
        observations.mkdir()
    source_hashes = _source_hashes()
    frozen_at = _utc_now()
    control_id, defect_id = _unique_run_id("rpf50-control"), _unique_run_id("rpf50-defect")
    control = _make_trial(NORMAL_PROFILE, control_id, frozen_at)
    defect = _make_trial(DEFECT_PROFILE, defect_id, frozen_at)
    c = TargetContracts.from_document(control["contracts"])
    d = TargetContracts.from_document(defect["contracts"])
    semantic_keys = ("amount_minor", "currency", "initial_status", "required_status",
                     "verifier_id", "verifier_version")
    require({k: c.effect[k] for k in semantic_keys} == {k: d.effect[k] for k in semantic_keys},
            "CONTROL_DEFECT_EFFECT_SEMANTICS_DIFFER")
    require(len({c.experiment["run_id"], d.experiment["run_id"]}) == 2
            and len({c.experiment["environment_id"], d.experiment["environment_id"]}) == 2
            and len({c.effect["order_id"], d.effect["order_id"]}) == 2
            and len({c.effect["operation_id"], d.effect["operation_id"]}) == 2,
            "CONTROL_DEFECT_IDENTITIES_NOT_DISTINCT")
    for item in (control, defect):
        run_dir = ROOT / item["run_directory"]
        require(not run_dir.exists(), "RUN_DIRECTORY_ALREADY_EXISTS")
    plan = {"schema_version": "rpf50-pair-preflight-v1", "prepared_at_utc": frozen_at,
            "source_level": SOURCE_LEVEL, "source_sha256": source_hashes,
            "provider_http_calls": 0, "llm_tokens": 0, "provider_cost_cny": 0.0,
            "non_test_trial_limit": 2, "business_step_limit": 20,
            "trials": [control, defect]}
    _write_exclusive(PREFLIGHT_PATH, canonical(plan), task_local=True)
    return plan


def _event(run_id: str, seq: int, event_type: str, facts: dict, observed_at: str | None = None) -> dict:
    return {"seq": seq, "event_id": f"event-{run_id}-{seq:02d}",
            "observed_at": observed_at or _utc_now(), "type": event_type,
            "facts": facts, "facts_sha256": digest(facts)}


def _commit_known_half_refund(sandbox: OrderSandbox) -> dict:
    """One fixed defect transaction; never calls or edits OrderSandbox.refund."""
    effect = sandbox.contracts.effect
    require(sandbox.created and sandbox.generation == 0 and sandbox.path.is_file(), "DEFECT_SANDBOX_STATE")
    with closing(sqlite3.connect(sandbox.path, timeout=5)) as db:
        db.execute("BEGIN IMMEDIATE")
        sandbox._check_owner(db)
        order = db.execute("SELECT paid_minor,refunded_minor,currency,status,revision FROM orders "
                           "WHERE order_id=?", (effect["order_id"],)).fetchone()
        receipt_count = db.execute("SELECT count(*) FROM refunds").fetchone()[0]
        require(order == (2500, 0, "CNY", "PAID", 0) and receipt_count == 0,
                "DEFECT_INITIAL_STATE_MISMATCH", "ENVIRONMENT")
        receipt_id = "receipt-" + digest({"environment": sandbox.contracts.experiment["environment_id"],
                                          "operation_id": effect["operation_id"]})[:24]
        db.execute("INSERT INTO refunds VALUES(?,?,?,?,?,'COMMITTED',1)",
                   (effect["operation_id"], effect["order_id"], 2500, "CNY", receipt_id))
        db.execute("UPDATE orders SET refunded_minor=1250,status='REFUNDED',revision=1 WHERE order_id=?",
                   (effect["order_id"],))
        db.commit()
    return {"status": "COMMITTED", "operation_id": effect["operation_id"],
            "receipt_id": receipt_id, "committed_revision": 1,
            "profile_id": DEFECT_PROFILE}


def execute_trial(plan: dict, *, progress_callback: Callable[[dict], None] | None = None) -> dict:
    require(type(plan) is dict and plan.get("storage_task") == TASK
            and plan.get("profile_id") in (NORMAL_PROFILE, DEFECT_PROFILE), "TRIAL_PLAN_INVALID")
    source_hashes = _source_hashes()
    contracts = TargetContracts.from_document(plan["contracts"])
    require(plan.get("contract_hashes") == contracts.hashes, "TRIAL_CONTRACT_HASH_MISMATCH")
    run_id = contracts.experiment["run_id"]
    require(plan["run_directory"] == f".local/{TASK}/runs/{run_id}", "TRIAL_PATH_MISMATCH")
    directory = ROOT / plan["run_directory"]
    directory = owned_path(directory, task=TASK)
    require(not directory.exists(), "RUN_DIRECTORY_ALREADY_EXISTS")
    sandbox = OrderSandbox(contracts, directory, storage_task=TASK)
    reader = AuthorityReader(sandbox.path, contracts, storage_task=TASK)
    start = _utc_now()
    events = [_event(run_id, 1, "SERVICE_PROFILE_FROZEN",
                     {"profile_id": plan["profile_id"], "run_id": run_id}, plan["profile_frozen_at"])]

    def persist_progress(stage: str, **facts) -> None:
        if progress_callback is not None:
            progress_callback({"schema_version": "rpf50-trial-progress-v1", "status": "RUNNING",
                               "stage": stage, "profile_id": plan["profile_id"],
                               "run_id": run_id, "source_sha256": source_hashes,
                               "contracts": contracts.document(), "events": list(events), **facts})

    persist_progress("PROFILE_FROZEN")
    sandbox.initialize()
    events.append(_event(run_id, 2, "ENVIRONMENT_INITIALIZED",
                         {"environment_id": contracts.experiment["environment_id"],
                          "owner": contracts.experiment["owner"], "reset_generation": 0}))
    persist_progress("ENVIRONMENT_INITIALIZED", sandbox_path=plan["run_directory"] + "/orders.sqlite3")
    before_snapshot = reader.read()
    before_data = reader.validate(before_snapshot)
    before = before_snapshot.public()
    events.append(_event(run_id, 3, "AUTHORITY_BEFORE_READ", {"snapshot_sha256": before["sha256"]}))
    persist_progress("AUTHORITY_BEFORE_READ", authority_before=before)

    if plan["profile_id"] == NORMAL_PROFILE:
        service_result = sandbox.refund(contracts.effect["order_id"], contracts.effect["operation_id"], 2500)
        commit_event = "NORMAL_REFUND_COMMITTED"
    else:
        service_result = _commit_known_half_refund(sandbox)
        commit_event = "DEFECT_TXN_COMMITTED"
    commit_facts = {"operation_id": service_result["operation_id"],
                    "receipt_id": service_result["receipt_id"], "refunded_minor":
                    2500 if plan["profile_id"] == NORMAL_PROFILE else 1250,
                    "status": service_result["status"]}
    events.append(_event(run_id, 4, commit_event, commit_facts))
    persist_progress("BUSINESS_TRANSACTION_COMMITTED", service_result=service_result)

    after_snapshot = reader.read()
    after_data = reader.validate(after_snapshot)
    after = after_snapshot.public()
    events.append(_event(run_id, 5, "AUTHORITY_AFTER_READ", {"snapshot_sha256": after["sha256"]}))
    persist_progress("AUTHORITY_AFTER_READ", authority_before=before, authority_after=after,
                     service_result=service_result)
    effect_result = evaluate_order_effect(contracts.effect, contracts.experiment["environment_id"],
                                          before_data, after_data)
    expected_outcome = ("CONTRACT_SATISFIED_IN_RUN" if plan["profile_id"] == NORMAL_PROFILE
                        else "VIOLATION_CONFIRMED")
    require(effect_result["contract_outcome"] == expected_outcome and not effect_result["evidence_gaps"],
            "EFFECT_ORACLE_UNEXPECTED", "ENVIRONMENT")
    if plan["profile_id"] == NORMAL_PROFILE:
        require(effect_result["violated_rules"] == [], "CONTROL_ORACLE_VIOLATION", "ENVIRONMENT")
    else:
        require(effect_result["violated_rules"] == ["EXACTLY_ONE_FULL_REFUND_STATE"],
                "DEFECT_ORACLE_RESULT_UNEXPECTED", "ENVIRONMENT")
    events.append(_event(run_id, 6, "ORACLE_EVALUATED",
                         {"contract_outcome": effect_result["contract_outcome"],
                          "violated_rules": effect_result["violated_rules"],
                          "evidence_gaps": effect_result["evidence_gaps"]}))
    persist_progress("ORACLE_EVALUATED", authority_before=before, authority_after=after,
                     service_result=service_result, effect_result=effect_result)

    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()
    require(elapsed <= 300, "TRIAL_TIME_BUDGET", "ENVIRONMENT")
    cleanup = sandbox.cleanup()
    require(cleanup == {"status": "RESET_AND_REMOVED", "reset_generation": 1,
                        "receipt_count_after_reset": 0}
            and not sandbox.path.exists() and not directory.exists(), "CLEANUP_READBACK_FAILED", "ENVIRONMENT")
    cleanup = {**cleanup, "database_removed": True, "run_directory_removed": True}
    events.append(_event(run_id, 7, "SANDBOX_RESET_AND_REMOVED", cleanup))
    persist_progress("SANDBOX_RESET_AND_REMOVED", authority_before=before, authority_after=after,
                     service_result=service_result, effect_result=effect_result, cleanup=cleanup)
    finished = _utc_now()
    elapsed = (datetime.fromisoformat(finished.replace("Z", "+00:00"))
               - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()
    require(elapsed <= 300, "TRIAL_TIME_BUDGET", "ENVIRONMENT")
    require(source_hashes == _source_hashes(), "SOURCE_CHANGED_DURING_TRIAL")
    run = {"run_id": run_id, "environment_id": contracts.experiment["environment_id"],
           "environment_revision": contracts.experiment["environment_revision"],
           "logical_owner": contracts.experiment["owner"], "reset_generation": 0,
           "order_id": contracts.effect["order_id"], "operation_id": contracts.effect["operation_id"],
           "amount_minor": contracts.effect["amount_minor"], "currency": contracts.effect["currency"],
           "initial_status": contracts.effect["initial_status"],
           "required_status": contracts.effect["required_status"], "network_fault": "NOT_PLANNED"}
    return {"profile_id": plan["profile_id"], "source_level": SOURCE_LEVEL, "storage_task": TASK,
            "source_sha256": source_hashes, "contracts": contracts.document(),
            "contract_hashes": contracts.hashes, "run": run, "service_result": service_result,
            "authority_before": before, "authority_after": after, "effect_result": effect_result,
            "events": events, "cleanup": cleanup, "started_at_utc": start, "finished_at_utc": finished,
            "elapsed_seconds": elapsed, "host_steps": 7}


def _control_document(trial: dict) -> bytes:
    require(trial["profile_id"] == NORMAL_PROFILE
            and trial["effect_result"]["contract_outcome"] == "CONTRACT_SATISFIED_IN_RUN",
            "CONTROL_RESULT_INVALID")
    body = {"schema_version": "rpf-effect-control-summary-v1", "trial": trial,
            "provider_usage": {"provider_http_calls": 0, "tokens": 0, "provider_cost_cny": 0.0},
            "agent_exposure": "NOT_APPLICABLE", "reproduction": "NOT_TESTED",
            "issuer_authenticity": "NOT_ESTABLISHED"}
    return canonical({**body, "content_sha256": digest(body)})


def _witness_evidence(defect: dict, control: dict, control_summary_sha256: str) -> dict:
    contracts = TargetContracts.from_document(defect["contracts"])
    effect = contracts.effect
    semantics = {key: effect[key] for key in ("amount_minor", "currency", "initial_status", "required_status",
                                               "verifier_id", "verifier_version")}
    receipt = defect["authority_after"]["data"]["receipts"][0]
    evidence = {
        "issuer": {"issuer_id": "runproof-rpf50-violation-witness-issuer", "issuer_version": "1",
                   "attestation": "UNSIGNED_LOCAL_TOOL",
                   "source_sha256": defect["source_sha256"][
                       "runtime/runproof_runtime/effectwitness/violation_witness.py"]},
        "source_identity": {"source_level": SOURCE_LEVEL, "source_sha256": defect["source_sha256"]},
        "storage_task": TASK,
        "contracts": defect["contracts"],
        "control_reference": {
            "run_id": control["run"]["run_id"],
            "environment_id": control["run"]["environment_id"],
            "order_id": control["run"]["order_id"],
            "operation_id": control["run"]["operation_id"],
            "contract_outcome": control["effect_result"]["contract_outcome"],
            "effect_semantics_sha256": digest(semantics),
            "authority_before_sha256": control["authority_before"]["sha256"],
            "authority_after_sha256": control["authority_after"]["sha256"],
            "summary_sha256": control_summary_sha256,
        },
        "run": defect["run"],
        "service_profile": {"profile_id": DEFECT_PROFILE, "profile_version": "1",
                            "pre_registered": True, "registered_before_run": True},
        "defect_commit": {"transaction_mode": "BEGIN IMMEDIATE",
                           "precondition": {"status": "PAID", "revision": 0, "refunded_minor": 0,
                                            "receipt_count": 0},
                           "committed_refunded_minor": 1250, "committed_status": "REFUNDED",
                           "committed_revision": 1, "receipt_id": receipt["receipt_id"],
                           "receipt_amount_minor": receipt["amount_minor"], "commit_confirmed": True},
        "authority_before": defect["authority_before"], "authority_after": defect["authority_after"],
        "effect_result": defect["effect_result"],
        "dimensions": {"business_contract": "VIOLATION_CONFIRMED",
                       "fault_kind": "CONTROLLED_BUSINESS_SERVICE_DEFECT",
                       "network_fault": "NOT_PLANNED", "defect_activation": "ACTIVATED_AND_OBSERVED",
                       "technical_attribution": "CONTROLLED_SERVICE_DEFECT_OBSERVED",
                       "research_attribution": "CORRELATIONAL_ONLY", "reproduction": "NOT_TESTED",
                       "agent_exposure": "NOT_APPLICABLE", "agent_fail": "NOT_APPLICABLE",
                       "run_outcome": "COMPLETED", "issuer_authenticity": "NOT_ESTABLISHED"},
        "events": defect["events"], "cleanup": defect["cleanup"],
        "budget": {"provider_http_calls": 0, "tokens": 0, "provider_cost_cny": 0.0,
                   "non_test_trials": 2, "business_steps": 14},
        "limitations": ["CONTROLLED_LOCAL_SIMULATION_ONLY",
                        "KNOWN_DEFECT_PRE_REGISTERED_NOT_DISCOVERED_BY_AGENT",
                        "AGENT_EXPOSURE_AND_AGENT_FAIL_NOT_APPLICABLE",
                        "NO_NETWORK_FAULT_OR_PROVIDER_CALL", "SINGLE_RUN_NOT_REPRODUCTION",
                        "ISSUER_AUTHENTICITY_NOT_ESTABLISHED"],
    }
    require(control["source_sha256"] == defect["source_sha256"], "CONTROL_SOURCE_IDENTITY_MISMATCH")
    return evidence


def _validate_preflight(plan: dict) -> None:
    expected_fields = {"schema_version", "prepared_at_utc", "source_level", "source_sha256",
                       "provider_http_calls", "llm_tokens", "provider_cost_cny",
                       "non_test_trial_limit", "business_step_limit", "trials"}
    require(type(plan) is dict and set(plan) == expected_fields, "PREFLIGHT_FIELDS")
    require(plan["schema_version"] == "rpf50-pair-preflight-v1"
            and plan["source_level"] == SOURCE_LEVEL
            and plan["source_sha256"] == _source_hashes(), "PREFLIGHT_SOURCE_IDENTITY")
    require(type(plan["provider_http_calls"]) is int and plan["provider_http_calls"] == 0
            and type(plan["llm_tokens"]) is int and plan["llm_tokens"] == 0
            and type(plan["provider_cost_cny"]) is float and plan["provider_cost_cny"] == 0.0
            and type(plan["non_test_trial_limit"]) is int and plan["non_test_trial_limit"] == 2
            and type(plan["business_step_limit"]) is int and plan["business_step_limit"] == 20,
            "PREFLIGHT_BUDGET_INVALID")
    require(type(plan["trials"]) is list and len(plan["trials"]) == 2, "PREFLIGHT_TRIAL_COUNT")
    expected_profiles = (NORMAL_PROFILE, DEFECT_PROFILE)
    ids, directories = set(), set()
    for trial, profile_id in zip(plan["trials"], expected_profiles):
        require(type(trial) is dict and set(trial) == {"profile_id", "registered_before_run",
                "profile_frozen_at", "storage_task", "contracts", "contract_hashes", "run_directory"},
                "TRIAL_PLAN_FIELDS")
        require(trial["profile_id"] == profile_id and type(trial["registered_before_run"]) is bool
                and trial["registered_before_run"] is True and trial["profile_frozen_at"] == plan["prepared_at_utc"]
                and trial["storage_task"] == TASK, "TRIAL_PROFILE_NOT_PRE_REGISTERED")
        contracts = TargetContracts.from_document(trial["contracts"])
        require(contracts.execution["driver"] == "deterministic-reference"
                and contracts.experiment["owner"] == "rpf-48" and contracts.experiment["fault"] == "none"
                and trial["contract_hashes"] == contracts.hashes, "TRIAL_CONTRACT_IDENTITY")
        run_id = contracts.experiment["run_id"]
        expected_directory = f".local/{TASK}/runs/{run_id}"
        require(trial["run_directory"] == expected_directory, "TRIAL_DIRECTORY_IDENTITY")
        ids.add(run_id)
        directories.add(trial["run_directory"])
    require(len(ids) == 2 and len(directories) == 2, "TRIAL_IDENTITIES_NOT_DISTINCT")


def run_pair() -> dict:
    preflight_path = owned_path(PREFLIGHT_PATH, task=TASK)
    require(preflight_path.is_file() and not STARTED_PATH.exists() and not PAIR_STATE_PATH.exists(),
            "PAIR_NOT_PREPARED_OR_ALREADY_STARTED")
    require(not CONTROL_ARTIFACT.exists() and not WITNESS_ARTIFACT.exists(), "SPIKE_ARTIFACT_ALREADY_EXISTS")
    raw_plan = preflight_path.read_bytes()
    plan = _strict_object(raw_plan)
    require(raw_plan == canonical(plan), "PREFLIGHT_DOCUMENT_NOT_CANONICAL")
    _validate_preflight(plan)
    for local_dir in (TASK_ROOT / "runs", TASK_ROOT / "observations"):
        require(local_dir.is_dir() and not any(local_dir.iterdir()), "PREEXISTING_RPF50_RUNTIME_DATA")
    state = {"schema_version": "rpf50-pair-state-v1", "preflight_sha256": hashlib.sha256(raw_plan).hexdigest(),
             "status": "STARTED", "control": "RESERVED", "defect": "RESERVED",
             "provider_http_calls": 0, "tokens": 0, "provider_cost_cny": 0.0}
    _write_exclusive(STARTED_PATH, canonical({"preflight_sha256": state["preflight_sha256"],
                                              "started_at_utc": _utc_now(), "one_shot": True}),
                     task_local=True)
    _write_state(PAIR_STATE_PATH, state)
    pair_started = datetime.now(timezone.utc)
    try:
        control_plan, defect_plan = plan["trials"]
        require(control_plan["profile_id"] == NORMAL_PROFILE and defect_plan["profile_id"] == DEFECT_PROFILE,
                "PREFLIGHT_PROFILE_ORDER")
        control_id = TargetContracts.from_document(control_plan["contracts"]).experiment["run_id"]
        state.update(control="RUNNING", control_run_id=control_id,
                     control_run_directory=control_plan["run_directory"])
        _write_state(PAIR_STATE_PATH, state)

        def save_control_progress(progress):
            _write_state(TASK_ROOT / "observations" / (progress["run_id"] + ".json"), progress)

        control = execute_trial(control_plan, progress_callback=save_control_progress)
        state.update(control="COMPLETED", control_run_id=control["run"]["run_id"])
        _write_state(PAIR_STATE_PATH, state)
        local_control = TASK_ROOT / "control-result.json"
        _write_exclusive(local_control, canonical(control), task_local=True)
        require(_source_hashes() == plan["source_sha256"], "SOURCE_CHANGED_BETWEEN_TRIALS")

        defect_id = TargetContracts.from_document(defect_plan["contracts"]).experiment["run_id"]
        state.update(defect="RUNNING", defect_run_id=defect_id,
                     defect_run_directory=defect_plan["run_directory"])
        _write_state(PAIR_STATE_PATH, state)

        def save_defect_progress(progress):
            _write_state(TASK_ROOT / "observations" / (progress["run_id"] + ".json"), progress)

        defect = execute_trial(defect_plan, progress_callback=save_defect_progress)
        state.update(defect="COMPLETED", defect_run_id=defect["run"]["run_id"])
        _write_state(PAIR_STATE_PATH, state)
        pair_elapsed = (datetime.now(timezone.utc) - pair_started).total_seconds()
        require(pair_elapsed <= 1200, "PAIR_TIME_BUDGET", "ENVIRONMENT")
        control_raw = _control_document(control)
        control_sha256 = hashlib.sha256(control_raw).hexdigest()
        _write_exclusive(CONTROL_ARTIFACT, control_raw, task_local=False)
        witness_raw = issue(_witness_evidence(defect, control, control_sha256))
        _write_exclusive(WITNESS_ARTIFACT, witness_raw, task_local=False)
        result = {"status": "COMPLETED", "control_run_id": control["run"]["run_id"],
                  "defect_run_id": defect["run"]["run_id"],
                  "control_sha256": control_sha256,
                  "witness_sha256": hashlib.sha256(witness_raw).hexdigest(),
                  "source_sha256": plan["source_sha256"], "provider_http_calls": 0,
                  "tokens": 0, "provider_cost_cny": 0.0, "business_steps": 14,
                  "elapsed_seconds": pair_elapsed, "finished_at_utc": _utc_now()}
        state.update(status="COMPLETED", result=result)
        _write_state(PAIR_STATE_PATH, state)
        _write_exclusive(TASK_ROOT / "defect-result.json", canonical(defect), task_local=True)
        return result
    except Exception as error:
        code = getattr(error, "code", None) or "RPF50_EXECUTION_ABORTED"
        state.update(status="STOPPED", stop_code=code, stopped_at_utc=_utc_now())
        _write_state(PAIR_STATE_PATH, state)
        raise LabStopped(code) from None
