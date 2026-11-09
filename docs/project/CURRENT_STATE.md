# CURRENT_STATE — RunProof / EffectWitness

> 可核验快照：2026-11-08。稳定产品目标在 `PROJECT_BRIEF.md`，已接受的决定在 `DECISIONS.md`，开发执行规则在根 `AGENTS.md`。本文件记录当前能力、风险和交付，不授权恢复旧实验或使用真实 Provider。

## Repository / working mode

- GitHub public repo：`MyKr-YSteinsK/runproof`；`main` 的最后独立核对 SHA：`ef1a92b911e7ff6f414d7a357a6ec562530ec1c0`（RPF-95/rev-2）。此值为本次治理变更前的观察基线，不代表永久 HEAD。
- 持续研发；常规代码、文档默认 main-first，任务范围内普通 focused commit/push，风险扩展再采用隔离 owner/worktree。完整研发链与 2026-10-29 迁移资料已进入 main；迁移历史中的旧 HEAD 不作为当前基线。
- 旧 `docs/history/`、`spikes/rpf-*` 已封存证据、用户私有 owner/WAL/marker/receipt 均保留。未授权发布、部署、竞赛提交或真实生产操作。

## Delivered evidence (levels are not interchangeable)

- RPF-00～39：既有 RunProof 的 Desktop Web、Java/PostgreSQL Control Plane、Python Runtime、Gate 和 Golden Demo 历史能力。原声明与固定 source/evidence 见 `docs/history`，本次未重新全面复跑。
- RPF-40～81：EffectWitness 两域、三合同、Explorer/Target/Authority/Witness、Provider/预算/故障探索相关研究组件及历史报告已纳入 main。各切片正式接受边界仍以固定提交、当次报告及 Architect 裁定为准；历史源码存在不代表当前产品安全可用。
- RPF-78：历史 rev-1 A08 失败仍须保留，后续更正不回填旧源/结果。RPF-80 是合成投影和独立只读 Oracle；RPF-81/rev-1 有 localhost 物理证据但正常恢复因果混杂，均不是旧 RPF-74 原生修复。
- RPF-94：EffectWitness 只读 Workbench、订单/运维历史来源与 Witness 限制展示已并入 main，任务 PARTIAL；无新 Gateway/Provider 运行。历史来源不是同一双域新会话。
- RPF-99：记录型 EffectWitness 工作台提供三步引导及可独立解压的 Node.js 静态包。Windows 本地验收覆盖回环只读预览、双域历史证据、语言与事件深链、原 Witness 离线校验。工作台区分订单研究与独立运维样本。真实 Explorer、跨域 Authority、Issuer 和发布资格仍需各自的验收。[交付指南](../EFFECTWITNESS_DELIVERY.zh-CN.md)
- RPF-95/rev-1：只读 MCP stdio、历史锚验证与 Workbench 事件往返已交付。早期 repo-root 启动可能触发 FastMCP `.env` 自动读取，是否读取及有无外传未获证明，保持 `UNVERIFIED`。
- RPF-95/rev-2：固定版 JiuwenSwarm `probe_mcp_live_connection` 经 `Runner.resource_mgr` 注册 3 个只读 MCP 工具，注册后的 `MCPTool.invoke` 实际调用运维 Witness 和历史摘要；部分能力获得有界 Architect 接受。依赖以 `--no-deps` 子集部署，`pip check` exit 1，完整依赖闭包/Agent LLM/系统级文件网络审计尚未完成；`VERIFIED_ANCHORED` 不证明第三方 Issuer。
- RPF-96/rev-1～3：截至本快照，Codex 本地回报 RPF-96 仍为未完成/未交付的离线原型：rev-3 聚焦测试 6/6，两次通过；尚缺完整 durable budget/recovery/receiver/独立 Oracle，物理发送未执行，未形成 commit/push。上述数据尚无远端证据，必须标记 `LOCAL_REPORTED_NOT_REMOTE_VERIFIED`。曾由 Windows Python Install Manager 意外安装 Python 3.15.2；owner 外影响仍未核实。旧发送额度 `UNVERIFIED`，原 owner 物理发送保持禁止。

## Active risk and release state

- **RPF-74 原生 UNKNOWN 缺口未修**：Config `UNKNOWN_OUTCOME` WAL seq199 后仍 `provider RESERVE` seq205/233；Order seq427 后仍 seq433/461。相关原业务/Provider 执行路径不得因 RPF-80/81/95/96 代码存在而自动复活。UNKNOWN 后先确定性只读对账，不盲重试写；物理零新预约仍需独立验证。
- RPF-98 修复后的已核对 hosted Canonical Release Gate 为 [Run 42497172434](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42497172434)。Router 为 `688 PASS / 0 ERROR / 5 SKIP / 539 UNAVAILABLE`。覆盖门禁仍分别缺 534 和 516 项，整体为 `FAILED`。RPF-99 对应 Run 以最终交付回执为准。
- 高优先级产品差距：真实受限 Explorer 的跨轮选择、受控 Target 双域真实作用、独立 Authority/Oracle 的新会话事实、Verified Feedback 输入因果链、有界且可离线验证 Witness、可信 Issuer 边界与人类 Desktop Web 实时工作流。只读 MCP 接入与历史 Witness 不能替代这些目标。
- `ELIGIBLE` 不代表部署；历史 hash/source identity 不代表独立第三方 Issuer；模型不能执掌业务真值或 Release Authority。R-01～R-10、MUST/SHOULD/NON-GOAL、D-COMP 目标的批准原义持续有效。

## Development priority and governance

1. 治理单一来源：`AGENTS.md` 作为日常执行约束；`PROJECT_BRIEF` 稳定目标、`DECISIONS` 长期接受决定、`CURRENT_STATE` 真实状态。RPF-79 迁移资料归档为带日期的 historical snapshot，不再驱动最新任务。
2. 采用风险分层：常规源码、文档和离线测试无需历史物理预算的证明；涉及新 socket/provider/持久化 side effect 才检查对应预算、owner、receiver 和副作用边界。历史额度缺失仅阻断其物理执行，不阻断安全代码完善与交付。
3. 维护活跃产品与测试：优先能缩小真实产品能力缺口的工作；RPF-96 若继续，应在可交付的源代码/离线边界先形成实际 commit，再决定物理试验是否另行授权。需独立归因并修复 CI 12 ERROR，但禁止通过隐藏测试或降级覆盖率制造绿色。
4. 旧文件瘦身先分类为 Active / Historical Evidence / Generated Disposable / Candidate Dead Code / User-owned Protected，引用与代码可达性核对后再有界处理。保护 `docs/reviews/` 和旧 private WAL、历史 Witness、Source Map；没有查证的历史目录不可称垃圾或批量删除。

本快照为可更新事实汇总，旧历史的 commit/report/diagnostic 不因本文改版而更改。
