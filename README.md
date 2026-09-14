# RunProof

RunProof（`RPF`）是一个 **Agent Reliability & Release Engineering Platform**：通过状态化评测、故障注入、失败回归化、证据可视化和发布门禁，把 Agent Failure 变成可重现、可验证、可持续复用的工程资产。

## 仓库入口

仓库包含 bootstrap 文档、[RPF-01 disposable DeepSeek probe](spikes/rpf-01/README.md)、[RPF-02 controlled-environment probe](spikes/rpf-02/README.md)、[RPF-03～RPF-08 product runtime](runtime/README.md)、[RPF-09 persistence/API boundary probe](spikes/rpf-09/README.md)、[RPF-10 PostgreSQL/auth boundary probe](spikes/rpf-10/README.md)、[RPF-11 formal Control Plane](control-plane/README.md)、RPF-14 formal durable execution / PostgreSQL job transport 和 [Evidence / Evaluation / Failure / Regression / Release Decision Web surface](web/README.md)。当前生命周期、任务与远端交付事实以 [CURRENT_STATE](docs/project/CURRENT_STATE.md) 为准。

- [PROJECT_BRIEF](docs/project/PROJECT_BRIEF.md)：稳定产品意图、v1 Reliability/UX 合同与边界。
- [DECISIONS](docs/project/DECISIONS.md)：继承 Bootstrap canonical D-001～D-012 的有效决定。
- [AGENTS](AGENTS.md)：仓库执行、安全和 Git/delivery 规则。
- RPF-02 已取得 Docker provider 的 Prototype-level minimum Environment 证据；RPF-03 已建立首个单 Run reliability vertical slice；RPF-04 收敛了 Run Evidence 合同；RPF-05 已建立真实 Agent FAIL、Platform/Environment ERROR 与 Failure Case 复现闭环；RPF-06 已将该 Failure Case 经 promotion gate 晋升为首条 Historical Regression，并完成 known-bad/fixed Candidate focused rerun；RPF-07 建立了三成员 Evaluation Suite、Baseline/Candidate 聚合比较与只读 Evaluation/Comparison 控制面；RPF-08 建立了 Quality Policy、Release Gate、Baseline/Candidate Release Decision；RPF-09 以 disposable Spring Boot/H2 candidate 验证了 Stabilization 的 metadata/artifact/API 最小边界。不代表 production-grade isolation/HA/DB/API/Job Transport，也不把 Docker、H2 或本地 artifact store 固化为永久产品身份。
- RPF-11 已将 RPF-10 证实的边界收敛为正式 Java/Spring + PostgreSQL canonical metadata 模块、immutable artifact store、受限 service auth、Python HTTP client 与默认 API-backed Web datasource；不引入 Queue、scheduler、durable worker、Approval 或 release/deploy endpoint。
- RPF-12 已接入真实 GitHub Actions Canonical Release Gate：每次 main 代码变更在 hosted runner 上 fresh 执行 Baseline/Candidate Evaluation，并以 Control Plane canonical Release Decision read-back 作为 CI 结论；只上传脱敏 JSON/Job Summary，不执行 release/deploy。
- RPF-14 已将 RPF-13 的候选边界落入正式 Control Plane：PostgreSQL durable Job/Attempt/Operation/Event/Evidence schema、fenced poll/claim/heartbeat、跨进程 UNKNOWN_OUTCOME reconcile、正式 Python worker、只读 Execution investigation surface，以及 RPF-12 的 Baseline/Candidate durable submit/poll/read 路径。仍不引入 broker、scheduler、生产 HA、Approval 或 release/deploy endpoint。
- RPF-15 已完成 Production-readiness investigation：用真实 disposable production-like Candidate A 验证 Web、Control Plane、durable worker、PostgreSQL named-volume、immutable artifact backup/restore、replacement、迁移/回滚兼容性和 Release Identity 边界，并推荐 managed persistence/stateless Candidate B + explicit-release；项目仍保持 Stabilization，不执行真实 Production deploy/release。

## 核心方向

Candidate → Evaluation Suite → Controlled Stateful Environment → Trajectory / State / Evidence → deterministic verification → Failure Investigation / Regression → Baseline vs Candidate → Quality Policy → Release Gate。

Desktop Web Control Plane 为 Primary human surface；CLI / Programmatic API / CI 为 automation surfaces。Production Change Agent 为首个 reference agent，DeepSeek 为首个 Provider；平台身份保持独立。

v1 Agent 有副作用 Tool 仅操作 Controlled Production Simulation Environment，不连接真实生产 destructive credentials。技术栈是待 Investigation/Spike 验证的推荐方向；正式产品范围与非目标见 PROJECT_BRIEF。
