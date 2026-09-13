# RPF-13 Durable Run Execution / Job Transport Spike

RPF-13 是一个 disposable Investigation / Spike。它在真实 `postgres:16-alpine` 上运行一个最小 Spring/JDBC candidate，调查 Run/Evaluation execution lifecycle、worker claim/lease、attempt fencing、side-effect reconcile 与未来 CI 的 submit/poll 边界。它不是正式 Control Plane 的改名，也不是生产 scheduler、broker、durable worker 或 release service。

## 验证入口

从仓库根目录运行：

```powershell
mvn -q test package -f spikes/rpf-13/control-plane/pom.xml
python spikes/rpf-13/probe.py --run
python spikes/rpf-13/verify-evidence.py
```

Probe 使用现有 Docker daemon 创建带 `rpf13` 前缀的临时 named volume/container，并在 `finally` 中清理。数据库密码只存在于 probe、JVM 与 container environment；结果、HTTP body、job payload 和日志不包含 credential、Authorization、request messages、private reasoning 或自由模型文本。运行副本只写入被忽略的 `.local/rpf-13/`；`reviewed-evidence.json` 是脱敏固定样本，不由 probe 自动覆盖。

最近一次 reviewed 证据在 Windows 11 / Java 17 / Python 3.14 / Docker PostgreSQL 16.15 上完成；固定样本源码身份由 `verify-evidence.py` 重新计算，不接受修改 candidate 后继续冒充旧 evidence。

## Decision packet

### Durable execution state

| State | 含义 | 是否终态 | 关键规则 |
| --- | --- | --- | --- |
| `QUEUED` | 已 durable submit，等待 worker | 否 | 可由 poll/claim 获取 |
| `CLAIMED` | 某个 worker 持有 lease，尚未声明开始 Agent | 否 | lease 过期且没有不确定 operation 才可 re-claim |
| `RUNNING` | 当前 attempt 已开始 | 否 | owner mutation 必须通过 fencing |
| `CANCEL_REQUESTED` | operator 请求取消，等待 worker 到安全边界 | 否 | 不能把 request 当作已取消 |
| `RECONCILE_REQUIRED` | 可能已发生 side effect，或 timeout/lease expiry 无法证明未发生 | 否 | 禁止 blind mutation retry，先按 operation/environment reconcile |
| `COMPLETED` | execution 已绑定 terminal evidence | 是 | job row 不再 claim；evidence append-only |
| `FAILED_PLATFORM` | 平台/worker/storage/timeout terminal outcome | 是 | outcome 可为 `ERROR`/`INCONCLUSIVE`，不转成 Agent `FAIL` |
| `CANCELLED` | queued cancel 或 worker 安全确认后的 terminal outcome | 是 | terminal evidence 必须为 `CANCELLED` |

Job state 是可更新的 coordination projection；每次状态/lease mutation 都递增 `version`，owner mutation 同时提交 `attempt_id`、`worker_id`、`lease_token` 和当前 `lease_version`。`rpf_execution_event` 是 append-only transition history。Terminal job 不 re-claim，后续解释只能创建新 evidence/superseding identity，不能 update-in-place 覆盖已完成 evidence。

### Execution / evidence boundary

`rpf_execution_job` 保存 logical job 的可变生命周期和有限 metadata/ref；`rpf_execution_attempt` 保存每次 worker lease 的身份和结果；`rpf_execution_operation` 保存 state-changing Tool operation identity；`rpf_simulated_effect` 是本 probe 的可查询 controlled environment receipt；`rpf_execution_evidence` 保存 immutable `entity_type/entity_id/content_sha256/artifact_ref`。execution retry 只增加 attempt，不覆盖已有 evidence；相同 evidence fingerprint replay 是幂等，其他 fingerprint 是 conflict。

Job payload 只允许 Evaluation/Scenario/Agent/source/artifact 等 reference metadata。它不承载 prompt、messages、Authorization、token、secret、password、credential、private reasoning 或 hidden CoT。Candidate 没有 Release Decision、Approval、deploy 或 release endpoint。

