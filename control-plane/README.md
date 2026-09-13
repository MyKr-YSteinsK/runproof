# RPF-14 Formal Control Plane / Durable Execution

这是 RunProof 的正式 Java/Spring Control Plane 产品模块，不是 `spikes/rpf-09`、`spikes/rpf-10` 或 `spikes/rpf-13` 的重命名。它把 PostgreSQL 作为 canonical metadata 与 durable execution coordination store，把 reviewed/product artifact bytes 放在 `ArtifactStore` 抽象之后，并通过受限的同步 HTTP/JSON API 提供登记、查询、artifact resolution、审计、readiness 和 Job Transport 边界。

## 验证入口

从仓库根目录运行：

```powershell
mvn -q test package -f control-plane/pom.xml
python control-plane/probe.py
$result = Get-ChildItem .local/rpf-14 -Filter probe-result.json -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
python control-plane/verify-evidence.py --result $result.FullName
```

`probe.py` 使用现有 Docker daemon 和 `postgres:16-alpine`，为一次 probe 创建带 `rpf14` 前缀的临时 PostgreSQL container/volume、随机进程内凭据和临时 artifact root；结果与服务日志只写入被忽略的 `.local/rpf-14/`，结束时清理 container/volume、独立 JVM 和 worker 子进程。它覆盖 RPF-11 canonical migration/ingest、Job submit/replay/conflict、真实独立 Python worker、concurrent claim、lease/heartbeat/reclaim/stale fencing、operation identity/response-lost/reconcile、artifact-ingest interruption、cancel/timeout、read API/metrics/retention boundary、服务/数据库重启、`pg_dump`/独立 `pg_restore`、schema mismatch 与 secret redaction。`verify-evidence.py` 只离线核验一个带 schema/source identity 的 PASS 结果。该证据证明当前正式 slice contract，不代表 production HA、租户权限、OAuth/OIDC、Approval、broker、scheduler 或 release/deploy authority。

## 手工启动

正式服务要求显式配置 PostgreSQL 与五个不相同的 service credentials；不会使用 H2 fallback，也不会从前端读取 token：

```powershell
$env:RPF_JDBC_URL = "jdbc:postgresql://127.0.0.1:5432/runproof"
$env:RPF_DB_USER = "runproof"
$env:RPF_DB_PASSWORD = "<process-only-secret>"
$env:RPF_ARTIFACT_STORE_ROOT = "D:\data\runproof-artifacts"
$env:RPF_AUTH_READ_TOKEN = "<read-token>"
$env:RPF_AUTH_EVIDENCE_TOKEN = "<evidence-token>"
$env:RPF_AUTH_DECISION_TOKEN = "<decision-token>"
$env:RPF_AUTH_AGENT_TOKEN = "<agent-token>"
$env:RPF_AUTH_CI_TOKEN = "<ci-token>"
$env:RPF_AUTH_WORKER_TOKEN = "<worker-token>"
java -jar control-plane/target/runproof-control-plane-0.1.0-SNAPSHOT.jar
```

默认监听 `127.0.0.1:8081`，可由 `RPF_CONTROL_PLANE_ADDRESS`、`RPF_CONTROL_PLANE_PORT` 覆盖。服务启动时检查 PostgreSQL identity、`rpf_schema_history`、canonical `rpf-11-postgresql-canonical-schema-v1` 与 additive execution `rpf-14-durable-execution-schema-v1`；不支持的 schema history 会 fail closed。Worker credential 只有 `metadata:read`、`evidence:write`、`execution:worker`，不包含 `decision:write`。

## API 边界

