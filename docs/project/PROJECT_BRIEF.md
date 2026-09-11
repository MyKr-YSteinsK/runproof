# PROJECT_BRIEF

> 保存稳定产品意图、v1 边界及跨任务产品/UX 不变量。当前实现、生命周期与交付事实由 CURRENT_STATE 持有。

## Product

- Name: RunProof (`RPF`)
- Purpose: Agent Reliability & Release Engineering Platform。把 Agent Failure 变成可重现、可验证、可持续复用的 Regression / Release Evidence 资产，支持有证据的迭代与发布判断。
- Primary users: Agent Engineer；AI Application / AI Backend Engineer；AI Platform / Agent Infrastructure Engineer。
- Primary platforms: Desktop Web Control Plane 是 portfolio-critical Primary human surface；CLI / Programmatic API / CI 是 automation surfaces。
- v1 reference: Production Change Agent，覆盖发布/Canary/Rollback、配置/Feature Flag 变更与状态迁移/维护；首个且默认真实 LLM Provider 为 DeepSeek。

## Core user loop

Candidate Agent Version → Evaluation Suite → Controlled Stateful Environment / Normal、Failure、Safety Scenarios → Trajectory + Environment Transition / Evidence → deterministic verification → Outcome / Failure Investigation → Reproduce / Validate / Promote Regression → Baseline vs Candidate → Quality Policy → Release Gate。

Failure reproduction、focused rerun 与持续 Regression 是核心工作流；Counterfactual Replay 保持 SHOULD，不因存在 Replay UI 入口升级为 v1 MUST。

## Product priorities

1. Evidence first：Agent 可以不确定，可确定事实的验证不能跟着不确定。
2. Reference-Agent-first：先做透 Production Change Agent，同时避免平台永久写死单领域；第二个真实、长期使用的 Agent 出现后再验证 Generic SDK/Adapter 抽象。
3. 可靠性、安全与可复现性优先；Baseline/Candidate 同时比较质量、恢复、安全、Tool usage、Token/Cost 和 Latency。
4. Desktop Web 的调查效率、视觉与信息架构属于正式验收，不能延期为末期美化。

## Stable architecture boundary

- 推荐方向（非施工承诺）：React + TypeScript Web、Java/Spring Boot Control Plane、Python Agent/Evaluation Runtime、PostgreSQL canonical metadata、OpenTelemetry-compatible observability、containerized environment 与文件/对象型 artifact storage。
- 具体语言职责、通信、Queue/Job Transport、执行隔离与 durable execution 边界由 Investigation / Spike 证据决定；不得因技术栈关键词引入组件。
- Canonical metadata 与大型 Trace/Artifact 逻辑分离；Cache 不得成为唯一 canonical truth。
- DeepSeek 通过 Provider boundary 接入；首个 Provider 不定义平台身份。
- v1 Agent 有副作用 Tool 只操作 Controlled Production Simulation Environment；不连接真实生产 destructive credentials。真实 Provider 调用与受测 Tool 的外部状态变更属于不同边界。
- Provider credentials、authorization token 等不得进入 Git、前端源码、Scenario、默认持久化 Trace 或普通 Evidence export；敏感字段默认 redact/mask。

## Cross-task reliability contracts

