# RunProof Reliability 模型

[English](RELIABILITY_MODEL.md) | [简体中文](RELIABILITY_MODEL.zh-CN.md) | [架构](ARCHITECTURE.zh-CN.md)

RunProof 分开表达 Agent 做了什么、平台能够证明什么，以及策略允许得出什么结论。这种分离就是 Reliability contract。

## 结果词汇

| Status | 含义 | Quality denominator |
|---|---|---|
| `PASS` | 必需结果和 invariants 已被验证 | 如果可归因于 Agent，则进入有效 Agent result |
| `FAIL` | Agent 行为违反 Scenario invariant 或预期结果 | 有效 Agent result；可成为 Failure Case 或 Regression |
| `ERROR` | Agent contract 之外的平台、Provider、Environment 或执行基础设施故障 | 保留在 attempt/evidence history，不计入 Agent quality 成功率 |
| `INVALID` | Scenario、verifier、identity 或 input 对本次评测无效 | 保留在 attempt history，不是有效 Agent trial |
| `INCONCLUSIVE` | 证据不足以安全决策 | 阻断或要求 review；不能静默变成 PASS |
| `CANCELLED` | 在有效结论前有意停止执行 | 保留在 attempt history，不是有效 Agent trial |
| `UNKNOWN_OUTCOME` | 可能发生副作用，但 response/receipt 不确定 | 必须先 reconcile 再 retry |
| `RECONCILE_REQUIRED` | 继续动作前必须检查 environment 或 receipt | 在 reconcile 前是 safety blocker |

`Agent FAIL != Platform ERROR`。即使 point estimate 很高，只要存在 safety violation 仍然必须阻断：safety precedence 高于单个比例。

## Evidence 与调查链

```text
Observed Fact
    → Verified Result
    → Failure Case（可复现 identity）
    → Regression（显式预期行为）
    → Failure Intelligence（归因 / family / first divergence）
    → Statistical Evaluation（重复观察）
    → Quality Gate
    → Release Decision（只读决策）
```

- **Run** 是一次执行，带有 Agent、Scenario、Environment、Verifier、timeline、state 和 outcome identity。
- **Trajectory / State Diff** 解释可观察 action 和状态迁移，不依赖模型私有 reasoning。
- **Evidence** 保存经验证的原始事实和稳定引用；派生结论必须能回指原始事实。
- **Failure Case** 是可复现且经过验证的失败 identity，不会自动成为 Regression。
- **Regression** 增加显式预期、复现、稳定性和 focused-rerun 历史。
- **Failure Intelligence** 提供确定性归因、first meaningful divergence、exact grouping、structural family 和版本定位，不自动 promotion 或 release。

## Artifact integrity 与存储

Artifact bytes 与 canonical metadata 是分开的 reliability boundary。
PostgreSQL 仍是 identity、schema、source identity 与 RunProof SHA-256 的
canonical 注册来源。正式 `S3ArtifactStore` 是 additive 且必须显式选择的
backend；`LocalFileArtifactStore` 仍是默认路径，错误 backend 配置 fail closed。
Conditional immutable create、同 bytes replay、不同 bytes conflict 和 bounded
unknown-write reconcile 共同保持 artifact identity contract。Verified object
read 只做一次 GET 并验证 body；ETag 或对象存在本身不能当作 evidence。

metadata commit 之前上传的对象是 orphan，不是 canonical evidence。HTTP/JSON
Worker upload 需要认证，并与 Agent authority 分离。SeaweedFS `4.47` 是
disposable compatibility proof，不是 live Production durability、HA、replication
或 release 结论。

## Safety 与恢复

可能发生副作用后丢失 response 时：

```text
可能已经发生副作用
        → UNKNOWN_OUTCOME
        → RECONCILE_REQUIRED
        → 检查 receipt/state
        → 证明 effect count 和最终 invariant
        → 安全恢复或停止
```

Lease 过期不能证明副作用没有发生。Worker 必须 fence stale attempt、reconcile environment state，并保留 operation identity。无法证明安全恢复时，禁止盲目 whole-run retry。

## 正式 Network Fault Profile

RPF-28 新增正式 `multi-service-toxiproxy-v1` Environment，但不替换单容器 Environment。每次 Run 拥有 fresh 的 Docker internal network，包含 target、dependency、Toxiproxy boundary 和 Agent-shaped client。Client 只能访问 data-plane proxy；fault activation 和 toxic configuration 始终属于 harness authority。

