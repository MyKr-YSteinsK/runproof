"""Small authenticated client for the formal RunProof Control Plane.

The client owns HTTP/JSON and immutable local artifact registration. It never
opens a database connection and never puts credentials in a manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


INGEST_MANIFEST_SCHEMA = "rpf-canonical-ingest-v1"
DEFAULT_BASE_URL = "http://127.0.0.1:8081/api/v1"
DEFAULT_ARTIFACT_ROOT = ".local/control-plane/artifacts"

CONTRACTS: dict[str, tuple[str, str, str, str]] = {
    "Run Evidence": ("RUN", "rpf-run-evidence-v2", "run", "run_id"),
    "Failure Case": ("FAILURE_CASE", "rpf-failure-case-v1", "failure_case", "failure_case_id"),
    "Regression": ("REGRESSION", "rpf-regression-v1", "regression", "regression_id"),
    "Regression Execution Result": ("REGRESSION_RESULT", "rpf-regression-result-v1", "result", "result_id"),
    "Historical Regression Collection": ("REGRESSION_COLLECTION", "rpf-regression-collection-v1", "collection", "collection_id"),
    "Evaluation Suite": ("EVALUATION_SUITE", "rpf-evaluation-suite-v1", "suite", "suite_id"),
    "Evaluation Result": ("EVALUATION", "rpf-evaluation-result-v1", "evaluation", "evaluation_id"),
    "Evaluation Comparison": ("COMPARISON", "rpf-evaluation-comparison-v1", "comparison", "comparison_id"),
    "Quality Policy": ("QUALITY_POLICY", "rpf-quality-policy-v1", "policy", "policy_id"),
    "Quality Gate Evaluation": ("QUALITY_GATE", "rpf-quality-gate-evaluation-v1", "gate_evaluation", "gate_evaluation_id"),
    "Release Decision": ("RELEASE_DECISION", "rpf-release-decision-v1", "release_decision", "release_decision_id"),
}

KIND_TO_ENTITY = {kind: contract[0] for kind, contract in CONTRACTS.items()}
REF_ID_FIELDS = (
    "run_id", "failure_case_id", "regression_id", "result_id", "collection_id", "suite_id",
    "evaluation_id", "comparison_id", "policy_id", "gate_evaluation_id", "release_decision_id",
)


class ControlPlaneClientError(RuntimeError):
    """Classified client/API error with no raw response body by default."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str = "CONTROL_PLANE_ERROR",
        retriable: bool = False,
        evidence_valid: bool | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retriable = retriable
        self.evidence_valid = evidence_valid
        self.correlation_id = correlation_id


class TransportUncertainError(ControlPlaneClientError):
    def __init__(self, message: str = "Control Plane transport result is uncertain") -> None:
        super().__init__(message, code="TRANSPORT_UNCERTAIN", retriable=True)


@dataclass(frozen=True)
class ArtifactManifest:
    path: Path
    content: bytes
    document: dict[str, Any]
    entity_type: str
    entity_id: str
    schema_version: str
    artifact_kind: str
    content_sha256: str
    source_sha256: str
    runtime_version: str
    artifact_key: str
    manifest: dict[str, Any]


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _first_text(value: Any, key: str) -> str:
    for item in _walk(value):
        candidate = item.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return ""


def _stable_ref(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, dict):
        return None
    kind = value.get("kind")
    if not isinstance(kind, str) or kind not in KIND_TO_ENTITY:
        return None
    for field in REF_ID_FIELDS:
        identifier = value.get(field)
        if isinstance(identifier, str) and identifier:
            return KIND_TO_ENTITY[kind], identifier
    return None


def _relationship_refs(document: dict[str, Any], entity_type: str) -> list[dict[str, str]]:
    contract = next((item for item in CONTRACTS.values() if item[0] == entity_type), None)
    if contract is None:
        return []
    container = document.get(contract[2], {})
    if not isinstance(container, dict):
        return []
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for role, value in container.items():
        if not role.endswith("_ref") and role not in {"stable_ref", "source_run_ref", "regression_ref"}:
            continue
        resolved = _stable_ref(value)
        if resolved is None:
            continue
        ref_type, ref_id = resolved
        identity = (role, ref_type, ref_id)
        if identity in seen:
            continue
        seen.add(identity)
        refs.append({"role": role, "entity_type": ref_type, "entity_id": ref_id})
    return refs


