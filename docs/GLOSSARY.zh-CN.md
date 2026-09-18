# RunProof 术语表

[English](GLOSSARY.md) | [简体中文](GLOSSARY.zh-CN.md) | [Reliability 模型](RELIABILITY_MODEL.zh-CN.md)

RunProof 在 identifier、raw evidence、route 和 status value 中保留下面的 English technical terms。Web 可以增加本地化解释，但翻译不会改变 canonical bytes。

| Term | RunProof 中的含义 |
|---|---|
| Agent | 被评测的版本化 actor；其行为与平台/环境健康度分开评估。 |
| Agent Version | Agent 的行为 identity，包括 model/provider reference、prompt/config、tool/runtime revision 和 contract version。 |
| Run | 一次绑定 Agent、Scenario、Environment、Verifier、timeline、state 和 outcome identity 的执行。 |
| Trajectory | 可观察的 action、tool call/result、fault、transition、retry、recovery 和 outcome fact；不包含私有 chain-of-thought。 |
| State Diff | 对相关 environment state 的经验证 before/after 比较。 |
| Controlled Simulation Environment | 为安全副作用和 fault scenario 提供的 fresh、owned、可观察环境。 |
| Evidence | 支持结论的经验证原始事实与稳定引用。 |
| Failure Case | 带 source/reproduction 和 evidence refs 的可复现、经过验证的失败 identity。 |
| Regression | 带显式 promotion、stability 和 focused-rerun evidence 的历史预期行为。 |
| Failure Intelligence | 确定性 attribution、first meaningful divergence、exact grouping、structural family 和 version location；不能自动 promotion 或 release。 |
| Exact signature | 同一 failure bytes/contract 的稳定 identity；历史 signature 语义必须保留。 |
| Structural family | 更宽的确定性 recurrence group；不能抹掉 domain 或 exact Failure Case identity。 |
| Version Bisect | 在兼容的 Regression oracle 下 fail-closed 定位 first bad candidate。 |
| Statistical Evaluation | 按冻结 Sampling Plan 重复执行的受控 trial；不是 live Provider probability 估计。 |
| Valid Agent denominator | `AGENT_PASS + AGENT_FAIL`，用于 Agent quality。 |
| Attempted/evidence denominator | 所有相关 attempted/evidence observation，包括 platform、invalid、inconclusive 和 cancelled。 |
| Wilson score interval | 当前受控统计合同使用的 interval method。 |
| `OBSERVED_FLAKY` | 不一致结果的 review observation，不是自动 live probability 声明。 |
| Quality Policy | 用于评估 evidence sufficiency、blocker、warning 和 review 的版本化规则与 precedence。 |
| Release Gate | 产生 decision input 的策略评估边界。 |
| Release Decision | 独立的 immutable 或 superseding decision record；`ELIGIBLE` 只是只读决策结果。 |
| `UNKNOWN_OUTCOME` | 可能发生副作用，但 response/receipt 不确定。 |
| `RECONCILE_REQUIRED` | retry 或新的副作用前必须 reconcile environment/receipt。 |
| `PASS` / `FAIL` | 证据有效且可归因时的 Agent-facing execution outcome。 |
| `ERROR` | Agent quality contract 之外的平台、Provider、Environment 或执行故障。 |
| `INVALID` / `INCONCLUSIVE` / `CANCELLED` | 无效、不足以决策或有意停止的 execution state。 |
| Control Plane | 正式 Java/Spring API 与 canonical metadata authority，供 Web、worker、seed 和 CI 使用。 |
| Artifact Store | 保存经验证 evidence bytes 的 immutable storage boundary。 |
| Durable Worker | 独立进程，负责 claim Job、fence attempt、reconcile uncertain operation 和报告 evidence。 |
| Observability signal | 正式 OpenTelemetry boundary 产生的可选诊断 telemetry；不是 canonical Evidence、Quality Gate input 或 Release authority。 |
| Trace identity | 用于关联的 OpenTelemetry `trace_id` / `span_id`；与 RunProof 的 Job、Attempt、Run、Environment、Operation identity 分离。 |
| Telemetry completeness | 有界诊断状态，例如 `COMPLETE`、`PROPAGATION_MISSING` 或 `EXPORT_UNAVAILABLE`；不会改变 canonical Run outcome。 |
| W3C Baggage allowlist | 允许跨服务传播的少量低风险 correlation key；排除 secret、prompt、body、reasoning 和 error narrative。 |
| Golden Demo | 本地 reviewed-evidence walkthrough 与 lifecycle boundary，不是 Production deployment。 |

## 命名规则

公共文档使用 English canonical filename，并以 `.zh-CN.md` 作为中文配对文件。Governance 保持 single-source：`AGENTS.md`、`docs/project/PROJECT_BRIEF.md`、`docs/project/DECISIONS.md` 和 `docs/project/CURRENT_STATE.md` 不复制为翻译版 Project-State 文件。