### Identity and lease contract

| Identity | 生命周期 / 用途 |
| --- | --- |
| `job_id` | logical execution identity；跨 attempt 保持不变 |
| `idempotency_key` + `request_fingerprint` | submit/replay identity；同 fingerprint replay，不同 fingerprint conflict |
| `target_type` + `target_id` | Run/Evaluation target；future CI 以 stable ref 关联 canonical evidence |
| `attempt_id` + `attempt_number` | 一次 worker execution identity；每次 safe re-claim 新建 |
| `worker_id` | worker instance identity；不授予 release authority |
| `lease_token` + `lease_version` | owner/fencing contract；token 只在 claim/heartbeat 响应给 worker，DB 仅存 SHA-256 |
| `operation_id` | state-changing operation identity；重试/恢复保持不变，避免重复 side effect |
| `correlation_id` | submit/CI/trace correlation；不是授权凭据 |

Lease 由 PostgreSQL row lock + `SELECT ... FOR UPDATE` 保护。claim 只在当前 lease 不存在或已 expiry 时尝试；heartbeat 延长 lease 并提高 `version`。旧 attempt 即使仍运行，也无法用旧 token/version finalize 当前 job。Lease expiry 本身绝不证明 side effect 未发生。

### Claim / retry / reconcile contract

- `QUEUED` → `CLAIMED` → `RUNNING` 是 execution state；`complete` 必须先拥有当前 fenced attempt，并且所有 operation 已 `CONFIRMED` 或 `NOT_SUBMITTED`。
- `PREPARED` 表示 operation identity 已持久化但尚无未发送证据；worker crash 后保守进入 `RECONCILE_REQUIRED`。只有显式 durable `NOT_SUBMITTED` 或 environment reconcile 证明未发生，才允许安全 retry。
- `IN_FLIGHT` / `UNKNOWN_OUTCOME` 表示请求可能已成功；expiry 后转 `RECONCILE_REQUIRED`，必须查询 operation/environment/receipt。`CONFIRMED` 之后再次 apply 只返回 `IDEMPOTENT_REPLAY`，不能产生第二个 effect。
- `UNKNOWN_OUTCOME` 可以由新的 worker process 标记并 reconcile；reconcile 后 `CONFIRMED` 不允许 retry，`NOT_SUBMITTED` 才可使用相同 `operation_id` 重试。无法证明时保持 reconcile/inconclusive，不伪装 Agent `FAIL`。
- Control Plane/DB unavailable 返回 retriable platform error；worker 不把 storage/transport failure 写成 Agent result。

## Crash matrix 结果

| 场景 | 结果 |
| --- | --- |
| A. claim 后、Agent 未启动 crash | lease expiry → safe re-claim；不产生 Agent `FAIL` |
| B. Agent started、state-changing action 前 crash | 无 operation effect，可由新 attempt 继续；evidence 不重复 |
| C. send 前 crash | 只有 durable `NOT_SUBMITTED` 证明存在时才 re-claim/retry；operation id 保持不变 |
| D. side effect 成功、response lost、worker process crash | 新 owner 先看到 `RECONCILE_REQUIRED`，标记 `UNKNOWN_OUTCOME`，查询 effect receipt 后 `CONFIRMED`；后续 apply 是 replay，effect count 保持 1 |
| E. artifact 生成、Control Plane ingest 前 process crash | artifact ref/fingerprint 可再次 ingest；same fingerprint `IDEMPOTENT_REPLAY`，attempt/evidence 不重跑/覆盖 |
| F. DB/Control Plane 暂时不可用 | HTTP 503 / retriable platform boundary；PostgreSQL 和 candidate JVM restart 后 completed job 可读回 |

## Candidate API

本 candidate 的最小 HTTP/JSON boundary 是：

