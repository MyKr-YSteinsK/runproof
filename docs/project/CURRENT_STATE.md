# CURRENT_STATE — RunProof / EffectWitness

> 2026-11-23 接管历史基线。核对基线为 `main@b076d2c4206683ba96eb8ffc6ae2cd290074af0c`。此 SHA 是整理前本地与远端共同基线；当前版本以所在 Git 提交为准。产品合同见 [PROJECT_BRIEF](PROJECT_BRIEF.md)，长期决定见 [DECISIONS](DECISIONS.md)。

## 2026-11-24 · RPF-115 rev-1

本轮以 `df81b1b8b6e8807dfde598446ed5d05cab9fe3b3` 为基线。Reference Agent 具备一次性 owner 初始化、绑定 request 的持久预约、提交前观察和两域独立调查。常规运行与子进程中断实测使用隔离 SQLite 和零 Provider。仓库及完整包的版本、收据、恢复及验证证据见 [RPF-115](../../spikes/rpf-115/RESULT.md)。产品 CI 已接入离线 Python、Node、Web 及文档检查；Canonical 的 required coverage 继续独立计量。优先推进项目自身，外部联动暂缓。

## 当前能力与证据

| 路线 | 已有实现和证据 | 证据范围 |
| --- | --- | --- |
| RunProof Golden Demo | Production Change 和 Incident Remediation 的 Scenario、Failure、Regression、Quality Gate 与只读调查页面。Python Runtime、Java/Spring、PostgreSQL canonical metadata 和 artifact store 有现存实现。 | 本次通过 reviewed artifact 和 Demo profile 静态复核。完整 Golden Demo 多服务运行沿用历史证据。[Demo](../DEMO.zh-CN.md) · [验证历史](../history/VERIFICATION_HISTORY.zh-CN.md) |
| EffectWitness 记录和只读 MCP | 记录型 Workbench 与独立订单/运维历史切片。RPF-95/rev-2 实测固定版 JiuwenSwarm 的 `Runner.resource_mgr` 注册和只读 `MCPTool.invoke`。 | RPF-95 使用 `--no-deps` 子集，依赖闭包未通过 `pip check`，LLM 决策与系统级安全审计未完成。[记录型交付](../EFFECTWITNESS_DELIVERY.zh-CN.md) · [RPF-95/rev-2](../../spikes/rpf-95/rev-2/RESULT.md) |
| EffectWitness 本地 Reference Agent | RPF-114/rev-2 的独立解包会话经 Controller 审核，订单响应丢失后读回收据，首轮反馈绑定配置变更，两域各一笔 SQLite 事务。独立读回的摘要与下载 Witness 一致，错锚和篡改被拒绝。 | 历史运行使用确定性 Agent，Provider 0，Issuer `NOT_ESTABLISHED`。外部 MCP、生产发布和竞赛门户上传 `NOT_RUN`。[RPF-114 验收](../../spikes/rpf-114/RESULT.md) · [交付清单](../../spikes/rpf-114/DELIVERABLES.md) |
| EffectWitness Live Explorer | RPF-110/rev-3 对历史 live 失败做了离线 parser 诊断，旧运行到达 `SEND_ENTRY → HTTP_RESPONSE → UNCERTAIN`。 | 实际历史发送总数、usage、费用 `UNKNOWN`，修订后的 live 复跑 `NOT_RUN`。这条记录不能给新 Provider 或业务动作授权。[RPF-110/rev-3](../../spikes/rpf-110/rev-3/RESULT.md) |

## 安全、CI 与本地现场

- **RPF-74 原生 UNKNOWN 缺口仍有反证。** Config `UNKNOWN_OUTCOME` WAL seq199 后仍 `provider RESERVE` seq205/233，Order seq427 后仍 seq433/461。RPF-80/81/95/96 与后续受限路径的实验范围各自独立。旧现场送出额度 `UNVERIFIED`。[维护归档](../history/MAINTENANCE_ARCHIVE.md)
- **Canonical Release Gate 处于 FAILED。** 截至接管前最近一次已核实的 [Run 42839529972](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42839529972) 在 required Runtime coverage 与 RPF-89 derived required coverage 失败。较早的 [RPF-98 Run 42497172434](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42497172434) 记录 `688 PASS / 0 ERROR / 5 SKIP / 539 UNAVAILABLE`。这是不同 SHA 的历史数据。以新提交自己的运行和归因更新状态。
- **本机存在未交付研究工作。** `RPF-74/rev-4` 与 `RPF-96` 相关原型在接管时未跟踪，未纳入接管提交。RPF-96 仍以 `LOCAL_REPORTED_NOT_REMOTE_VERIFIED` 记录。旧 Python Install Manager 意外安装事件的 owner 外影响未核实。普通开发使用已核实解释器。[运行与恢复](../项目源文件/RUNBOOK.md)
- **本次聚焦验证。** Web 77 项、TypeScript 与生产构建通过，保留现有大 chunk 提示。Python Control Plane client、HTTP transport 和 durable worker 共 8 项，reviewed artifacts 与 Golden Demo profile 静态检查通过。Maven 离线测试 16 项和 Java 打包通过。物理演示、真实 Provider 和外部发布本轮未运行。
- **接管 CI 输入恢复。** 首次接管提交的 [Local Product](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45161449323) 通过。[Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45161449251) 因编辑了固定 SHA 的 Runtime 测试文件而在账本前报 `SOURCE_DRIFT`。后续提交恢复原测试字节，将 HTTP 回归放入聚焦套件。原 required coverage 和验证器沿用各自固定身份。

## 维护入口

1. 按 [GPT Project 接管入口](../项目源文件/00-START_HERE.md) 恢复背景，按 [Runbook](../项目源文件/RUNBOOK.md) 选择所需检查。普通维护采用 main-first，风险按实际副作用分层。
2. 2026-10-29 RPF-79 迁移包已退出工作树常用路径。完整字节在固定 Git 基线和本地待清理区可取；R-01～R-10、D-COMP 及 MUST/SHOULD/NON-GOAL 的批准身份保留。[归档与取回](../history/MAINTENANCE_ARCHIVE.md)
3. [升级评审](../项目源文件/UPGRADE_REVIEW.md) 记录产品、代码、CI、迁移和 `config-center` 联动候选。用户确认取舍后方可启动重大重构。仓库的既有 `Stabilization` 状态及各历史验收按对应证据理解。
