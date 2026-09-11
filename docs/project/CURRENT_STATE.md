# CURRENT_STATE

> 当前真实快照；不追加过程日志。稳定目标见 PROJECT_BRIEF，执行政策见 AGENTS。

## Current

- Lifecycle: `Discovery`
- Plan: `RPF-00 = Complete`；`RPF-01 = Complete`，实验、必要验证与代码/固定证据/结论的远端交付已完成。
- Branch: `main`。
- Product / published version: 无。
- Last verified: 2026-09-11；真实 DeepSeek probe、14 项 synthetic/local 合同测试及固定样本的源码身份/状态重放/usage-cost/secret 边界离线核验通过。

## Major capabilities and technical shape

- 已有 [RPF-01 probe 与结论](../../spikes/rpf-01/README.md)：Node.js 24 无第三方依赖的 disposable 本地状态实验，不是正式 Agent/runtime/environment。
- 真实 `deepseek-flash` non-thinking 正常路径及 response-lost/reconcile、thinking 单个 user turn 内多轮 Tool Calls、JSON Output 与安全 HTTP 400 样本通过；各状态路径仅发生一次 mutation，无 blind retry。
- 最终脱敏样本 15 请求（14 个 200、1 个 400），10,123 已报告 tokens，派生成本 0.00574568 CNY；400 无 usage，成本 unknown。模型返回 alias/fingerprint，没有不可变版本号；文档声明 V4.1-Flash 与响应事实分开保存。
- 正式产品 runtime / Provider adapter / Web / 服务脚手架：无。仅 Spike 范围发生真实 Provider 调用；credential/私有 continuation 不持久化。
- CI / deployment workflow / endpoint / release：无。

## Workflow / delivery facts

- 用户已确认 GitHub identity：`MyKr-YSteinsK/runproof`，`Public`。
- Git Credential Manager 与 GitHub API 已验证账户 `MyKr-YSteinsK`；无需依赖 gh CLI。
- Remote: `origin` → https://github.com/MyKr-YSteinsK/runproof.git；GitHub 已验证为 Public，默认分支 `main`。
- Upstream: `main` → `origin/main`；RPF-01 已普通 push，并验证 ahead/behind=`0/0`、worktree clean；最终快照提交仍在交付时核对远端 HEAD。
- Delivery model: `push-only`；无部署触发。具体授权与执行规则见 AGENTS。

## Known limitations / risks

- TU-001 最小 non-streaming/single-turn Tool-Using 合同获得实验支持，建议首个 Prototype 默认 non-thinking。thinking 的跨 user turn、fault/restart/continuation 恢复及 streaming 未验证；有限样本不证明长期稳定性。
- 本地单进程状态与 receipt 不是可信正式 Environment isolation/reset 证据；TU-002 Environment Execution Model 优先待调查。TU-003 Fault Injection Boundary、TU-004 Durable Run Execution、TU-005 Evaluation Job Transport、TU-006 Replay Semantics、TU-007 Non-deterministic Evaluation、TU-008 Agent Integration Contract、TU-009 Large Trace Visualization 仍未整体解决。
- 401/402/422/429/5xx/transport 等主要为 documented + synthetic 分类证据，不宣称真实触发；secret 防护不是完整生产 DLP，成本估计不是账单。Java/Python 等推荐架构未被此次 Node probe 决定或否定。
- TU-010 Failure Minimization 待真实 Failure Corpus 后再调查，不阻塞 v1。

## Active work

无进行中的产品实现任务；RPF-01 Spike 已完成，下一边界由 Architect 确定。

## Next likely boundary

TU-002 Environment Execution Model Spike：以当前 observed-state/receipt/reconcile 合同验证隔离、restore/readiness 与污染边界，再进入有可信环境的 Prototype；不提前选择 Queue 或建设 Durable framework。具体下一 Plan 由 Architect 确定。

## Update rule

在完成、Partial、Blocked 或交接时仅按 material change 更新当前事实；目标不能写成能力，当前限制不能改写成永久 non-goal。最终提交身份与同步状态以实时 Git/远端核验为准，不维护旧 SHA 流水或将 Optional USER CHECK 纳入待办。