```text
POST /api/v1/jobs
GET  /api/v1/jobs/{jobId}
POST /api/v1/jobs/{jobId}/claim
POST /api/v1/jobs/{jobId}/start
POST /api/v1/jobs/{jobId}/heartbeat
POST /api/v1/jobs/{jobId}/operations
POST /api/v1/jobs/{jobId}/operations/{operationId}/not-submitted
POST /api/v1/jobs/{jobId}/operations/{operationId}/apply
POST /api/v1/jobs/{jobId}/operations/{operationId}/confirm
POST /api/v1/jobs/{jobId}/operations/{operationId}/unknown
POST /api/v1/jobs/{jobId}/operations/{operationId}/reconcile
POST /api/v1/jobs/{jobId}/evidence
POST /api/v1/jobs/{jobId}/complete
POST /api/v1/jobs/{jobId}/fail-platform
POST /api/v1/jobs/{jobId}/cancel
POST /api/v1/jobs/{jobId}/cancel/ack
POST /api/v1/jobs/{jobId}/timeout
```

这是 disposable local candidate，未把 service bearer、user login、OAuth/OIDC/SSO 或 tenant/RBAC 伪装成已解决的产品合同。未来正式 API 必须在现有 D-015/D-016 authority 边界上补充 scoped worker/CI identity；worker 只能执行/报告，不能写 Release Decision 或 deploy authority。

## Transport conclusion

### Candidate A — selected for the next formal boundary

PostgreSQL-backed durable job state + worker poll/claim 已由真实实验支持：row lock 确保 concurrent claim 只有一个 owner；lease/version/token 防 stale finalize；append-only attempts/events 保留 crash history；operation identity + environment receipt 负责 at-least-once 下的 reconcile。它复用现有 PostgreSQL candidate，local/CI reproducibility 好，组件数和运维成本较低。

### Candidate B — deferred

Independent broker/queue + PostgreSQL canonical execution state 没有在本 Spike 中实现，因为当前 v1 scale 和已验证 failure semantics 并不需要 broker 才能成立；broker 不会自动提供 side-effect exactly-once。只有测得的吞吐/延迟、延迟投递、fan-out、跨服务背压或 broker-specific operational requirement 出现后，才重新开展 Candidate B spike。引入 broker 之前仍必须保持 PostgreSQL canonical execution state 和 operation reconcile contract。

结论是：`POSTGRESQL_POLL_CLAIM_LEASE` 推荐进入下一份正式实现 Plan，但不等于 production HA、scheduler、autoscaling、multi-region、exactly-once 或 retention policy 已完成。

## TU / CI / operator boundary

- `TU-004 Durable Run Execution`：在 prototype investigation scope 已解锁为 `UNLOCKED_FOR_NEXT_FORMAL_IMPLEMENTATION`；正式实现仍需把 candidate state/lease/operation/evidence contract 纳入 product Control Plane，并补充 worker lifecycle、retention、observability 和 auth。
- `TU-005 Evaluation Job Transport`：推荐 `POSTGRESQL_POLL_CLAIM_LEASE`；broker 暂缓，等待真实容量/拓扑证据。
- Future CI：submit Evaluation job → 获得 `job_id` → poll/query `QUEUED/CLAIMED/RUNNING/RECONCILE_REQUIRED` → terminal 后读取 stable evidence refs，再由既有 RPF-12 canonical Control Plane read API 读取 Evaluation/Decision。timeout/platform error fail closed；CI 不直写 DB、不伪造 `ELIGIBLE`、不写 Decision、不 deploy/release。
- Operator/read model：job query 已表达 state、worker、attempt、lease status、operation、reconcile、terminal outcome、platform reason、evidence 和 append-only events；完整 Web UI 留待后续正式 Plan，不在本 Spike 中实现。

## Next formal Plan boundary

下一份正式实现 Plan 应限定为：formal Control Plane execution schema/API、Python durable worker adapter、fenced claim/heartbeat、operation reconcile interface、immutable evidence ingest、worker/CI scoped authority、terminal/read model、crash/restart integration tests、retention/observability 设计，以及将 RPF-12 direct Evaluation 迁移成 submit/poll/read contract 的最小 CI slice。它不应顺手引入 broker、生产 scheduler、HA/leader election、Approval 或 deploy/release endpoint；这些仍需独立决定和证据。