versioned `rpf-network-fault-profile-v1` 区分 `none`、`latency`、`timeout`、`dependency-unavailable`、`response-lost` 与 `pre-side-effect-failure`。Evidence 分开记录 `planned`、`triggered`、`observed`、`reconciled`。side effect 已提交但响应丢失时，必须证明 client 没有收到成功响应、存在稳定 operation receipt、effect 恰好一次，并先 reconcile 再 retry。依赖或 side-effect 前失败则必须证明对照关系：没有 receipt 且 effect 为零。Readiness、initial state、fault reset 和 cleanup 都属于 terminal proof；cleanup 无法验证时 Environment 必须 quarantine。

## 可选 OpenTelemetry 诊断合同

RPF-30 增加正式但可选的 OpenTelemetry 路径。Telemetry disabled、外置
Collector 健康、Collector 不可用三种情况下，canonical execution semantics
必须一致。disabled 路径是真正 no-op，不启动 exporter thread；enabled export
使用有界异步路径，queue drop/export failure 只形成诊断健康信号。它们不能
把 Run 改成 `FAIL`、阻止 terminal Evidence、触发盲目 retry，也不能阻塞
`UNKNOWN_OUTCOME` reconcile。

W3C `traceparent` 和有限 allowlist 的 W3C Baggage 用来关联 Java Control
Plane、durable Job/Attempt、Python Worker、Agent/Tool、RPF-28
target/dependency 与 verifier。canonical `job_id`、`attempt_id`、`run_id`、
`environment_id`、`operation_id` 仍是独立 identity；trace/span ID 不能成为
业务主键。Attempt reclaim 保留 Job correlation、创建新的 Attempt subtree，
并可用 link 关联旧 Attempt，但不能伪装为同一次执行。

response-lost trace 只用于调查：当 target receipt、effect count、reconcile
和 verifier 证明 Scenario 时，error span 可以与 Agent `PASS` 同时存在。
Telemetry completeness 可以是 `COMPLETE`、`PROPAGATION_MISSING` 或
`EXPORT_UNAVAILABLE`；缺失 propagation 会被检测，但对 canonical Run
fail-open。Attribute 与 metric label 均采用低 cardinality allowlist，不能
包含 credential、prompt、body、private reasoning、本机私有路径，也不能把
canonical ID 用作 metric label。Collector 是可选的 pinned 验证 fixture；
没有 trace UI、长期 retention 或 Jaeger/Tempo/Grafana 产品依赖。

## Statistical Reliability

Statistical evaluation 与单次 Evaluation/Comparison 分离。Sampling Plan 固定 trial 数、attempt budget、Agent/config、Scenario、environment sequence、metric 定义以及 Wilson method/version。

- 有效 Agent denominator 只包含 `AGENT_PASS + AGENT_FAIL`。
- Platform/Environment、Invalid、Inconclusive 和 Cancelled 保留在 attempted/evidence denominator 与 trial matrix 中，但不成为 Agent success 或 failure。
- 必须满足 minimum valid sample；当策略要求更大 denominator 时，不能用 `1/1` 或 `3/3` 通过。
- Wilson score interval 描述受控观察；当前 deterministic corpus 不是 live Provider probability 估计。
- `OBSERVED_FLAKY` 是 review observation，不是自动概率声明。
- zero-tolerance safety event、harmful remediation、authority violation、Historical Regression failure 或 `UNKNOWN_OUTCOME` 后盲目 retry 都是 hard blocker。

Comparison 分类为 `IMPROVED`、`REGRESSED`、`NO_CLEAR_DIFFERENCE` 或 `INCOMPARABLE`，依据兼容的 plan、证据充分性和 interval relationship，而不是只看 point estimate。

## Quality Policy 与 Release Decision

当前 precedence 为：

```text
HARD_BLOCKER → EVIDENCE_INSUFFICIENT → REVIEW_REQUIRED → ELIGIBLE
```

`ELIGIBLE`、`BLOCKED`、`REVIEW_REQUIRED`、`INCONCLUSIVE` 属于 Release Decision 域，不是 Run outcome 域。Decision 记录到达状态的原因，并链接 Evaluation、Comparison、Regression、Failure 和 Evidence refs；它绝不授予 deployment authority。

## 当前证据边界

reviewed corpus 在两个显式 Agent、正式多服务网络故障 Environment、Failure Intelligence、统计 cohort 和 PostgreSQL durable Trial Job 上证明了 deterministic controlled semantics，但没有证明长期 live Provider reliability、Production 规模的统计显著性、Production remediation safety 或 HA。source identity 和 verification anchor 见 [VERIFICATION_HISTORY.zh-CN.md](history/VERIFICATION_HISTORY.zh-CN.md)。
