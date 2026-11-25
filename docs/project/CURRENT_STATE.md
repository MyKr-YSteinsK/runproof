# CURRENT_STATE — RunProof / EffectWitness

> 2026-11-23 接管历史基线。核对基线为 `main@b076d2c4206683ba96eb8ffc6ae2cd290074af0c`。此 SHA 是整理前本地与远端共同基线；当前版本以所在 Git 提交为准。产品合同见 [PROJECT_BRIEF](PROJECT_BRIEF.md)，长期决定见 [DECISIONS](DECISIONS.md)。

## 2026-11-25 · RPF-119 rev-2

独立 CLI 增加一次性任务 claim、发送前的持久预约、请求阶段记录和回复投影的只读复核。Provider 0 保留六组对照、11 次回环 POST 和 8 个真实子进程中断窗口。重开无重发，原始 SQLite 收据可独立核对。本机有 DeepSeek 凭据，实际计费币种待核实，六组真实试验暂为 `NOT_RUN`。当前批准只覆盖本轮额度和合成目标。[验收与试验状态](../../spikes/rpf-119/RESULT.md)

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
- **产品 CI 与发行基线。** 产品 CI 增加 Provider 0 请求与预算回归。RPF-119 的审查基线 `1ec69addfb7fca5038c4c50b5a41032d100e979e` 通过产品 CI 与 Canonical 仓库合同检查。两步 required coverage 分别缺 534 和 516，发行受阻。按交付 SHA 查询对应运行。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45459896840) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45459897282)
- **CI 基线（2026-11-24）。** RPF-116 的审查基线 `93f2151cdeadec8e106603ad54b882f5b383f82b` 上，产品 CI 通过。Canonical 的仓库合同检查通过，两步 required coverage 仍缺 534 和 516，发行受阻。较早的记录见 [接管前 Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42839529972) 与 [RPF-98](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42497172434)。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45387631184) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45387780159)
- **本机存在未交付研究工作。** `RPF-74/rev-4` 与 `RPF-96` 相关原型在接管时未跟踪，未纳入接管提交。RPF-96 仍以 `LOCAL_REPORTED_NOT_REMOTE_VERIFIED` 记录。旧 Python Install Manager 意外安装事件的 owner 外影响未核实。普通开发使用已核实解释器。[运行与恢复](../项目源文件/RUNBOOK.md)
- **2026-11-23 接管时的聚焦验证。** Web 77 项、TypeScript 和生产构建通过，构建有大 chunk 提示。Python Control Plane client、HTTP transport 和 durable worker 共 8 项，reviewed artifacts 与 Golden Demo profile 静态检查通过。Maven 离线测试 16 项和 Java 打包通过。
- **2026-11-23 接管时的 CI 输入恢复。** 首次接管提交编辑了固定 SHA 的 Runtime 测试文件，Canonical 在账本前报 `SOURCE_DRIFT`。后续提交恢复原测试字节，把 HTTP 回归放入聚焦套件。[接管产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45161449323) · [接管 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45161449251)

## 维护入口

1. 按 [GPT Project 接管入口](../项目源文件/00-START_HERE.md) 恢复背景，按 [Runbook](../项目源文件/RUNBOOK.md) 选择所需检查。普通维护采用 main-first，风险按实际副作用分层。
2. 2026-10-29 RPF-79 迁移包已退出工作树常用路径。完整字节在固定 Git 基线和本地待清理区可取；R-01～R-10、D-COMP 及 MUST/SHOULD/NON-GOAL 的批准身份保留。[归档与取回](../history/MAINTENANCE_ARCHIVE.md)
3. [升级评审](../项目源文件/UPGRADE_REVIEW.md) 记录产品、代码、CI、迁移和 `config-center` 联动候选。用户确认取舍后方可启动重大重构。仓库的既有 `Stabilization` 状态及各历史验收按对应证据理解。
