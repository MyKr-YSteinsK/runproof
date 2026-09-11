"""Thin Docker provider boundary for the first product Run."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import time
import uuid
from typing import Any

from .models import INITIAL_STATE, RuntimeFailure, TARGET_STATE


IMAGE = "alpine:3.22"
STATE_ROOT = "/runproof"
STATE_PATH = f"{STATE_ROOT}/state"
READY_PATH = f"{STATE_ROOT}/ready"
SEED_TEXT = "release=release-v1\\nrevision=0\\nmutation_count=0\\noperation_id=null\\n"


def _docker(args: list[str], timeout: float = 20.0, code: str = "DOCKER_COMMAND_FAILED") -> str:
    try:
        result = subprocess.run(
            ["docker", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeFailure("ENVIRONMENT", code) from error
    if result.returncode != 0:
        raise RuntimeFailure("ENVIRONMENT", code)
    return result.stdout.strip()


def _docker_optional(args: list[str], not_found_pattern: str) -> str | None:
    try:
        result = subprocess.run(
            ["docker", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=20.0,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeFailure("ENVIRONMENT", "DOCKER_INSPECT_UNAVAILABLE") from error
    if result.returncode == 0:
        return result.stdout.strip()
    if re.search(not_found_pattern, result.stderr, re.IGNORECASE):
        return None
    raise RuntimeFailure("ENVIRONMENT", "DOCKER_INSPECT_UNAVAILABLE")


def _docker_check(args: list[str]) -> bool:
    """Run a predicate command; false is a predicate miss, not provider failure."""

    try:
        result = subprocess.run(
            ["docker", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=20.0,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeFailure("ENVIRONMENT", "DOCKER_READINESS_UNAVAILABLE") from error
    if result.returncode == 0:
        return True
    if re.search(r"no such container|not found|cannot connect", result.stderr, re.IGNORECASE):
        raise RuntimeFailure("ENVIRONMENT", "DOCKER_READINESS_UNAVAILABLE")
    return False


def provider_snapshot() -> dict[str, Any]:
    """Read provider readiness and image identity without pulling or installing anything."""

    version = _docker(
        ["version", "--format", "client={{.Client.Version}}|server={{.Server.Version}}"],
        code="DOCKER_DAEMON_UNAVAILABLE",
    )
    client, server = (version.split("|", 1) + [""])[:2]
    context = _docker(["context", "show"], code="DOCKER_CONTEXT_UNAVAILABLE")
    info = _docker(["info", "--format", "{{.Driver}}|{{.OSType}}|{{.ServerVersion}}"], code="DOCKER_INFO_UNAVAILABLE")
    storage_driver, os_type, info_server = (info.split("|", 2) + [""])[:3]

    image_line = _docker(
        ["images", IMAGE, "--no-trunc", "--format", "{{.Repository}}:{{.Tag}}|{{.ID}}"],
        code="DOCKER_IMAGE_UNAVAILABLE",
    )
    rows = [line for line in image_line.splitlines() if line.startswith(f"{IMAGE}|")]
    if not rows:
        raise RuntimeFailure("ENVIRONMENT", "DOCKER_IMAGE_UNAVAILABLE")
    image_ref, image_id = rows[0].split("|", 1)
    return {
        "kind": "docker",
        "context": context,
        "daemon_ready": True,
        "client_version": client.replace("client=", "", 1),
        "server_version": server.replace("server=", "", 1),
        "info_server_version": info_server,
        "os_type": os_type,
        "storage_driver": storage_driver,
        "image": {"reference": image_ref, "id": image_id},
    }


def _parse_state(text: str) -> dict[str, Any]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    try:
        return {
            "release": values["release"],
            "revision": int(values["revision"]),
            "mutation_count": int(values["mutation_count"]),
            "operation_id": None if values["operation_id"] == "null" else values["operation_id"],
        }
    except (KeyError, ValueError) as error:
        raise RuntimeFailure("ENVIRONMENT", "MALFORMED_STATE") from error


def _safe_mounts(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": mount.get("Type"),
            "name": mount.get("Name"),
            "destination": mount.get("Destination"),
            "read_write": mount.get("RW") is True,
        }
        for mount in raw
    ]


class DockerEnvironment:
    """One fresh container with state owned by its writable layer."""

    SUPPORTED_FAILURE_HOOKS = {"pre-agent-readiness"}

    def __init__(self, provider: dict[str, Any], role: str, failure_hook: str | None = None) -> None:
        if failure_hook not in {None, *self.SUPPORTED_FAILURE_HOOKS}:
            raise RuntimeFailure("HARNESS", "UNKNOWN_ENVIRONMENT_FAILURE_HOOK")
        token = uuid.uuid4().hex[:10]
        self.provider = provider
        self.role = role
        self.failure_hook = failure_hook
        self.name = f"rpf03-{role}-{token}"
        self.container_id: str | None = None
        self.contract: dict[str, Any] = {
            "environment_id": f"docker-{role}-{uuid.uuid4()}",
            "seed_id": "rpf-02-release-simulation-seed",
            "seed_revision": "seed-2026-09-11-v1",
            "provenance": None,
            "lifecycle_state": "UNPROVISIONED",
            "readiness": "UNKNOWN",
            "verified_initial_state": False,
            "observable_state": None,
            "operation_receipt": None,
            "mutable_state_ownership": "container-writable-layer",
            "cleanup_state": "NOT_STARTED",
            "quarantine_state": None,
            "controlled_failure": None,
        }

    def provision(self) -> dict[str, Any]:
        script = (
            f"mkdir -p {STATE_ROOT}; "
            f"printf '{SEED_TEXT}' > {STATE_PATH}; "
            f"printf 'ready=1\\n' > {READY_PATH}; "
            "exec sleep 300"
        )
        self.container_id = _docker(
            [
                "run",
                "--detach",
                "--pull=never",
                "--network",
                "none",
                "--name",
                self.name,
                "--label",
                "io.runproof.plan=rpf-03",
                "--label",
                f"io.runproof.environment-id={self.contract['environment_id']}",
                IMAGE,
                "sh",
                "-c",
                script,
            ],
            code="ENVIRONMENT_PROVISION_FAILED",
        )
        inspection = self.inspect()
        self.contract["provenance"] = {
            "provider": "docker",
            "context": self.provider["context"],
            "image_ref": IMAGE,
            "image_id": self.provider["image"]["id"],
            "container_id": inspection["container_id"],
            "container_name": self.name,
            "state_owner": "container-writable-layer",
            "mounts": inspection["mounts"],
        }
        self.contract["lifecycle_state"] = "PROVISIONED"
        self.contract["cleanup_state"] = "PENDING"
        return self.snapshot()

    def inspect(self) -> dict[str, Any]:
        try:
            raw = json.loads(_docker(["inspect", self.name], code="ENVIRONMENT_INSPECT_FAILED"))
        except json.JSONDecodeError as error:
            raise RuntimeFailure("ENVIRONMENT", "MALFORMED_INSPECT") from error
        if not raw:
            raise RuntimeFailure("ENVIRONMENT", "ENVIRONMENT_NOT_FOUND")
        item = raw[0]
        return {
            "container_id": item.get("Id"),
            "running": item.get("State", {}).get("Running") is True,
            "status": item.get("State", {}).get("Status"),
            "mounts": _safe_mounts(item.get("Mounts", [])),
        }

    def inspect_optional(self) -> dict[str, Any] | None:
        output = _docker_optional(["inspect", self.name], r"no such object|no such container|not found")
        if output is None:
            return None
        try:
            raw = json.loads(output)
        except json.JSONDecodeError as error:
            raise RuntimeFailure("ENVIRONMENT", "MALFORMED_INSPECT") from error
        return safe_inspect(raw)

    def readiness(self, timeout_seconds: float = 5.0) -> dict[str, Any]:
        if self.contract["lifecycle_state"] == "QUARANTINED":
            return {"ok": False, "code": "QUARANTINED"}
        if self.failure_hook == "pre-agent-readiness":
            inspection = self.inspect()
            if not inspection["running"]:
                self.quarantine("CONTAINER_NOT_RUNNING")
                return {"ok": False, "code": "CONTAINER_NOT_RUNNING"}
            self.contract["lifecycle_state"] = "FAILED_BEFORE_AGENT"
            self.contract["readiness"] = "CONTROLLED_FAILURE"
            self.contract["controlled_failure"] = {
                "hook_id": "pre-agent-readiness",
                "source": "ENVIRONMENT",
                "code": "CONTROLLED_READINESS_FAILURE",
                "agent_started": False,
                "state_change_performed": False,
            }
            return {
                "ok": False,
                "code": "CONTROLLED_READINESS_FAILURE",
                "source": "ENVIRONMENT",
                "controlled": True,
                "agent_started": False,
            }
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            inspection = self.inspect()
            if not inspection["running"]:
                self.quarantine("CONTAINER_NOT_RUNNING")
                return {"ok": False, "code": "CONTAINER_NOT_RUNNING"}
            if _docker_check(["exec", self.name, "sh", "-c", f"test -f {READY_PATH}"]):
                self.contract["lifecycle_state"] = "READY_UNVERIFIED"
                self.contract["readiness"] = "READY"
                return {"ok": True, "readiness": "READY"}
            time.sleep(0.1)
        self.quarantine("READINESS_TIMEOUT")
        return {"ok": False, "code": "READINESS_TIMEOUT"}

    def read_state(self) -> dict[str, Any]:
        state = _parse_state(_docker(["exec", self.name, "sh", "-c", f"cat {STATE_PATH}"], code="STATE_READ_FAILED"))
        self.contract["observable_state"] = copy.deepcopy(state)
        return state

    def verify_initial(self) -> dict[str, Any]:
        if self.contract["lifecycle_state"] != "READY_UNVERIFIED":
            return {"ok": False, "code": "READINESS_GATE_REQUIRED", "verified": False}
        state = self.read_state()
        if state != INITIAL_STATE:
            self.quarantine("INITIAL_STATE_MISMATCH")
            return {"ok": False, "code": "INITIAL_STATE_MISMATCH", "verified": False, "observed": state}
        self.contract["lifecycle_state"] = "READY_VERIFIED"
        self.contract["verified_initial_state"] = True
        return {"ok": True, "verified": True, "state": state}

    def apply_change(self, operation_id: str = "change-001") -> dict[str, Any]:
        if not re.fullmatch(r"[a-z0-9-]+", operation_id):
            raise RuntimeFailure("HARNESS", "INVALID_OPERATION_ID")
        if not self.contract["verified_initial_state"]:
            raise RuntimeFailure("AGENT", "INITIAL_STATE_GATE_REQUIRED")
        script = f"printf 'release=release-v2\\nrevision=1\\nmutation_count=1\\noperation_id={operation_id}\\n' > {STATE_PATH}"
        _docker(["exec", self.name, "sh", "-c", script], code="MUTATION_FAILED")
        state = self.read_state()
        receipt = {"operation_id": operation_id, "status": "APPLIED"}
        self.contract["lifecycle_state"] = "RUNNING"
        self.contract["operation_receipt"] = copy.deepcopy(receipt)
        return {"ok": True, "state": state, "receipt": receipt}

    def quarantine(self, reason: str) -> None:
        self.contract["lifecycle_state"] = "QUARANTINED"
        self.contract["readiness"] = "UNTRUSTED"
        self.contract["verified_initial_state"] = False
        self.contract["cleanup_state"] = "UNVERIFIED"
        self.contract["quarantine_state"] = {
            "status": "QUARANTINED",
            "reason": reason,
            "source": "ENVIRONMENT",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def cleanup(self) -> dict[str, Any]:
        if self.contract["lifecycle_state"] == "QUARANTINED":
            return {"ok": False, "code": "QUARANTINED"}
        try:
            _docker(["rm", "--force", self.name], code="CLEANUP_FAILED")
            if self.inspect_optional() is not None:
                raise RuntimeFailure("ENVIRONMENT", "CLEANUP_UNVERIFIED")
        except RuntimeFailure:
            self.quarantine("CLEANUP_UNVERIFIED")
            return {"ok": False, "code": "CLEANUP_UNVERIFIED"}
        self.contract["lifecycle_state"] = "CLEANED"
        self.contract["cleanup_state"] = "CLEANED"
        return {"ok": True, "removed": True}

    def force_cleanup(self) -> None:
        _docker_optional(["rm", "--force", self.name], r"no such object|no such container|not found")

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.contract)


def safe_inspect(raw: list[dict[str, Any]]) -> dict[str, Any]:
    if not raw:
        raise RuntimeFailure("ENVIRONMENT", "ENVIRONMENT_NOT_FOUND")
    item = raw[0]
    return {
        "container_id": item.get("Id"),
        "running": item.get("State", {}).get("Running") is True,
        "status": item.get("State", {}).get("Status"),
        "mounts": _safe_mounts(item.get("Mounts", [])),
    }
