# RunProof 项目上下文

**交接状态** 2026-11-27，RPF-127 收口，停在阶段验收。以当前文件所在完整 Git 提交或同提交的 Project 导出清单为准。先读 [接手索引](HANDOFF_INDEX.md) 和 [CURRENT_STATE](../project/CURRENT_STATE.md) 定位实测、旧证据及未核实事项，再按 [同步入口](00-START_HERE.md) 核对同版本文件。从 [PROJECT_BRIEF](../project/PROJECT_BRIEF.md) 与 [DECISIONS](../project/DECISIONS.md) 查稳定合同和已接受决定。实际执行以项目根 [AGENTS.md](../../AGENTS.md) 为入口。

## 目标与已确认范围

RunProof 让 Agent 工程师可以重现、解释并验证工具失败和业务副作用，把调查案例升级到 Regression，用真实证据支撑版本与发布资格判断。它也是展示工具调用、Agent 状态、确定性工程、失败恢复与评测的个人作品。

- 现有平台的标准闭环为 Candidate Agent Version → Stateful Evaluation → Trajectory 与 State Diff → 独立 Verifier → Failure Investigation → Regression → Baseline/Candidate → Quality Policy → Release Decision。参考场景有 Production Change 与 Incident Remediation。Desktop Web 是人类的主要调查入口，CLI、HTTP API 和 CI 为自动化入口。
- 测试场景定义可恢复起点、任务、预期与禁止结果、不变量和故障。Run 绑定 Agent、Scenario、Environment、Verifier 版本与 Evaluation 身份。以独立规则和业务读回验证结果。把 Agent 故障、环境中断、证据不足区分呈现；防止无覆盖时误发 `ELIGIBLE`。
- 保留并解释 `UNKNOWN_OUTCOME` 与 `RECONCILE_REQUIRED`。有副作用的操作先只读对账，明确授权后才考虑后续动作。Agent、Controller、Authority、Verifier、审批和发布资格各有责任。轨迹只保存可观察事件，遵守敏感数据脱敏与可验证历史不静默重写。
- 原 v1 的真实 Provider 首选 DeepSeek，业务写只在 Controlled Simulation。现有界面支持 Desktop Web 双语、深链、时间线、State Diff 和证据分层。Counterfactual Replay、完整 durable resume、通用 SDK、多 Agent 与生产接入有各自决策条件。

## 当前可演示闭环

RPF-126 在 Windows 的干净源码检出和独立解包应用中验收了 Reference Agent。源码与包内各完成一次合成订单退款和配置变更。源码会话在调查 GET 503 后可用同一 nonce 只读恢复，新增 POST 与业务写入均为 0。两路 Witness 各自通过内容复核，外部签发者未建立。包的 320 项清单及 SHA-256 见 RPF-126 报告，实跑源码固定为 `bc8f72438677dee69b905a3ffbfe27894bc17d06`。Provider 0。RPF-127 复核和保全既有证据。[RPF-126 验收](../../spikes/rpf-126/RESULT.md) · [RPF-127 收口](../../spikes/rpf-127/RESULT.md)

仓库与完整工程包提供离线 Reference Agent 的新建和只读重开入口。独立核验的 SQLite 订单收据支撑第二轮工具意图。中断时用原 nonce、request 或 session 追溯写入。诊断 v2 核对原事件语义，并将本次业务读回与原执行读回分开。当写入意图已保存、故障事件缺失，触发与观察为未知。无锚复核通过表示内容自洽。任务完成依靠成功 Witness，签发者身份另需可信来源。日常回归覆盖 transport、两种本地产品、Agent、诊断、工程包协议与 Web。[运行手册](RUNBOOK.md) · [RPF-116 实测](../../spikes/rpf-116/RESULT.md)

RPF-117 用同一组本地场景检验两种确定性策略。完整反馈才可获准进入第二步。坏反馈的错误提议及宿主拦截分别计量，未到达第二步的记录进入宿主覆盖，不进入 Agent 第二步判断分母。评测用只读复核关联实际策略选择、原报告和 SQLite 收据。[复跑与边界](../../spikes/rpf-117/RESULT.md)

RPF-118 的仓库 CLI 允许预编写的模型格式回复经过同一 Controller 和 Authority。回复、确定性解析和业务效果分别可查。只读复核使用保存的回复和原台账。两步都报告 Agent 判断，缺失或异常回复不计入决策质量。实测限合成回复与合成 SQLite 目标，真实 Provider 请求为零。[模拟回复对照与真实试验候选](../../spikes/rpf-118/RESULT.md)

