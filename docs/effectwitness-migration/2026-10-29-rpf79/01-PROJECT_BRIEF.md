> 版本 **MIGRATION-2026-10-29-RPF79-rev1**；2026-10-29分支迁移资料，非canonical Project State、非main合并。CURRENT STATE按固定SHA和报告核验；TARGET INTENT保留批准需求；PLANNING CONTEXT不构成执行许可。
>
> 最高明确已接受离线阶段：**RPF-77**（75～77的接受来源为RPF-79正式Plan带入的上一Architect结论，不是本轮重新裁定）。**RPF-78：PARTIAL / PENDING_ARCHITECT_REVIEW**；**RPF-74/rev-4：PAUSED**。先审78再决定修订或下一方向。main=`bda0cd49e50e3181f604324e94877a24b9885334`，迁移Base=`240dbae75cc70f142c7c37a2a3994085063d7ccc`；最新未审查78=`d86528e9927ea2cd7a401da4865829c5a14bfcd2`。证据与验收分开，细节见10/14及SOURCE_EVIDENCE_INDEX.json。

> **保全说明：** 以下原批准合同全文保留。原文2026-10-22“迁移说明”及RPF65待规划等状态句仅为HISTORY_2026_10_22；其中产品要求/决定继续为TARGET INTENT。当前事实只以新版10/14为准，不将历史迁移说明当新执行指令。

# PROJECT BRIEF｜RunProof EffectWitness

> **2026-10-22 迁移说明：** 下文定义已批准的产品目标和候选范围，不能作为最新代码状态。RPF-40～64 的实际成果、负结果和技术边界见 [10-CURRENT_STATE_AND_EVIDENCE.md](10-CURRENT_STATE_AND_EVIDENCE.md)；RPF-65 未计划实施。旧「近期路线」保留为历史规划，不得再次从 RPF-40 开始。赛事当前记录日期以新版 09 为准。


> 性质：**已批准的产品/竞赛目标**，不是当前实现能力清单。原 RunProof 正式长期产品定位仍由仓库 `docs/project/PROJECT_BRIEF.md` 负责。本文件仅定义其竞赛升级增量；长期变更需有界合并并保留旧决定。

## 1. 项目是什么

- 竞赛：首届 **openJiuwen 智能体创新大赛**；优先 Coding/Agent 工具与可靠性工程方向，结合赛事开放的实际场景。
- 作品名：**RunProof EffectWitness**；核心机制：**Proof-Guided Exploration (PGE)**；用户面对的主要产品界面：**EffectWitness Lab**。
- 核心命题：一个 Agent 自述已完成任务，不足以证明它的工具操作真的符合业务安全要求。EffectWitness 面向有状态、有副作用的 Agent，进行受控实验、自主选择故障条件、观察权威业务状态和生成有条件的**失败见证**。
- 目标用户：Agent 应用开发者、AI 后端/平台工程师、负责自动化流程可靠性的工程团队。
- 输入：受测 Agent 的合法执行接口、任务/业务约束、受控可恢复环境、可用故障注入能力、执行预算。
- 输出：实际运行与探索轨迹、Contract 判定、Evidence Feedback、Witness Certificate（或证据不足的明确结果），以及可复现实验参数与验证入口。

## 2. 为什么与现有工具存在独立用途

Codex + Skill 能够做代码审查、编写测试、运行脚本和修复代码；常见 Agent Observability/Eval 产品能做 Trace、数据集评测和比较；已有 fault injection/Effect Contract 项目能验证工具调用副作用。EffectWitness **不得**宣称这些能力的简单组合是首创。

有价值的待验证差异是：**按业务风险选择实验 → 从实际证据中识别有效性/信息缺口 → 反馈给探索 Agent 再选择 → 由独立权威状态验证 → 输出陈述证据边界的可复现 Witness**。模型负责有限策略探索，确定性系统负责事实与权限。要以同预算的固定策略/现有工具作基线，不预设一定胜出。

独立产品可以通过 API/MCP/Skill 被 Codex、JiuwenSwarm 或其他开发环境使用；产品价值不依赖创建一个在 Coding 能力上超过 Codex 的新助手。

## 3. 已批准 CORE / MUST（当前竞赛阶段）

