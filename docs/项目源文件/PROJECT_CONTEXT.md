# RunProof 项目上下文

**版本** 2026-11-24 RPF-116，审查基线 `93f2151cdeadec8e106603ad54b882f5b383f82b`，仓库 `MyKr-YSteinsK/runproof`。此文件用于 GPT Project 上传。活跃合同、接受决定和当前事实分别在仓库 [PROJECT_BRIEF](../project/PROJECT_BRIEF.md)、[DECISIONS](../project/DECISIONS.md) 与 [CURRENT_STATE](../project/CURRENT_STATE.md)。执行从根 [AGENTS.md](../../AGENTS.md) 开始。

## 目标与已确认范围

RunProof 让 Agent 工程师可以重现、解释并验证工具失败和业务副作用，把调查案例升级到 Regression，用真实证据支撑版本与发布资格判断。它也是展示工具调用、Agent 状态、确定性工程、失败恢复与评测的个人作品。

- 现有平台的标准闭环为 Candidate Agent Version → Stateful Evaluation → Trajectory 与 State Diff → 独立 Verifier → Failure Investigation → Regression → Baseline/Candidate → Quality Policy → Release Decision。参考场景有 Production Change 与 Incident Remediation。Desktop Web 是人类的主要调查入口，CLI、HTTP API 和 CI 为自动化入口。
- 测试场景定义可恢复起点、任务、预期与禁止结果、不变量和故障。Run 绑定 Agent、Scenario、Environment、Verifier 版本与 Evaluation 身份。以独立规则和业务读回验证结果。把 Agent 故障、环境中断、证据不足区分呈现；防止无覆盖时误发 `ELIGIBLE`。
- 保留并解释 `UNKNOWN_OUTCOME` 与 `RECONCILE_REQUIRED`。有副作用的操作先只读对账，明确授权后才考虑后续动作。Agent、Controller、Authority、Verifier、审批和发布资格各有责任。轨迹只保存可观察事件，遵守敏感数据脱敏与可验证历史不静默重写。
- 原 v1 的真实 Provider 首选 DeepSeek，业务写只在 Controlled Simulation。现有界面支持 Desktop Web 双语、深链、时间线、State Diff 和证据分层。Counterfactual Replay、完整 durable resume、通用 SDK、多 Agent 与生产接入有各自决策条件。

## 当前可演示闭环

仓库与完整工程包提供离线 Reference Agent 的新建和只读重开入口。独立核验的 SQLite 订单收据支撑第二轮工具意图。中断时用原 nonce、request 或 session 追溯写入。诊断 v2 核对原事件语义，并将本次业务读回与原执行读回分开。当写入意图已保存、故障事件缺失，触发与观察为未知。无锚复核通过表示内容自洽。任务完成依靠成功 Witness，签发者身份另需可信来源。日常回归覆盖 transport、两种本地产品、Agent、诊断、工程包协议与 Web。[运行手册](RUNBOOK.md) · [RPF-116 实测](../../spikes/rpf-116/RESULT.md)

## 竞赛历史的适用范围

EffectWitness 提出 Proof-Guided Exploration、Execution/Effect/Experiment 三合同、业务可写目标与独立 Authority、结构化 Witness 与离线 Verifier。原批准的 R-01～R-10 依次覆盖真实 Explorer、证据影响下一实验、三合同、独立业务验证、Witness、确定性复核、订单/运维双域、Lab UI、安全可靠性和比赛材料。D-COMP-01/04/05/06 与 COMP-03 保存已批准的总体方向、重点、两域、核心机制及当时预算。完整原词与 MUST/SHOULD/NON-GOAL 在 [RPF-79 固定快照](https://github.com/MyKr-YSteinsK/runproof/tree/b076d2c4206683ba96eb8ffc6ae2cd290074af0c/docs/effectwitness-migration/2026-10-29-rpf79)。历史预算只针对当时任务。候选的新定位需明确评审如何处置原目标。

## 现实基线

| 入口 | 现有能力 | 当前证据边界 |
| --- | --- | --- |
| Golden Demo | Python Runtime、Java/Spring、PostgreSQL、React Web 的既有平台和 reviewed corpus，可调查旧运行和 Release Decision | 历史多服务运行。本轮静态复核；最近核实的 Canonical Release Gate 覆盖检查失败 |
| EffectWitness Workbench | 记录模式展示历史订单与独立运维样本。RPF-95 固定 JiuwenSwarm 版本实测只读 MCP 工具调用 | 记录型，完整依赖环境及真实 LLM 未验收 |
| EffectWitness Reference Agent | RPF-114/rev-2 单次独立解包会话。Controller 审核意图，订单响应丢失后读回收据，验证反馈后进入配置域，两域各写一个 SQLite 事务 | 确定性策略，Provider 0。Witness 来源绑定可复核，Issuer 未建立。真实 MCP、生产、门户提交未运行 |
| 历史 live 与 UNKNOWN 研究 | RPF-74 存在副作用结果未知后继续 Provider 预约的反例。RPF-110 真实尝试到达 HTTP 响应，解析进入 UNCERTAIN | 旧费用和实际发送量未知。RPF-110/rev-3 修复只验证离线，RPF-96 仍有本机未交付原型 |

## 新阶段候选

用户确认作品集价值与实际使用并重，授权本轮治理接管、小范围重构和整理。2026-11-24 起优先完善 RunProof 自身，跨项目接入暂缓。正式产品目标、真实 Provider、联动写入、旧实现退役及 CI 迁移留待用户确认。[升级评审](UPGRADE_REVIEW.md) · [作品组合](PORTFOLIO.md)
