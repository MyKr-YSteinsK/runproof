# RPF-09 Control Plane Persistence / API Boundary Spike

RPF-09 是从 Prototype 进入 Stabilization 的 investigation，不是正式后端产品实现。它验证最小的 Java/Spring Control Plane、canonical metadata、immutable artifact reference 和 Python Runtime → HTTP/JSON ingestion boundary；不引入 Queue、scheduler、durable worker 或 release/deploy endpoint。

## Reproduce

从仓库根目录运行：

```powershell
mvn -q test package -f spikes/rpf-09/control-plane/pom.xml
python spikes/rpf-09/probe.py
```

Probe 会启动一个独立的 Spring Boot JVM，将 reviewed Run、Evaluation 和 Release Decision 复制到忽略的 `.local/rpf-09/<probe>/artifacts/`，把 H2 文件数据库写入同一临时目录，并在结束时回收 JVM。结果 JSON 与服务日志均不提交。

当前本机 evidence：Windows 11 x64、Java/JDK 17.0.12、Maven 3.9.16、Python 3.14.6、Node 24.16/npm 11.13；Spring Boot 3.4.5、H2 2.3.232。Docker CLI 存在但 daemon 未运行，宿主机没有 `psql`，因此本轮没有冒充 PostgreSQL/Docker 证据。

## Probe contract

### Persistence candidate

- `rpf-09-metadata-schema-v1` 由显式 migration 创建 `rpf_schema_history` 与 `canonical_metadata`。
- H2 2.3.232 file mode 只保存 canonical summary：`entity_type`、`entity_id`、outcome、agent/evaluation summary、artifact key/kind/schema/content hash/source hash/runtime version、idempotency key 和 created time。
- 数据库不保存完整 trajectory、raw JSON 或长文本 artifact；服务返回的 read model 也不包含 raw artifact。
- `(entity_type, entity_id)` 是 immutable canonical identity；`idempotency_key` 具备数据库唯一约束。
- 同一 identity + 同一 artifact fingerprint 是 `IDEMPOTENT_REPLAY`；同一 identity + 不同 artifact content/source/schema fingerprint 返回 409 `IDENTITY_CONTENT_CONFLICT`，不 update-in-place。
- `fail_after_write=true` 只用于 disposable rollback probe，验证事务异常后没有残留 metadata。

### Artifact reference

Python 端的最小 immutable writer 以 store key 写入 artifact；相同 bytes 可重复登记，不同 bytes 覆盖同 key 会被拒绝。Java registry 仅接受相对 store key，并在 ingest/query 时验证：

1. entity type 与允许的 schema/kind；
2. artifact id 与 entity id；
3. relative path 未越过 store root；
4. content SHA-256；
5. JSON header、嵌套 entity identity；
6. source SHA-256 与 runtime version。

因此 metadata → artifact ref 是可解析且可验证的；artifact 缺失、hash 改变、JSON/header/source identity 损坏时，API 返回明确的 422 invalid-evidence error，不返回伪造的完整事实。

### HTTP/JSON boundary

服务只接受受约束的 completed-result manifest，不接受 raw artifact 作为 metadata contract 的唯一输入：

```json
{
  "manifest_schema_version": "rpf-control-plane-ingest-v1",
  "entity_type": "RELEASE_DECISION",
  "entity_id": "release-decision-rpf08-candidate",
  "outcome": "ELIGIBLE",
  "agent_version": "1.0.1-observe-before-mutation-fix",
  "evaluation_id": "evaluation-…",
  "idempotency_key": "RELEASE_DECISION:…:sha256",
  "artifact_ref": {
    "artifact_id": "release-decision-rpf08-candidate",
    "artifact_key": "release-decision-candidate.json",
    "artifact_kind": "Release Decision",
    "schema_version": "rpf-release-decision-v1",
    "content_sha256": "…",
    "source_sha256": "…",
    "runtime_version": "rpf-08.v1"
  }
}
```

Endpoints exposed by the disposable candidate:

- `GET /api/v1/health`：health/readiness 与 migration version；
- `POST /api/v1/ingest/completed-evidence`：验证 artifact 并 transactionally 登记 metadata；
- `GET /api/v1/runs/:id`、`/evaluations/:id`、`/release-decisions/:id`：summary + verified artifact resolution；
- `GET /api/v1/release-decisions`：只读 Decision list；
- `GET /api/v1/probe/boundary`：明确 synchronous HTTP/JSON、无 Queue/job transport、无 release authorization；
- `POST /api/v1/probe/shutdown`：仅供 probe 回收 JVM，不属于产品 API。

## Actual evidence

最近一次 `python spikes/rpf-09/probe.py` 通过，结果包括：

| Experiment | Observed result |
| --- | --- |
| Spring process health/readiness | `UP` / `READY`; H2 responding; schema `rpf-09-metadata-schema-v1` |
| Python → Java cross-process path | Run、Evaluation、Release Decision 三类 manifest 均 `INGESTED`；canonical metadata 不含 raw artifact |
| Stable reference | 三类 summary query 均重新解析并验证 immutable artifact ref |
| Duplicate ingestion | `200 IDEMPOTENT_REPLAY` |
| Same identity / different content | `409 IDENTITY_CONTENT_CONFLICT` |
| Transaction rollback | forced write 后 query 为 `404 CANONICAL_METADATA_NOT_FOUND`；随后正常 ingest 成功 |
| Missing / corrupted artifact | ingest/query 均 fail closed：`INVALID_EVIDENCE_ARTIFACT_MISSING` / `INVALID_EVIDENCE_ARTIFACT_HASH_MISMATCH` |
| Unknown schema | `422 INVALID_EVIDENCE_UNKNOWN_SCHEMA` |
| Service restart | metadata、artifact refs 与两条 Release Decision history 均恢复 |
| Transport failure | 停止服务后的连接失败分类为 `RETRIABLE_TRANSPORT_FAILURE` |
| Boundary | `SYNCHRONOUS_HTTP_JSON`; `job_transport_resolved=false`; release/deploy authorization=false |