- Stateful Scenario 不是 Prompt 集合：包含已知 Initial State、Task、Required/Acceptable Outcome、Forbidden Outcome、Invariants 及可选 Fault Profile。
- Environment 必须有可识别 revision、可恢复起点、可观测副作用与可信 provenance。restore/reset、readiness 或 initial-state verification 失败时不得开始正式 Evaluation；污染环境须隔离/quarantine。
- 正式 Run / Release Evidence 绑定 Agent Version（含 model、prompt/config、tool/runtime revision 等行为身份）、Scenario Version、Environment Revision、Verifier Version 与 Evaluation identity；关键身份缺失不能成为正式 Release Evidence。
- Run outcome 至少区分 `PASS / FAIL / ERROR / INVALID / INCONCLUSIVE / CANCELLED`。非 Scenario 设计的 Provider outage、平台/环境故障与无效 Scenario/Verifier 不得伪装成 Agent FAIL；ERROR/INVALID 不计入 Agent Quality 成功率，Release Gate 必须考虑有效证据覆盖率。
- Fault 的 planned / triggered / observed 分开记录并与时间线对齐；目标 Fault 未实际触发时，不得将该 Fault Scenario 算作有效 PASS。
- Trajectory 保存可观察 observation/action、Tool call/result、Fault、Environment transition、approval/interruption、retry/recovery 与 outcome，不依赖模型私有 Chain-of-Thought。
- 可由状态、显式规则与程序验证的事实不能仅由 LLM Judge 裁定；验证结果能回到 expected/actual state、violated invariant 与 evidence。
- `Observed Fact / Verified Result / Inference / AI Analysis` 分层保存并呈现，不把派生分析改写成原始事实。
- `UNKNOWN_OUTCOME` 的有副作用操作先 reconcile 再决定 retry；reconcile 不自动意味着重试安全。Worker crash 不得算 Agent FAIL；无法证明安全恢复时不得静默 whole-run retry，应进入 ERROR/quarantine/review。自动 durable resume 仍为 SHOULD。
- Failure → Reproduce → Validate → Promote to Regression → Add to Suite 是独立质量流程，要求可重现性、相关性、稳定性、非重复性及明确预期；修复后可 focused rerun，未来版本持续验证。
- Run outcome 与 Release Decision 是不同状态域。Quality Policy 支持 Hard/Soft/Review Gate；Release Decision 至少表达 `ELIGIBLE / BLOCKED / REVIEW REQUIRED / INCONCLUSIVE`。关键证据不足时 fail closed/inconclusive；不能因“0 FAIL”误报可发布。
- `ELIGIBLE` 不等于已发布或执行器获得 deploy/release 授权。关键 Release Authority 不由被测 Agent 持有；Agent/runtime 不得绕过 Approval / Quality Policy。
- Run / Release 历史事实不可静默重写；后续解释使用 review、annotation 或 superseding decision。平台重启不能丢失已保存历史。
- Agent/model/tool 与 platform/worker/environment/verifier 双侧 observability 属于 v1 合同；Token/Cost/Latency 可追踪，Step/Time/运行预算必须限制 runaway。Web/CLI/CI 共享核心平台事实与结果。

## v1 non-goals and deferred scope

- 普通 Chatbot、通用知识库 RAG、CRUD Admin 作为产品主形态；通用 Agent Framework/Team、Marketplace、Visual Workflow Builder、Fine-tuning 平台或一开始支持所有 Agent Framework。
- 真实 Production destructive operation；真实 Production integration 属于 FUTURE，须单独安全与授权设计。
- Native/Mobile App、PWA/Offline；Desktop Web 仍需基础响应式不破坏。
- 导师研究方向的硬集成；研究价值须通过独立产品决定进入范围。
- Counterfactual Replay、Failure Minimization、Attribution、Durable Resume、Release Evidence Pack 等按 Requirements 的 SHOULD/延期优先级推进，不是首个切片的先决条件。

以上是 v1 范围或延期边界，不声明 FUTURE 能力永久禁止；不能以“推荐方案尚未调查”作为产品永久 non-goal。

## Canonical UX baselines

- 保护已认可的 A1 Reliability Control Plane 体验语义：克制专业、清晰 context identity，以 Failure Timeline 为主，State Diff、Release Evidence、Blocking Invariant 辅助，高密度而不压迫。
- Failure Investigation 以 Timeline、State Diff、Trajectory Diff、Invariant/Evidence 与 first meaningful divergence 为核心，帮助重建行为、故障和状态变化。
- Evaluation → Failure → Tool/Event drill-down 保持 Agent/Version/Evaluation/Scenario 上下文连续；Run/Failure/Regression/Release Decision 支持稳定 deep-link。
- Baseline/Candidate 是一等比较能力，不要求两个页面人工对照；reproduce/focused rerun、Regression、Compare 等动作靠近相关证据。
- Observed Fact / Verified Result / Inference / AI Analysis 有明确视觉层级；Evidence 缺失明确展示，不补造。关键证据默认可见，raw payload 渐进展开。
- Evaluation 组织进度/矩阵/分布；Failure 组织时间线/diff/evidence；Release 组织 policy/gates/blocking evidence。不得把所有页面套成 KPI cards + chart + table，也不为丰富而强行图表化。
- 核心状态不能只靠颜色；核心动作不依赖 hover，有明确 focus 与键盘可达性；长 Trace/矩阵在大数据量下可操作，局部滚动不破坏整体页面。
- 组件库、主题色、light/dark、图表库、字号与间距属于实现选择；已认可概念方向不等于已锁定视觉实现。

## Context ownership and update rule

本文件是跨任务合同摘要，不替代完整 Requirements/Architecture/UX。完整 Bootstrap 上下文由 Architect 持有；每份 Plan 提取当前任务相关 MUST、Acceptance 和 UX invariant，不要求执行器依赖不可读取的外部材料。摘要遗漏不构成已确认需求被废除；具体取舍以有效决定及其适用范围判断。

仅在稳定产品意图、v1 边界、跨任务不变量或 canonical UX 实质变化时更新。不得写入当前任务、生命周期、实现进度或运行/交付快照。