- `/api/v1/health`、`/readyz`、`/capabilities` 是运维/readiness surface；其他 API 需要 bearer service credential。
- `POST /api/v1/ingest/completed-evidence` 接受 completed Run/Evaluation/Failure/Regression/Policy/Gate 等 evidence manifest；仅 `evidence:write` 或 CI candidate 可用。
- `POST /api/v1/release-decisions` 仅接受独立 `decision:write` principal；Control Plane 校验 Decision refs、immutable history 与 `release_executed=false` / `deployment_authorized=false`。
- `/api/v1/runs`、`/failures`、`/regressions`、`/evaluations`、`/comparisons`、`/release-decisions` 及其 detail route 返回 `canonical_metadata` 和 `artifact_resolution`，不把 raw trajectory 写入 PostgreSQL metadata。
- `/api/v1/artifacts/{entityType}/{entityId}` 仅在 hash/schema/identity/source 校验通过后返回 verified artifact；缺失或损坏 artifact 不会被伪装为可用。
- `/api/v1/jobs`、`/api/v1/jobs/{jobId}` 和 `/api/v1/execution-metrics` 提供 Execution read model；`POST /api/v1/jobs` 由 CI submitter 创建 `QUEUED` Job，worker 通过 claim/start/heartbeat、operation prepare/dispatch/reconcile、execution evidence ingest 和 complete/fail-platform 推进状态。Attempt/Event 为 append-only；lease token 只在 claim/heartbeat 的受限响应中返回，read model 只返回 presence，不返回 raw token/hash。
- Durable state 支持 `QUEUED`、`CLAIMED`、`RUNNING`、`CANCEL_REQUESTED`、`RECONCILE_REQUIRED`、`COMPLETED`、`FAILED_PLATFORM`、`CANCELLED`；lease expiry 不是副作用未发生的证明，`UNKNOWN_OUTCOME` 必须 reconcile-before-retry，`COMPLETED` 必须绑定 execution evidence。
- 没有 release/deploy endpoint；`ELIGIBLE` 仍是 decision-only 结果。

## Python client 与 reviewed corpus

统一 client 位于 `runtime/runproof_runtime/control_plane_client.py`，只使用 HTTP/JSON，不直连数据库。它负责 manifest、immutable local artifact copy、认证 header、typed error、idempotent retry 和 transport uncertainty reconcile：

```powershell
python -m runtime.runproof_runtime.control_plane_client register-reviewed-corpus `
  --root . `
  --artifact-store-root .local/control-plane/artifacts `
  --base-url http://127.0.0.1:8081/api/v1 `
  --evidence-token-env RPF_AUTH_EVIDENCE_TOKEN `
  --decision-token-env RPF_AUTH_DECISION_TOKEN `
  --json
python -m runtime.runproof_runtime.control_plane_client query RUN <run-id> `
  --base-url http://127.0.0.1:8081/api/v1 `
  --token-env RPF_AUTH_READ_TOKEN
```

Corpus importer 保留 reviewed JSON 原始 bytes，不会静默覆盖历史 artifact，也不导入 disposable spike output。credential、Authorization、request messages、private reasoning 与自由模型文本不进入 manifest、canonical summary、artifact export、日志或 Web source。

## Formal durable worker

Worker entrypoint 是 `runtime.runproof_runtime.durable_worker`，只通过 `ControlPlaneClient` 的 HTTP/JSON 方法访问正式 Control Plane，不直连 PostgreSQL。它执行 `poll → claim → heartbeat → bounded Evaluation → operation/evidence ingest → terminal finalize`；重启后依据 Job/Operation/Evaluation artifact 边界继续处理，transport uncertainty 先 reconcile，不 whole-run blind retry。

```powershell
$env:RPF_AUTH_WORKER_TOKEN = "<worker-token>"
python -m runtime.runproof_runtime.durable_worker `
  --base-url http://127.0.0.1:8081/api/v1 `
  --token-env RPF_AUTH_WORKER_TOKEN `
  --repo-root . `
  --max-jobs 1 `
  --once `
  --result-path .local/durable-worker-result.json
```

该 worker 当前执行 RPF-07 deterministic Evaluation profiles；它不是生产 scheduler、broker、autoscaling、HA、deploy/release executor 或通用 Agent SDK。RPF-12 CI 使用同一正式 worker mechanism，durable path 失败时不会 silent fallback 到 direct Evaluation。