1. 实际的 Exploration Agent：真实 LLM/Tool Calling，能按可用反馈选择实验，且满足资源/授权边界。
2. PGE：展示至少一次根据证据反馈调整实验选择的真实决策，决策与已观察证据可关联。
3. 三份合同：**Agent Execution / Effect / Experiment**，清晰区分受测 Agent、业务权威事实与受控实验条件。
4. 独立业务效果判定：由程序基于可核验状态/收据验证，不由 LLM 决定 PASS/FAIL。
5. Witness Certificate 与离线独立校验：结论分维度；关联身份、冻结合同、真实事件、状态差异、证据引用及复现范围。
6. 跨领域证明：**订单/退款**及**运维/配置变更**，复用核心探索与验证语义，领域差异由合同/适配器承担。
7. 真实直观 Web：任务输入、实验选择、反馈、失败证据和 Timeline/State Diff 深入调查连贯；不把固定 Review Corpus 当最新自主运行。
8. 与原 RunProof 的正式证据、历史、控制权限、运行恢复及 Git 治理兼容；本次竞赛真实演示、3 分钟内视频与申报材料可交付。

具体逐项验收与要求 ID 以 [02-REQUIREMENTS.md](02-REQUIREMENTS.md) 为准。

## 4. STRONG CANDIDATE / SHOULD

- 预算受限的 Witness Minimization（删除步骤后必须**重新运行**验证，不能把 UI 过滤当作最小复现）；
- 受控改进候选与 Baseline/Candidate 可信对照（不强制通用自动改代码）；
- Effect Contract 驱动的有界测试候选生成；
- 有信息量的固定策略基线与 Codex + Skill 用途对比；
- 可通过标准 MCP/API 作为开发工具链的插件入口。

这些价值高，但实施由已证实的核心能力与剩余工期驱动，不自动提升为硬 Gate。

## 5. OPTIONAL / FUTURE、明确非目标

未来可探索第三领域（Coding Agent）、扩大外部框架矩阵、复杂因果归因、多轮反事实、自动修复和生产级云部署；当前不承诺这些已完成。

本次 `REJECTED / NON-GOAL`：大规模 LLM Benchmark、无界自进化、自建通用 Coding Agent、多租户 SaaS、通用 Agent Marketplace、A2A 全生态、真实支付/生产破坏性操作、依赖大模型主观评分做安全判定、未经授权的部署/发布。

## 6. 截止日期与成功分级

- 原孵化时内部提前完成目标：**2026-10-30**；之后 RPF-61 已记录公告和 PC 门户更新为 **2026-11-10**（ZIP≤500MB）。精确截止时刻、时区与登录后字段未核验。以 09 号交付文件及实际报名系统为准，不将内部提前目标当官方截止。
- `L1 Functional`: 至少一条真正的探索与验证闭环、可演示 Witness/无效证据结果。
- `L2 Mechanism`: 真实反馈改变选择且有证据链接；跨领域核心复用；独立 verifier 可以重新检验。
- `L3 Comparative`: 在有限、可比较预算下，PGE 相对固定顺序策略获得额外有效信息或有效违规发现。若未胜也如实报告。
- `L4 Generalized`: 多数据/模型/领域统计性领先需更多独立样本；**本次不作为目标或宣传结论**。

获奖是目标和上行收益，**不是项目验证 PASS 的预设条件**。没获奖时仍应具备 Agent Infra、分布式执行可靠性、状态验证、API/MCP 集成和实验能力的简历证据。

## 7. 历史孵化路线（RPF-40～45 已完成阶段，勿据此再生成）

`RPF-40` 真实仓库/WorkSwarm/执行边界 Spike → `RPF-41` 最小合同与订单效果测试 → `RPF-42` PGE + Evidence Feedback → `RPF-43` Witness + 运维复用 → 后续实时 Lab、增强、材料交付。独立任务可以并行但不得越过真实依赖；详细权限和首个 Plan 交接见 [00-START_HERE.md](00-START_HERE.md)。

## 8. 外部项目事实边界

原 RunProof 的具体实现以 GitHub `main` 与测试证据为准，不凭本 Brief 声称产品已有新能力。参赛需要真正的工具操作与权威状态验证；已有 Golden Demo 可作为能力介绍，但不能当作新 PGE 完成证据。产品方向变化由 Main 与用户按重要性审查，不能由 Codex 在某次实验中自行改写。