## Ownership and update model

| Fact | Canonical metadata | Immutable artifact / ref | Writer / owner | Update semantics |
| --- | --- | --- | --- | --- |
| Agent Version / Scenario Version | identity、version、source refs | full versioned definition when needed | Agent/Evaluation authoring; Control Plane registers | new version only |
| Environment provenance | environment id、revision、provider summary、readiness identity | full environment/run evidence | Environment provider + Runtime | append evidence; no rewrite |
| Run | run id、outcome、attribution、evaluation id、artifact ref | trajectory、tool/fault/transition、verification | Python Runtime writes completed result; Control Plane ingests | immutable; later reconcile/annotation is additive |
| Failure Case | signature、workflow status、source/reproduction refs | failure observation/evidence details | Investigation workflow | state transition with audit; no overwrite of evidence |
| Regression | regression id/version/status/promotion refs | contract, focused results and evidence | Regression workflow | new result/version; promotion history additive |
| Evaluation Suite | suite identity/version/member refs/digest | frozen suite manifest | Evaluation authoring/orchestrator | versioned definition |
| Evaluation | evaluation id/status/counts/coverage/refs | member result and run refs | Python Evaluation Runtime | completed result immutable |
| Comparison | comparison id/status/aggregate/ref summary | member diff details | Evaluation/Comparison Runtime | new comparison for new inputs |
| Quality Policy | policy identity/version/registry ref | versioned rules and source identity | Policy/Control Plane boundary | new policy version; no silent replacement |
| Gate Evaluation | gate id/status/diagnostic refs | full deterministic rule results | Quality evaluator | immutable evaluation |
| Release Decision | decision id/status/subject/policy/gate refs/supersedes | full decision evidence | Control Plane decision boundary; approval authority remains separate | append-only; superseding decision, never update-in-place |
| Web read model | none; derived DTO projection | none | API adapter | disposable/cacheable, never canonical |

The table describes the next service ownership target, not a claim that all writers already exist in the repository. The current probe only implements the Run/Evaluation/Release Decision registration slice.

## Decision packet

### Recommendation

1. Keep PostgreSQL as the v1 canonical metadata candidate. The real H2 probe validates relational schema, transaction and restart semantics, but does not validate PostgreSQL dialect, operations, HA, backup or production performance.
2. Keep raw/large evidence in a file/object artifact store behind an immutable registry. Canonical metadata stores only verified identity, outcome/summary and stable artifact refs; a future store may use content-addressed keys and object retention policy.
3. Confirm D-008 at prototype level: Spring Boot is a viable deterministic Control Plane candidate and Python remains the Agent/Evaluation Runtime. The cross-process probe is evidence for the boundary, not a complete production architecture.
4. Use synchronous HTTP/JSON for the first completed-result ingestion and read model. It is not TU-005 Job Transport; Queue, retry scheduling, leases and durable execution remain separate decisions.
5. Use `(entity_type, entity_id)` plus immutable artifact fingerprint for idempotency. Retries are safe only with the same identity/fingerprint and idempotency key; different content is a conflict/quarantine path.
6. Make Release Decision history append-only. Later evidence or Policy versions create a new Decision with `supersedes_decision_id`; no Agent/runtime or `ELIGIBLE` result can authorize release.

### API/read-model migration

The Web adapter can consume API-style `canonical_metadata` + `artifact_resolution` DTOs and map them to the existing Release Decision list view model without knowing database columns. The compatibility proof is in `web/src/data/controlPlaneReadModel.ts` and its Vitest test. A future migration can register existing reviewed artifacts by manifest, preserve their original schema/source/content identity, and switch the data source in `web/src/data` without rewriting presentation components. Historical artifacts must not be copied into a mutable metadata blob or silently rewritten.

### Error and retry boundary

| Class | Examples | Retry / handling |
| --- | --- | --- |
| Request validation | unknown manifest schema, missing required field | non-retriable 400; fix caller |
| Identity conflict | same entity id with different content | non-retriable 409; quarantine/new version/superseding decision |
| Invalid evidence | missing, corrupt, unknown schema, path/hash/source mismatch | non-retriable 422; do not count as Agent FAIL |
| Metadata not found | unknown query identity | 404; caller/read model decides whether to refresh |
| Platform/storage | database unavailable | 503 `retriable=true`; retry only with idempotency contract |
| Transport | Control Plane process/network unavailable | retriable transport; reconcile/query before resubmitting |

### Remaining boundary

TU-004 Durable Run、TU-005 Job Transport、durable resume/lease/checkpoint、CI provider integration, auth/tenant/approval authority, artifact object-store durability/retention, PostgreSQL compatibility/operations, observability and production release architecture remain open. No release/deploy authorization was added by this Spike.

## Recommended next formal boundary

Development Architect should approve a focused Control Plane persistence implementation plan covering PostgreSQL migration compatibility, artifact-store abstraction, authenticated idempotent ingest, Run/Evaluation/Decision read endpoints, and additive history. It should still exclude Queue/scheduler/durable worker, approval service and production release execution. A Checkpoint Review is recommended before that implementation because PostgreSQL remains an unexecuted external candidate and Release Decision authority must be assigned explicitly.