def _summary(document: dict[str, Any], entity_type: str, entity_id: str) -> dict[str, Any]:
    """Build a bounded canonical summary; trajectory/raw fields never enter it."""

    contract = next(item for item in CONTRACTS.values() if item[0] == entity_type)
    container = document.get(contract[2], {})
    if not isinstance(container, dict):
        container = {}
    outcome = "UNKNOWN"
    for key in ("status", "current_status", "outcome", "evaluation_status", "decision_status", "lifecycle_status"):
        value = container.get(key)
        if isinstance(value, str) and value:
            outcome = value
            break
    if entity_type == "RUN" and isinstance(document.get("outcome"), dict):
        outcome = str(document["outcome"].get("status") or outcome)
    agent = container.get("agent") if isinstance(container.get("agent"), dict) else document.get("agent")
    scenario = container.get("scenario") if isinstance(container.get("scenario"), dict) else document.get("scenario")
    summary: dict[str, Any] = {
        "entity_id": entity_id,
        "status": outcome,
    }
    if isinstance(container.get("category"), str):
        summary["category"] = container["category"]
    if isinstance(container.get("decision_subject"), str):
        summary["decision_subject"] = container["decision_subject"]
    if isinstance(agent, dict):
        for key in ("agent_id", "agent_family", "agent_version", "known_bad_version"):
            if isinstance(agent.get(key), str):
                summary[key] = agent[key]
    if isinstance(scenario, dict):
        for key in ("scenario_id", "scenario_version"):
            if isinstance(scenario.get(key), str):
                summary[key] = scenario[key]
    if isinstance(container.get("evaluation_id"), str):
        summary["evaluation_id"] = container["evaluation_id"]
    if entity_type == "RUN" and isinstance(container.get("evaluation_id"), str):
        summary["evaluation_id"] = container["evaluation_id"]
    if entity_type == "RELEASE_DECISION":
        summary["decision_status"] = outcome
        candidate_version = container.get("candidate_agent_version")
        if isinstance(candidate_version, str):
            summary["candidate_agent_version"] = candidate_version
    return summary


def _source_identity(document: dict[str, Any], content_sha256: str) -> tuple[str, str]:
    source_sha256 = _first_text(document, "source_sha256")
    runtime_version = _first_text(document, "runtime_version")
    # Older reviewed artifacts have no source hash. Content hash is a
    # deterministic, non-secret provenance fallback without rewriting bytes.
    return source_sha256 or content_sha256, runtime_version or "rpf-import-v1"


