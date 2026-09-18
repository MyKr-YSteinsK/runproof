# RunProof 能力历史

[English](CAPABILITY_HISTORY.md) | [简体中文](CAPABILITY_HISTORY.zh-CN.md) | [验证历史](VERIFICATION_HISTORY.zh-CN.md)

本文是能力级历史，不是 Plan 日志。它解释当前 Stabilization 边界如何逐步形成；详细 evidence anchor 见 [VERIFICATION_HISTORY.zh-CN.md](VERIFICATION_HISTORY.zh-CN.md)。

| 阶段 | 已形成的能力 | 保留的边界 |
|---|---|---|
| Bootstrap 与 probes | Agent contract、最小 Controlled Environment 与 Provider/error classification 实验 | Probe 是 disposable evidence；Docker 不是永久 Production identity |
| 有状态 Run slice | Production Change reference Agent、Scenario、Tool loop、Docker state、response-loss reconcile 和 Run Evidence | 没有通用 Agent SDK、streaming/thinking continuation 或真实破坏性 Production operation |
| Evidence 与调查 | Timeline、State Diff、Failure Case、Regression promotion、focused rerun 和只读 Web 调查 | Source evidence 不能静默改写；`FAIL` 与 `ERROR` 保持分离 |
| Evaluation 与 policy | Evaluation Suite、Baseline/Candidate Comparison、Quality Policy、Release Gate 和只读 Release Decision | `ELIGIBLE` 不是 deploy/release authority |
| Persistence 与 durable execution | 正式 Java/Spring Control Plane、PostgreSQL canonical metadata、immutable artifact、durable Job、worker lease、fencing 和 reconcile | 不声明 broker、scheduler、autoscaling、Production HA、Approval 或 tenant/RBAC |
| Production-like 边界 | Candidate A replacement/restore evidence 与 Candidate B managed-persistence/stateless target 比较 | Candidate A 是本地复现环境；Candidate B 不是完成的云部署 |
| Cross-Agent 调查 | Incident Remediation Agent、窄 integration contract、独立 evidence domain、Failure Intelligence、Version Bisect 和统计 cohort | 没有 plugin marketplace、LLM/embedding/ML analysis、auto-promotion 或真实 remediation |
| Delivery surface | Golden Demo、API-backed Overview、lifecycle ownership check 和 hosted canonical CI Gate | 本地/面试交付面不是 Production release |
| Presentation 与公共文档 | Web `en-US`/`zh-CN` presentation-only i18n，以及双语公共文档与 current/history 分离 | canonical governance 保持 single-source；raw evidence 和 identifier 保持 English/不变 |
| 正式诊断可观测性 | 可选的官方 Java/Python OpenTelemetry SDK、W3C propagation、allowlisted correlation context、有界异步 export、Collector 健康/不可用诊断，以及跨服务 durable-run trace correlation | Telemetry 仅是诊断信号：trace/span identity 不是 canonical evidence、release authority、Web schema、retention、SaaS observability 或 Production capacity 证明 |
| 对象存储能力 | 正式 provider-neutral `S3ArtifactStore`、显式 local/S3 backend wiring、conditional immutable create/replay/conflict、verified one-GET read、bounded unknown-write reconcile、PostgreSQL canonical ingest、认证的 HTTP/JSON Worker upload 与 SeaweedFS 4.47 compatibility proof | `LocalFileArtifactStore` 仍是默认路径，历史 bytes 不迁移；不建立托管对象存储、HA/replication/lifecycle authority、2PC 或 Production durability 结论 |

当前活跃模式是 `Stabilization` 中的 `Feature Freeze / Portfolio Maintenance`。新能力必须经过新 Plan 和新 evidence，不能从本文历史推断出来。
