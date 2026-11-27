# CURRENT_STATE — RunProof / EffectWitness

> 2026-11-23 接管历史基线。核对基线为 `main@b076d2c4206683ba96eb8ffc6ae2cd290074af0c`。此 SHA 是整理前本地与远端共同基线；当前版本以所在 Git 提交为准。产品合同见 [PROJECT_BRIEF](PROJECT_BRIEF.md)，长期决定见 [DECISIONS](DECISIONS.md)。

## 2026-11-27 · RPF-128 / RPF-129 本地验收

同一退款超时表象在 Windows 的三组独立合成会话中得到退款／配置收据 1／1、0／0、1／0。B 由闭合回滚和不变状态共同证明未落账。C 在决策时 Authority 不可用，事后确认退款仍保留原转人工裁决。openJiuwen 0.1.21 的真实 ReAct 循环只调用记录提议的工具，并读回回执。每轮六格的固定顺序组在 B、C 均被独立 Controller 拒绝。两路各从新进程重复一次，共 18 个不同会话，Provider 0。验收为 Windows 本地、固定回复和合成业务，用户仅授权本地交付。[实测与证据](../../spikes/rpf-129/RESULT.md) · [复跑命令](../项目源文件/RUNBOOK.md#超时实验)

## 2026-11-27 · RPF-127 rev-1

当前停在阶段验收。原位保全 RPF-114 的三份封存交付物及 RPF-126 当前候选和验收证据。初赛实际提交对象、版本和时间未核实。仅将一棵与 RPF-126 ZIP 逐成员一致的构建暂存树移入本机待清理区，共 320 文件、5,181,298 字节，已在备用路径实测恢复并复核原件。Provider 0。Project 可按同一个 Git 提交的清单手动装载。复赛和后续路线仍待用户确认。[RPF-127 验收](../../spikes/rpf-127/RESULT.md) · [接手索引](../项目源文件/HANDOFF_INDEX.md)

## 2026-11-27 · RPF-126 rev-1

离线交付候选固定为 `bc8f72438677dee69b905a3ffbfe27894bc17d06`。干净 Windows 检出完成一次正常双域会话，原 nonce 只读重开经调查 GET 503 后恢复，新增 POST 和业务写入均为 0。同源码完整工程包独立解包、启动并验真，错误摘要被拒。Provider 0。实测无产品阻塞，当前结果留待阶段验收。[实测和公开索引](../../spikes/rpf-126/RESULT.md)

## 2026-11-27 · RPF-125 rev-1

Reference Agent 已将会话绑定、调查读回和导出各自显示。Windows 同一 owner 的调查 GET 返回 404/503 时，已确认会话和时间线仍可查，匹配的 Witness 可下载并由原 CLI 复核。调查恢复、错配和迟到响应均已验证。只读重开新增 POST 与业务写入均为 0，Provider 0。[故障对照与回归](../../spikes/rpf-125/RESULT.md)

## 2026-11-27 · RPF-124 rev-1

R72r2 隔离复验已提供仓库入口。干净 Windows NTFS 检出通过三个冻结原方法，两次独立只读复核得到相同结论，三份 WAL 和一个退款 SQLite 保持原摘要与修改时间。源码漂移、复用输出目录和修改 WAL 的负控均拒绝。Provider 0。本机复验供查证，Canonical 覆盖继续按托管证据计量。[命令和实测](../../spikes/rpf-124/RESULT.md)

## 2026-11-26 · RPF-123 rev-1

R72r2 专用运行器候选的三个原方法在新 Windows NTFS 隔离根全部通过。独立只读复核确认未授权 SQLite 预约被拒绝、会话仅预约和结算一次，以及响应丢失后合成退款仅有一条收据。Provider 0。本机结果供评审同类扩样，三项在 Canonical 仍为 `UNAVAILABLE`。[复验与边界](../../spikes/rpf-123/RESULT.md)

## 2026-11-26 · RPF-122 rev-1

基线与说明候选分别从干净 Windows 检出复跑 Reference Agent 与两组策略对照。修订中英 README 的无锚 Witness 校验和单场景报告入口。订单响应丢失后，独立读回确认原 operation 只有一条退款收据，同一 nonce 只读重开未增加请求或收据。坏反馈组区分主动停手与 Controller 拦截，正常组各自完成双域操作。Provider 0。本机验收 A01–A04 通过，托管 CI 状态按提交独立记录。[实测与命令](../../spikes/rpf-122/RESULT.md)

## 2026-11-25 · RPF-121 rev-1

确定性策略评测的 `explain` 从同次只读复核导出单场景双列 HTML。坏反馈下，参考策略主动停手，顺序型对照的配置提议被 `FEEDBACK_INPUT_BINDING` 拒绝。两者订单与配置收据均为 1/0。正常反馈下两种策略均完成，收据为 1/1，各自成功 Witness 已核对。缺失诊断和跨会话替换均被拒绝。对账与导出独立于发行覆盖，Provider 0。[验收与复跑](../../spikes/rpf-121/RESULT.md)

## 2026-11-25 · RPF-120 rev-1

只读对账核对同次 Actions 文件的 1,232 个必需方法，按原始 Router、RPF-87、RPF-89 复算缺口 539 → 534 → 516。Windows x64 的独立 NTFS 隔离根通过原 `FactoryContractTests` 30 项，含一处 junction 拒绝测试。Provider 预约、发送和 token 均为 0。本机复验证据独立保留，Canonical 的 Windows 路由仍有 35 项缺口。[对账与原生复验证据](../../spikes/rpf-120/RESULT.md)

## 2026-11-25 · RPF-119 rev-2

已完成六组真实 DeepSeek 和六组 Reference 对照。两条路径首步均为 6/6、第二步为 5/5、宿主安全为 6/6，各有一个完整双域任务。DeepSeek 发出 11 次请求，均返回 HTTP 200，自动重试和未知消耗均为 0。API 报告输入 11,151、输出 433 token，峰值估算 CNY 0.0232572，账单 `UNKNOWN`。原账本及业务收据只读复核通过，正式试验的 165 个文件逐项一致。一次性授权已消费。[验收与试验状态](../../spikes/rpf-119/RESULT.md)

## 2026-11-25 · RPF-118 rev-1

仓库评测 CLI 可接收保存的合成模型回复，沿用单会话的工具准入和 SQLite 业务核验。六组参考与模拟对照各完成 6 个隔离会话。第二步参考 5/5、模拟 3/5，模拟路径的两次错误提议均被拒绝。两种策略的宿主安全均为 6/6。复核重解析原回复，核对原意图和只读收据。模拟 11 次尝试，真实调用、token 和预约均为 0。真实发送及预算仍待单独审批。[验收与取证](../../spikes/rpf-118/RESULT.md)

## 2026-11-25 · RPF-117 rev-1

本地 Controller 与诊断校验共享反馈准入规则，第二步须绑定 Agent 实际看到的完整已核验反馈。仓库 CLI 以六个冻结场景比较参考策略和顺序型负对照，并用只读 SQLite 重新计算任务完成、Agent 第二步判断和宿主安全。运行、场景和策略选择绑定到持久 request，共用现有 Witness 和诊断 verifier。[策略对照与回归](../../spikes/rpf-117/RESULT.md)

## 2026-11-24 · RPF-116 rev-1

本地 Reference Agent 的调查报告 v2 核对已落盘的工具意图、Controller 决定、执行时的 Authority 读回和反馈。提交后故障事件尚未落盘时，退款可由收据确认，故障触发和观察状态仍为未知。合法的停止和中断记录可复核；历史报告使用对应源码的校验工具。[RPF-116 实测与工程包](../../spikes/rpf-116/RESULT.md)

## 2026-11-24 · RPF-115 rev-1

该轮以 `df81b1b8b6e8807dfde598446ed5d05cab9fe3b3` 为基线。Reference Agent 具备一次性 owner 初始化、绑定 request 的持久预约、提交前观察和两域独立调查。常规运行与子进程中断实测使用隔离 SQLite 和零 Provider。仓库及完整包的版本、收据、恢复及验证证据见 [RPF-115](../../spikes/rpf-115/RESULT.md)。产品 CI 已接入离线 Python、Node、Web 及文档检查。Canonical 的 required coverage 继续独立计量。优先推进项目自身，外部联动暂缓。

## 当前能力与证据

| 路线 | 已有实现和证据 | 证据范围 |
| --- | --- | --- |
| RunProof Golden Demo | Production Change 和 Incident Remediation 的 Scenario、Failure、Regression、Quality Gate 与只读调查页面。Python Runtime、Java/Spring、PostgreSQL canonical metadata 和 artifact store 有现存实现。 | RPF-116 通过 reviewed artifact 和 Demo profile 静态复核。完整 Golden Demo 多服务运行沿用历史证据。[Demo](../DEMO.zh-CN.md) · [验证历史](../history/VERIFICATION_HISTORY.zh-CN.md) |
| EffectWitness 记录和只读 MCP | 记录型 Workbench 与独立订单/运维历史切片。RPF-95/rev-2 实测固定版 JiuwenSwarm 的 `Runner.resource_mgr` 注册和只读 `MCPTool.invoke`。 | RPF-95 使用 `--no-deps` 子集，依赖闭包未通过 `pip check`，LLM 决策与系统级安全审计未完成。[记录型交付](../EFFECTWITNESS_DELIVERY.zh-CN.md) · [RPF-95/rev-2](../../spikes/rpf-95/rev-2/RESULT.md) |
| EffectWitness 本地 Reference Agent | Controller 审核工具意图，独立读回退款收据再把核验反馈交给配置步骤。仓库和完整工程包提供新建、只读重开、Witness 与调查报告 v2。 | RPF-116 实测为确定性 Agent、Provider 0、Issuer `NOT_ESTABLISHED`。[诊断验收](../../spikes/rpf-116/RESULT.md) · [RPF-114 历史验收](../../spikes/rpf-114/RESULT.md) |
| EffectWitness Live Explorer | RPF-110/rev-3 对历史 live 失败做了离线 parser 诊断，旧运行到达 `SEND_ENTRY → HTTP_RESPONSE → UNCERTAIN`。 | 实际历史发送总数、usage、费用 `UNKNOWN`，修订后的 live 复跑 `NOT_RUN`。这条记录不能给新 Provider 或业务动作授权。[RPF-110/rev-3](../../spikes/rpf-110/rev-3/RESULT.md) |

## 安全、CI 与本地现场

- **RPF-74 原生 UNKNOWN 缺口仍有反证。** Config `UNKNOWN_OUTCOME` WAL seq199 后仍 `provider RESERVE` seq205/233，Order seq427 后仍 seq433/461。RPF-80/81/95/96 与后续受限路径的实验范围各自独立。旧现场送出额度 `UNVERIFIED`。[维护归档](../history/MAINTENANCE_ARCHIVE.md)
- **产品 CI 与发行基线。** 产品 CI 覆盖 Provider 0 请求与预算回归，以及 RPF-120 的只读对账。RPF-120 的审查基线 `d959030c74744fc3de1bbaff93703a80b9ab25aa` 通过产品 CI 与 Canonical 仓库合同检查。两步 required coverage 分别缺 534 和 516，发行受阻。按交付 SHA 查询对应运行。[审查基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45548688568) · [审查基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45548688606)
- **CI 基线（2026-11-24）。** RPF-116 的审查基线 `93f2151cdeadec8e106603ad54b882f5b383f82b` 上，产品 CI 通过。Canonical 的仓库合同检查通过，两步 required coverage 仍缺 534 和 516，发行受阻。较早的记录见 [接管前 Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42839529972) 与 [RPF-98](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42497172434)。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45387631184) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45387780159)
- **本机存在未交付研究工作。** `RPF-74/rev-4` 与 `RPF-96` 相关原型在接管时未跟踪，未纳入接管提交。RPF-96 仍以 `LOCAL_REPORTED_NOT_REMOTE_VERIFIED` 记录。旧 Python Install Manager 意外安装事件的 owner 外影响未核实。普通开发使用已核实解释器。[运行与恢复](../项目源文件/RUNBOOK.md)
- **2026-11-23 接管时的聚焦验证。** Web 77 项、TypeScript 和生产构建通过，构建有大 chunk 提示。Python Control Plane client、HTTP transport 和 durable worker 共 8 项，reviewed artifacts 与 Golden Demo profile 静态检查通过。Maven 离线测试 16 项和 Java 打包通过。
- **2026-11-23 接管时的 CI 输入恢复。** 首次接管提交编辑了固定 SHA 的 Runtime 测试文件，Canonical 在账本前报 `SOURCE_DRIFT`。后续提交恢复原测试字节，把 HTTP 回归放入聚焦套件。[接管产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45161449323) · [接管 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45161449251)

## 维护入口

1. 按 [接手索引](../项目源文件/HANDOFF_INDEX.md) 查看当前候选、运行证据和未核实事项。使用 [GPT Project 接管入口](../项目源文件/00-START_HERE.md) 装载同版本文件，按 [Runbook](../项目源文件/RUNBOOK.md) 选择经授权的检查。普通维护采用 main-first，风险按实际副作用分层。
2. 2026-10-29 RPF-79 迁移包已退出工作树常用路径。完整字节在固定 Git 基线和本地待清理区可取；R-01～R-10、D-COMP 及 MUST/SHOULD/NON-GOAL 的批准身份保留。[归档与取回](../history/MAINTENANCE_ARCHIVE.md)
3. [升级评审](../项目源文件/UPGRADE_REVIEW.md) 记录产品、代码、CI、迁移和 `config-center` 联动候选。用户确认取舍后方可启动重大重构。仓库的既有 `Stabilization` 状态及各历史验收按对应证据理解。