def build_artifact_manifest(path: Path, artifact_store_root: Path) -> ArtifactManifest:
    content = path.read_bytes()
    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ControlPlaneClientError(f"Invalid artifact JSON: {path.name}", code="INVALID_ARTIFACT_JSON") from exc
    if not isinstance(document, dict):
        raise ControlPlaneClientError(f"Artifact must be a JSON object: {path.name}", code="INVALID_ARTIFACT_JSON")
    artifact_kind = document.get("artifact_kind")
    schema_version = document.get("schema_version")
    if not isinstance(artifact_kind, str) or not isinstance(schema_version, str) or artifact_kind not in CONTRACTS:
        raise ControlPlaneClientError(f"Unsupported reviewed artifact kind: {path.name}", code="UNSUPPORTED_ARTIFACT_KIND")
    entity_type, expected_schema, container_name, id_field = CONTRACTS[artifact_kind]
    if schema_version != expected_schema:
        raise ControlPlaneClientError(f"Unexpected artifact schema: {path.name}", code="UNSUPPORTED_ARTIFACT_SCHEMA")
    container = document.get(container_name)
    entity_id = container.get(id_field) if isinstance(container, dict) else None
    if not isinstance(entity_id, str) or not entity_id:
        raise ControlPlaneClientError(f"Artifact identity is missing: {path.name}", code="INVALID_ARTIFACT_IDENTITY")
    if not _is_safe_path_component(entity_id):
        raise ControlPlaneClientError("Artifact identity cannot be used as a store path component", code="INVALID_ARTIFACT_PATH")
    content_sha256 = hashlib.sha256(content).hexdigest()
    source_sha256, runtime_version = _source_identity(document, content_sha256)
    artifact_key = f"{entity_type.lower()}/{entity_id}/{content_sha256}.json"
    store_root = artifact_store_root.resolve()
    target = (store_root / Path(*artifact_key.split("/"))).resolve()
    try:
        target.relative_to(store_root)
    except ValueError as exc:
        raise ControlPlaneClientError("Artifact key escapes the local artifact store", code="INVALID_ARTIFACT_PATH") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != content:
        raise ControlPlaneClientError("Immutable artifact key contains different bytes", code="ARTIFACT_OVERWRITE_REJECTED")
    if not target.exists():
        try:
            with target.open("xb") as handle:
                handle.write(content)
        except FileExistsError:
            if target.read_bytes() != content:
                raise ControlPlaneClientError("Immutable artifact key contains different bytes", code="ARTIFACT_OVERWRITE_REJECTED")
    source = {"source_sha256": source_sha256, "runtime_version": runtime_version}
    refs = _relationship_refs(document, entity_type)
    manifest = {
        "manifest_schema_version": INGEST_MANIFEST_SCHEMA,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_schema_version": schema_version,
        "outcome": _summary(document, entity_type, entity_id)["status"],
        "agent_version": _summary(document, entity_type, entity_id).get("agent_version"),
        "evaluation_id": _summary(document, entity_type, entity_id).get("evaluation_id"),
        "idempotency_key": f"{entity_type}:{entity_id}:{content_sha256}",
        "supersedes_entity_id": (
            container.get("history", {}).get("supersedes_decision_id")
            if isinstance(container, dict) and isinstance(container.get("history"), dict)
            else None
        ),
        "source_identity": source,
        "key_refs": refs,
        "summary": _summary(document, entity_type, entity_id),
        "artifact_ref": {
            "artifact_id": entity_id,
            "artifact_key": artifact_key,
            "artifact_kind": artifact_kind,
            "schema_version": schema_version,
            "content_sha256": content_sha256,
            "source_sha256": source_sha256,
            "runtime_version": runtime_version,
        },
    }
    return ArtifactManifest(
        path=path,
        content=content,
        document=document,
        entity_type=entity_type,
        entity_id=entity_id,
        schema_version=schema_version,
        artifact_kind=artifact_kind,
        content_sha256=content_sha256,
        source_sha256=source_sha256,
        runtime_version=runtime_version,
        artifact_key=artifact_key,
        manifest=manifest,
    )


