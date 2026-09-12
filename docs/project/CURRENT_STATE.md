# CURRENT_STATE

> 当前真实快照；不追加过程日志。稳定目标见 PROJECT_BRIEF，执行政策见 AGENTS。

## Current

- Lifecycle: `Prototype`
- Plan: `RPF-00 = Complete`；`RPF-01 = Complete`；`RPF-02 = Complete`；`RPF-03 = Complete`；`RPF-04 = Complete`；`RPF-05 = Complete`；`RPF-06 = Complete`：已建立真实 Agent `FAIL`、Platform/Environment `ERROR`、独立 `rpf-failure-case-v1` 复现/验证闭环，并将当前 validated Failure Case 经五项 promotion gate 晋升为首条独立 `rpf-regression-v1` Historical Regression，完成 known-bad/fixed Candidate focused rerun 与只读调查控制面。
- Branch: `main`。
- Product / published version: 无。
- Last verified: 2026-09-12；RPF-01 的 14 项 synthetic/local 合同测试、RPF-02 的 7 项 host 生命周期测试与 1 项真实 Docker provider 集成测试、RPF-03～RPF-06 runtime 的 23 项 Python 合同/集成测试、Web 的 6 项 adapter tests、frontend typecheck/build 与 reviewed artifact verifier 均通过；正常和 response-lost 两条真实 DeepSeek + Docker v2 live Run 均为 `PASS`，RPF-05 的 Agent FAIL source/reproduction 与 controlled Environment ERROR、RPF-06 的两条 known-bad stability Run 与 fixed Candidate focused Run 均通过真实 Docker runtime；浏览器在 1440/1280 desktop viewport 的 Run/Failure Case/Regression list/detail、promotion link、source/reproduction/focused Run deep-link 均通过，页面无横向溢出且无 blocking console error；历史与当前 reviewed JSON 的源码身份、状态、secret/private-protocol 边界离线核验通过。

## Major capabilities and technical shape

- 已有 [RPF-01 probe 与结论](../../spikes/rpf-01/README.md)：Node.js 24 无第三方依赖的 disposable 本地状态实验，不是正式 Agent/runtime/environment。
- 已有 [RPF-02 probe 与结论](../../spikes/rpf-02/README.md)：Docker Desktop `desktop-linux` / Engine `29.6.1` 上，Fresh-per-run 的 writable-layer、重建无污染、双实例隔离、named-volume persistent-state 对照、cleanup/quarantine 与 environment identity/provenance 合同均有实际证据；Reuse-and-reset 仍是未来优化候选。
- 已有 [RPF-03 product runtime 与 vertical slice](../../runtime/README.md)：Python formal runtime 绑定 `production-change-release@1.0.0`，以 DeepSeek `deepseek-flash` non-thinking tool loop 驱动受控 Docker 状态变更；正常 live 与 response-lost live 都由实际状态、receipt、S0→S1 diff 和 deterministic verifier 判定 `PASS`，各路径仅一次 mutation、无 blind retry，响应丢失先 reconcile。
- 已有 [RPF-04 Evidence Control Plane](../../web/README.md)：React + TypeScript + Vite 的正式 Desktop Web read-only surface，通过薄 data adapter 消费真实 v2 reviewed artifacts；提供 Run entry、context identity、stable timeline/event deep-link、Fault ≠ Failure recovery path、S0→S1 State Diff、Evidence/Invariant Inspector 与 raw payload 渐进展开。历史 v1 与当前 v2 明确分层，未静默迁移。
- 已有 RPF-05 Failure Investigation surface：`/runs`、`/runs/:runId`、`/failures`、`/failures/:failureCaseId` 均消费本地 reviewed corpus；Agent FAIL 显示 violated invariant、guard evidence、state protection 与 Failure Case 引用，Platform/Environment ERROR 显示 pre-Agent readiness boundary、Agent 未启动与质量排除；Failure Case 只在 stable signature、invariant、evidence pattern、健康边界和 fresh identity 均匹配后进入 `validated`，明确不是 Regression。
- 已有 RPF-06 Regression workflow：`regression.py` 提供 reproducibility、relevance、stability、non-duplicate、explicit expectation 五项结构化 promotion gate；`rpf-regression-v1` 以稳定 signature-derived identity、versioned expected behavior/oracles、promotion decision、evidence refs 和 focused rerun history 独立于 Run/Failure Case；`rpf-regression-result-v1` 分离 Run outcome 与 Regression result，最小 `Historical Regression` collection 通过静态 reviewed manifest 提供稳定 lookup；known-bad `1.0.0-known-bad-unsafe-precondition` 稳定 FAIL，fixed Candidate `1.0.1-observe-before-mutation-fix` 通过同一 Regression。
- RPF-01 的真实 `deepseek-flash` non-thinking 正常路径及 response-lost/reconcile、thinking 单个 user turn 内多轮 Tool Calls、JSON Output 与安全 HTTP 400 样本通过；各状态路径仅发生一次 mutation，无 blind retry。
- RPF-01 最终脱敏样本 15 请求（14 个 200、1 个 400），10,123 已报告 tokens，派生成本 0.00574568 CNY；400 无 usage，成本 unknown。模型返回 alias/fingerprint，没有不可变版本号；文档声明 V4.1-Flash 与响应事实分开保存。
- 正式产品 runtime / Provider adapter 已有 RPF-03～RPF-06 的单 Run Prototype 实现，Desktop Web Control Plane 已有 RPF-06 的只读本地 reviewed corpus surface；CLI 提供 check/promote/focused/verify Regression 入口；Java Control Plane、API/backend service、DB、Queue、scheduler 与 durable worker 仍无。credential/私有 continuation 不持久化。
- CI / deployment workflow / endpoint / release：无。