RPF-119 rev-2 已完成一次性 DeepSeek 评测。六组合成 SQLite 会话共发送 11 次真实请求，正常场景完成退款和配置变更，五组在配置变更前停手。只读复核重解析保存的回复投影，并核对已落盘的工具意图、预算和业务收据。实际峰值估算 CNY 0.0232572，供应商账单未知。一次性调用授权已消费。[RPF-119 结果](../../spikes/rpf-119/RESULT.md)

## RPF-120 覆盖对账

只读工具从同一 Canonical 运行的归档逐项复算 1,232 个必需方法，三阶段缺口为 539 → 534 → 516。`VALID` 表示输入身份、方法集合和覆盖变更可以对账，发行覆盖结论为 `BLOCKED_BY_REQUIRED_COVERAGE`。

Windows x64 的新 NTFS 隔离根通过原 `FactoryContractTests` 30 项，含 junction 拒绝，Provider 0。30 项本机证据独立保存，Canonical 仍有 35 项 `WINDOWS_NATIVE` 缺口，含这 30 项。未来接入需评审同一 run、attempt 和 checkout 下冻结矩阵、源码、精确方法集、Windows 进程回执及 owner/junction 证据的绑定。[RPF-120 结果](../../spikes/rpf-120/RESULT.md) · [只读命令](RUNBOOK.md#归档覆盖对账)

RPF-126 报告提交 `b87795bb5dac151af40b91c32cb01b23847999f8` 的产品 CI 通过，Canonical 的必需覆盖两步仍缺 534 和 516 项。交接版本的独立工作流和实际 checkout 按导出清单核对。[RPF-126 产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45949094891) · [RPF-126 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45949094899)

## 竞赛历史的适用范围

EffectWitness 提出 Proof-Guided Exploration、Execution/Effect/Experiment 三合同、业务可写目标与独立 Authority、结构化 Witness 与离线 Verifier。原批准的 R-01～R-10 依次覆盖真实 Explorer、证据影响下一实验、三合同、独立业务验证、Witness、确定性复核、订单/运维双域、Lab UI、安全可靠性和比赛材料。D-COMP-01/04/05/06 与 COMP-03 保存已批准的总体方向、重点、两域、核心机制及当时预算。完整原词与 MUST/SHOULD/NON-GOAL 在 [RPF-79 固定快照](https://github.com/MyKr-YSteinsK/runproof/tree/b076d2c4206683ba96eb8ffc6ae2cd290074af0c/docs/effectwitness-migration/2026-10-29-rpf79)。历史预算只针对当时任务。候选的新定位需明确评审如何处置原目标。

RPF-114 的工程 ZIP、PPT 和 Submission ZIP 已从封存清单逐项核对。初赛实际上传的文件、版本和时间均未核实。RPF-126 属于当前离线候选，封存之后的 Git 增量按各版本证据追溯。[证据边界与历史入口](HANDOFF_INDEX.md)

## 现实基线

| 入口 | 现有能力 | 当前证据边界 |
| --- | --- | --- |
| Golden Demo | Python Runtime、Java/Spring、PostgreSQL、React Web 的既有平台和 reviewed corpus，可调查旧运行和 Release Decision | RPF-116 复核 reviewed artifact 和 Demo profile。完整多服务运行沿用历史证据 |
| EffectWitness Workbench | 记录模式展示历史订单与独立运维样本。RPF-95 固定 JiuwenSwarm 版本实测只读 MCP 工具调用 | 记录型，完整依赖环境及真实 LLM 未验收 |
| EffectWitness Reference Agent | RPF-126 在固定源码与新解包应用中完成双域会话。Controller 审核意图，订单响应丢失后读取收据，验证反馈后进入配置域，两域各写一个 SQLite 事务 | 确定性策略，Provider 0。源码只读重开已验收，包内只读重开未验收。Witness 内容可复核，Issuer 未建立 |
| 历史 live 与 UNKNOWN 研究 | RPF-74 存在副作用结果未知后继续 Provider 预约的反例。RPF-110 真实尝试到达 HTTP 响应，解析进入 UNCERTAIN | 旧费用和实际发送量未知。RPF-110/rev-3 修复只验证离线，RPF-96 仍有本机未交付原型 |

## 当前优先级与候选

用户确认作品集价值与实际使用并重。当前停在阶段验收，等用户确认交接范围与下一阶段。复赛改造、重大产品或研究方向、架构迁移、新的真实 Provider 调用、外部联动执行、历史实现退役及 Canonical 覆盖准入变更，按各自权限提请用户决定。config-center 联动仍是待评审候选，RunProof 端现有证据限于固定版本的源码审阅。[升级评审](UPGRADE_REVIEW.md#4-config-center-集成候选) · [作品组合](PORTFOLIO.md)