def _is_safe_path_component(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and "/" not in value and "\\" not in value and "\x00" not in value


class ControlPlaneClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        timeout: float = 8.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.base_url = (base_url or os.environ.get("RPF_CONTROL_PLANE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.token = token or os.environ.get("RPF_CONTROL_PLANE_TOKEN")
        if not self.token:
            raise ControlPlaneClientError("Control Plane token is not configured", code="CLIENT_CREDENTIAL_MISSING")
        self.timeout = timeout
        self._opener = opener

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
                "X-Request-Id": f"rpf-client-{uuid.uuid4()}",
            },
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw = response.read()
                status = getattr(response, "status", 200)
        except HTTPError as error:
            raw = error.read()
            status = error.code
            self._raise_api_error(status, raw, error.headers.get("X-Request-Id") if error.headers else None)
        except (URLError, TimeoutError, OSError) as error:
            raise TransportUncertainError() from error
        try:
            document = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ControlPlaneClientError("Control Plane returned invalid JSON", status=status, code="INVALID_API_RESPONSE") from error
        if not isinstance(document, dict):
            raise ControlPlaneClientError("Control Plane returned a non-object JSON response", status=status, code="INVALID_API_RESPONSE")
        return document

    @staticmethod
    def _raise_api_error(status: int, raw: bytes, correlation_id: str | None) -> None:
        try:
            document = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            document = {}
        code = document.get("error") if isinstance(document.get("error"), str) else "CONTROL_PLANE_HTTP_ERROR"
        retriable = bool(document.get("retriable")) or status in {408, 429, 500, 502, 503, 504}
        message = "Control Plane request failed"
        if status == 401:
            code = "AUTHENTICATION_REQUIRED"
        elif status == 403:
            code = "AUTHORIZATION_FORBIDDEN"
        raise ControlPlaneClientError(
            message,
            status=status,
            code=code,
            retriable=retriable,
            evidence_valid=document.get("evidence_valid") if isinstance(document, dict) else None,
            correlation_id=correlation_id or (document.get("correlation_id") if isinstance(document, dict) else None),
        )

    def ingest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        entity_type = manifest.get("entity_type")
        path = "/release-decisions" if entity_type == "RELEASE_DECISION" else "/ingest/completed-evidence"
        return self.request("POST", path, manifest)

    def get(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        try:
            return self.request("GET", f"/metadata/{quote(entity_type, safe='')}/{quote(entity_id, safe='')}")
        except ControlPlaneClientError as error:
            if error.status == 404 and error.code == "CANONICAL_METADATA_NOT_FOUND":
                return None
            raise

    def list(self, entity_type: str | None = None) -> list[dict[str, Any]]:
        suffix = "" if entity_type is None else f"?entity_type={entity_type}"
        response = self.request("GET", f"/metadata{suffix}")
        items = response.get("items")
        if not isinstance(items, list):
            raise ControlPlaneClientError("Control Plane list response is malformed", code="INVALID_API_RESPONSE")
        return [item for item in items if isinstance(item, dict)]

    def get_artifact(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        return self.request("GET", f"/artifacts/{quote(entity_type, safe='')}/{quote(entity_id, safe='')}")

    def ingest_with_reconcile(self, manifest: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.ingest(manifest)
        except ControlPlaneClientError as error:
            if not error.retriable and error.status is not None:
                raise
            existing = self.get(str(manifest["entity_type"]), str(manifest["entity_id"]))
            expected = manifest.get("artifact_ref", {})
            if existing is not None:
                current = existing.get("canonical_metadata", {}).get("artifact_ref", {})
                if current.get("content_sha256") == expected.get("content_sha256"):
                    return {"status": "RECONCILED", "already_exists": True, "metadata": existing}
                raise ControlPlaneClientError(
                    "Transport reconciliation found different immutable content",
                    status=409,
                    code="IDENTITY_CONTENT_CONFLICT",
                )
            # No canonical row exists after the query; the idempotency key makes
            # this one bounded retry safe.
            return self.ingest(manifest)

    def ingest_file(
        self,
        path: Path,
        artifact_store_root: Path,
        *,
        entity_type: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        artifact = build_artifact_manifest(path, artifact_store_root)
        manifest = dict(artifact.manifest)
        if entity_type is not None and entity_type != artifact.entity_type:
            raise ControlPlaneClientError("Explicit entity type does not match artifact", code="INVALID_ARTIFACT_IDENTITY")
        if idempotency_key:
            manifest["idempotency_key"] = idempotency_key
        return self.ingest_with_reconcile(manifest)


def reviewed_product_corpus(root: Path) -> list[Path]:
    """Return the current product corpus in dependency-safe registration order."""

    runtime = root / "runtime"
    names = [
        # Run Evidence, including evaluation/focused member runs.
        "reviewed-normal-run-v2.json", "reviewed-response-lost-run-v2.json",
        "reviewed-agent-fail-run.json", "reviewed-agent-fail-reproduction-run.json", "reviewed-environment-error-run.json",
        "reviewed-regression-stability-01-run.json", "reviewed-regression-stability-02-run.json", "reviewed-regression-fixed-candidate-run.json",
        "reviewed-evaluation-baseline-normal-run.json", "reviewed-evaluation-baseline-recovery-run.json", "reviewed-evaluation-baseline-regression-run.json",
        "reviewed-evaluation-candidate-normal-run.json", "reviewed-evaluation-candidate-recovery-run.json", "reviewed-evaluation-candidate-regression-run.json",
        # Final product Failure Case/Regression history; the pre-promotion case
        # is intentionally not silently ingested under the same identity.
        "reviewed-failure-case-promoted.json", "reviewed-regression.json",
        "reviewed-regression-known-bad-result.json", "reviewed-regression-fixed-candidate-result.json",
        "reviewed-evaluation-baseline-regression-result.json", "reviewed-evaluation-candidate-regression-result.json",
        "reviewed-regression-collection.json",
        "reviewed-evaluation-suite.json", "reviewed-evaluation-baseline.json", "reviewed-evaluation-candidate.json",
        "reviewed-evaluation-comparison.json",
        "reviewed-quality-policy.json", "reviewed-quality-gate-baseline.json", "reviewed-quality-gate-candidate.json",
        "reviewed-release-decision-baseline.json", "reviewed-release-decision-candidate.json",
    ]
    paths = [runtime / name for name in names]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise ControlPlaneClientError(f"Reviewed corpus file is missing: {missing[0].name}", code="CORPUS_INPUT_MISSING")
    return paths


def register_reviewed_corpus(
    root: Path,
    artifact_store_root: Path,
    base_url: str,
    *,
    evidence_token: str,
    decision_token: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    evidence_client = ControlPlaneClient(base_url, evidence_token)
    decision_client = ControlPlaneClient(base_url, decision_token)
    for path in reviewed_product_corpus(root):
        artifact = build_artifact_manifest(path, artifact_store_root)
        client = decision_client if artifact.entity_type == "RELEASE_DECISION" else evidence_client
        response = client.ingest_with_reconcile(artifact.manifest)
        results.append({
            "file": path.name,
            "entity_type": artifact.entity_type,
            "entity_id": artifact.entity_id,
            "status": response.get("status", "UNKNOWN"),
            "already_exists": bool(response.get("already_exists", False)),
        })
    return results


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ControlPlaneClientError(f"Required credential environment variable is missing: {name}", code="CLIENT_CREDENTIAL_MISSING")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RunProof formal Control Plane client")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register = subparsers.add_parser("register-reviewed-corpus")
    register.add_argument("--root", type=Path, default=Path.cwd())
    register.add_argument("--artifact-store-root", type=Path, default=Path(os.environ.get("RPF_ARTIFACT_STORE_ROOT", DEFAULT_ARTIFACT_ROOT)))
    register.add_argument("--base-url", default=os.environ.get("RPF_CONTROL_PLANE_URL", DEFAULT_BASE_URL))
    register.add_argument("--evidence-token-env", default="RPF_AUTH_EVIDENCE_TOKEN")
    register.add_argument("--decision-token-env", default="RPF_AUTH_DECISION_TOKEN")
    register.add_argument("--json", action="store_true")

    query = subparsers.add_parser("query")
    query.add_argument("entity_type")
    query.add_argument("entity_id")
    query.add_argument("--base-url", default=os.environ.get("RPF_CONTROL_PLANE_URL", DEFAULT_BASE_URL))
    query.add_argument("--token-env", default="RPF_AUTH_READ_TOKEN")

    args = parser.parse_args(argv)
    try:
        if args.command == "register-reviewed-corpus":
            result = register_reviewed_corpus(
                args.root,
                args.artifact_store_root,
                args.base_url,
                evidence_token=_env(args.evidence_token_env),
                decision_token=_env(args.decision_token_env),
            )
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"REGISTERED {len(result)} reviewed artifacts")
            return 0
        client = ControlPlaneClient(args.base_url, _env(args.token_env))
        response = client.get(args.entity_type, args.entity_id)
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0 if response is not None else 1
    except ControlPlaneClientError as error:
        print(json.dumps({"status": error.status, "error": error.code, "retriable": error.retriable}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