## Workflow / delivery facts

- 用户已确认 GitHub identity：`MyKr-YSteinsK/runproof`，`Public`。
- Git Credential Manager 与 GitHub API 已验证账户 `MyKr-YSteinsK`；无需依赖 gh CLI。
- Remote: `origin` → https://github.com/MyKr-YSteinsK/runproof.git；GitHub 已验证为 Public，默认分支 `main`。
- Upstream: `main` → `origin/main`；RPF-04 delivery record commit `d03cb59`、RPF-05 focused commit `408506a` 与 RPF-06 implementation commit `1ee20b5` 均已普通 push，RPF-06 delivery-state update 亦随后提交并 push；交付后 fetch 核验远端 HEAD、ahead/behind=`0/0` 与 worktree clean。
- Delivery model: `push-only`；无部署触发。具体授权与执行规则见 AGENTS。

## Known limitations / risks

- TU-001 最小 non-streaming/single-turn Tool-Using 合同获得实验支持，建议首个 Prototype 默认 non-thinking。thinking 的跨 user turn、fault/restart/continuation 恢复及 streaming 未验证；有限样本不证明长期稳定性。
- RPF-02 已取得 Prototype-level minimum Environment isolation/reset 合同证据，但不等于 production-grade isolation、HA、durable worker 或 deployment readiness。首个 Prototype 建议采用 Fresh-per-run 语义；Reuse-and-reset 仍需 provider 级 snapshot/restore、ownership 与 quarantine 成本证据后再启用。TU-002 已在该范围关闭；TU-003 Fault Injection Boundary、TU-004 Durable Run Execution、TU-005 Evaluation Job Transport、TU-006 Replay Semantics、TU-007 Non-deterministic Evaluation、TU-008 Agent Integration Contract、TU-009 Large Trace Visualization 仍未整体解决。
- RPF-03 只证明一个 Production Change Agent、一个版本化 Scenario、DeepSeek non-thinking/non-streaming 和两个 live Fault Profile 的单 Run Prototype 合同；不等于通用 Agent SDK、生产级 isolation/HA、durable resume、streaming/thinking continuation、真实生产 destructive operation 或发布授权。当前 Docker 是 evidence/provider 实现，不是永久产品身份。
- RPF-06 Web 仍属于 read-only local/static adapter；Regression promotion/rerun 由 CLI/runtime 产生 reviewed artifacts，页面不提供写操作；尚未实现 API ingestion、Evaluation Suite、Baseline/Candidate aggregate、Quality Policy、Release Gate 或 live Run/reproduce/promote action。当前浏览器证据来自桌面 Chromium；`Real-device verification: not executed`，不据此宣称 iOS/mobile/PWA 体验。
- RPF-06 focused evidence 使用 deterministic known-bad/fixed profiles，因此本轮 promotion/focused rerun 不需要新增 DeepSeek Provider 调用；真实 Provider failure/continuation 未由该路径重新验证。
- 401/402/422/429/5xx/transport 等主要为 documented + synthetic 分类证据，不宣称真实触发；secret 防护不是完整生产 DLP，成本估计不是账单。Java/Python 等推荐架构未被此次 Node probe 决定或否定。
- TU-010 Failure Minimization 待真实 Failure Corpus 后再调查，不阻塞 v1。

## Active work

无进行中的产品实现任务；RPF-06 已在 promotion gate、首条 Historical Regression、known-bad/fixed focused rerun 与只读调查 surface 范围完成并交付，未把 Docker 写成永久产品架构决定，也未新增 canonical durable decision。

## Next likely boundary

进入下一 Reliability workflow boundary：调查最小 Evaluation Suite 以及 Baseline vs Candidate aggregate 语义；保留 RPF-06 的 v2 evidence/v1 case/v1 regression adapter 与只读边界，在后续 Plan 明确数据来源前不引入 API/backend、Queue、scheduler 或 Durable framework。

## Update rule

在完成、Partial、Blocked 或交接时仅按 material change 更新当前事实；目标不能写成能力，当前限制不能改写成永久 non-goal。最终提交身份与同步状态以实时 Git/远端核验为准，不维护旧 SHA 流水或将 Optional USER CHECK 纳入待办。
