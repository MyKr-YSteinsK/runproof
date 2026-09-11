# CURRENT_STATE

> 当前真实快照；不追加过程日志。稳定目标见 PROJECT_BRIEF，执行政策见 AGENTS。

## Current

- Lifecycle: `Prototype`
- Plan: `RPF-00 = Complete`；`RPF-01 = Complete`；`RPF-02 = Complete`；`RPF-03 = Complete`：已建立首个单 Run Reliability vertical slice，包含版本化 Stateful Scenario、DeepSeek Provider boundary、Fresh-per-run Docker Environment、response-lost → UNKNOWN_OUTCOME → reconcile、确定性 Verifier 与脱敏 Run Evidence。
- Branch: `main`。
- Product / published version: 无。
- Last verified: 2026-09-11；RPF-01 的 14 项 synthetic/local 合同测试、RPF-02 的 7 项 host 生命周期测试与 1 项真实 Docker provider 集成测试、RPF-03 的 7 项 Python 合同/集成测试，以及正常和 response-lost 两条真实 DeepSeek + Docker live Run 均通过；五份固定样本的源码身份/状态/secret 边界离线核验通过。

## Major capabilities and technical shape

- 已有 [RPF-01 probe 与结论](../../spikes/rpf-01/README.md)：Node.js 24 无第三方依赖的 disposable 本地状态实验，不是正式 Agent/runtime/environment。
- 已有 [RPF-02 probe 与结论](../../spikes/rpf-02/README.md)：Docker Desktop `desktop-linux` / Engine `29.6.1` 上，Fresh-per-run 的 writable-layer、重建无污染、双实例隔离、named-volume persistent-state 对照、cleanup/quarantine 与 environment identity/provenance 合同均有实际证据；Reuse-and-reset 仍是未来优化候选。
- 已有 [RPF-03 product runtime 与 vertical slice](../../runtime/README.md)：Python formal runtime 绑定 `production-change-release@1.0.0`，以 DeepSeek `deepseek-flash` non-thinking tool loop 驱动受控 Docker 状态变更；正常 live 与 response-lost live 都由实际状态、receipt、S0→S1 diff 和 deterministic verifier 判定 `PASS`，各路径仅一次 mutation、无 blind retry，响应丢失先 reconcile。
- RPF-01 的真实 `deepseek-flash` non-thinking 正常路径及 response-lost/reconcile、thinking 单个 user turn 内多轮 Tool Calls、JSON Output 与安全 HTTP 400 样本通过；各状态路径仅发生一次 mutation，无 blind retry。
- RPF-01 最终脱敏样本 15 请求（14 个 200、1 个 400），10,123 已报告 tokens，派生成本 0.00574568 CNY；400 无 usage，成本 unknown。模型返回 alias/fingerprint，没有不可变版本号；文档声明 V4.1-Flash 与响应事实分开保存。
- 正式产品 runtime / Provider adapter 已有 RPF-03 的单 Run Prototype 实现；Java Control Plane、Web、服务脚手架、DB、Queue、scheduler 与 durable worker 仍无。credential/私有 continuation 不持久化。
- CI / deployment workflow / endpoint / release：无。

## Workflow / delivery facts

- 用户已确认 GitHub identity：`MyKr-YSteinsK/runproof`，`Public`。
- Git Credential Manager 与 GitHub API 已验证账户 `MyKr-YSteinsK`；无需依赖 gh CLI。
- Remote: `origin` → https://github.com/MyKr-YSteinsK/runproof.git；GitHub 已验证为 Public，默认分支 `main`。
- Upstream: `main` → `origin/main`；RPF-01 已普通 push，并验证 ahead/behind=`0/0`、worktree clean；最终快照提交仍在交付时核对远端 HEAD。
- Delivery model: `push-only`；无部署触发。具体授权与执行规则见 AGENTS。

## Known limitations / risks

- TU-001 最小 non-streaming/single-turn Tool-Using 合同获得实验支持，建议首个 Prototype 默认 non-thinking。thinking 的跨 user turn、fault/restart/continuation 恢复及 streaming 未验证；有限样本不证明长期稳定性。
- RPF-02 已取得 Prototype-level minimum Environment isolation/reset 合同证据，但不等于 production-grade isolation、HA、durable worker 或 deployment readiness。首个 Prototype 建议采用 Fresh-per-run 语义；Reuse-and-reset 仍需 provider 级 snapshot/restore、ownership 与 quarantine 成本证据后再启用。TU-002 已在该范围关闭；TU-003 Fault Injection Boundary、TU-004 Durable Run Execution、TU-005 Evaluation Job Transport、TU-006 Replay Semantics、TU-007 Non-deterministic Evaluation、TU-008 Agent Integration Contract、TU-009 Large Trace Visualization 仍未整体解决。
- RPF-03 只证明一个 Production Change Agent、一个版本化 Scenario、DeepSeek non-thinking/non-streaming 和两个 live Fault Profile 的单 Run Prototype 合同；不等于通用 Agent SDK、生产级 isolation/HA、durable resume、streaming/thinking continuation、真实生产 destructive operation 或发布授权。当前 Docker 是 evidence/provider 实现，不是永久产品身份。
- 401/402/422/429/5xx/transport 等主要为 documented + synthetic 分类证据，不宣称真实触发；secret 防护不是完整生产 DLP，成本估计不是账单。Java/Python 等推荐架构未被此次 Node probe 决定或否定。
- TU-010 Failure Minimization 待真实 Failure Corpus 后再调查，不阻塞 v1。

## Active work

无进行中的产品实现任务；RPF-03 已在首个单 Run vertical slice 范围完成并交付，未把 Docker 写成永久产品架构决定，也未新增 canonical durable decision。

## Next likely boundary

进入 Desktop Web Control Plane 的首个 Evidence / Failure Investigation surface：继承 RPF-03 的 Run identity、Trajectory、Environment transition、S0→S1 State Diff、Verified Result 与 Evidence layer 语义，先保证调查上下文、关键事实层级和 failure drill-down，再决定是否扩展运行时边界；继续不引入 Queue、scheduler 或 Durable framework，除非后续 Plan 明确授权。

## Update rule

在完成、Partial、Blocked 或交接时仅按 material change 更新当前事实；目标不能写成能力，当前限制不能改写成永久 non-goal。最终提交身份与同步状态以实时 Git/远端核验为准，不维护旧 SHA 流水或将 Optional USER CHECK 纳入待办。
