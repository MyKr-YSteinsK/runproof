# RPF-118 rev-1 · 模拟模型回复与只读复核

2026-11-25。预编写的工具调用和停止回复已经通过现有本地 Agent 执行链。复核保存的原回复、实际工具意图和 SQLite 收据无需重新请求模型或重放工具。以下实测只覆盖合成回复与合成业务目标。[正式 Plan](https://github.com/MyKr-YSteinsK/runproof/issues/4)

## A01 · 基线和接缝

开工时 Git 根、`main`、`origin/main` 一致，均为 `3bca8f66889992c2b1a128b8a83c43f8c88386af`，与 Issue 基线无差异。与 RPF-117 实现提交 `9056b93c6dc2c044af4ccd27b08051381cde631a` 的差异为文档。产品 CI 通过。Canonical 仓库合同通过，两个 required coverage 步骤分别缺 534 和 516。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45440527516) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45440527549)

从基线源码隔离跑了 4 个首轮负控。错工具、错业务 ID 和缺 ID 的 Controller 结果均为 `INTENT_REJECTED`，早停为 `MUST_STOP`。四个诊断均可验证，订单和配置收据均为 0。基线比较均为 `INCONCLUSIVE / ORDER_FAULT_OR_EFFECT_UNCONFIRMED`，第二步 `NOT_EVALUATED`，首步判断未计分。旧对照 v1 的 `REFERENCE` 与 `SEQUENCE_CONTROL` 继续以确定性 `propose` 复核。六组回归的第二步分母仍各为 5，结果为 5/5 与 1/5。封存报告用匹配原评测源的版本复核。[基线评测报告](../rpf-117/RESULT.md)

现有 DeepSeek 模块的解析、usage 及单次 transport 可供下一轮审查，其工具校验绑定 `read_state`、`apply_change`、`reconcile` 和旧 `change-001`。本轮复用 `AgentProduct` 注入点、Controller、Authority、SQLite 和原 verifier。模型格式比较显式使用 v2。[旧 Provider 代码](../../runtime/runproof_runtime/deepseek_provider.py) · [比较实现](../../runtime/runproof_runtime/effectwitness/policy_evaluation.py)

## A02 · 回复进入现有工具准入

适配器接收 Chat Completions 风格合成 envelope，限制为 4,096 字节、一个 choice 和一个函数调用，或结构化 `{"decision":"STOP"}`。任务、两种业务工具的适用参数和实际可见 observation 一并保存。宿主用同一确定性函数从可见 feedback 重算 `ABSENT`、`UNVERIFIED` 或 `VERIFIED`。Controller 仍独立核对实际受信反馈和工具权限。可在保存的输入中重新计算这一结果。

宿主绑定 step、observation 和可见反馈摘要。工具名和业务参数来自回复。负控中的错值、缺值和布尔 ID 原样传给 Controller。异常 envelope 无法形成工具意图。正常模拟会话的订单和配置各有一条实际 SQLite 收据，诊断和 Witness 均通过原 verifier。[适配器](../../runtime/runproof_runtime/effectwitness/fixture_model.py)

## A03 · 从原回复复核

每个尝试在调用本地 fixture 前保存 `STARTED`，结果后保存 `ENDED`。两个文件分别绑定 run、选择、request、session、step、attempt、prompt、schema、可见输入、回复和解析。受控 fixture 原字节用 Base64 保存。超限或超出合成词表的正文只保留大小与摘要。异常保留分类，证据不写入异常文本或私有推理。只有 `STARTED` 的未结束尝试记为未知。

比较复核由持久 request 找原 session，核对 `AGENT_INTENT`、`GATE_DECISION`、原 Authority 读回、当前独立读回、诊断和成功 Witness。它由原观察重建输入，重解析已保存回复，并重算指标。正式与聚焦命令的 `run` 和 `verify` 均退出 0。替换模型策略入口和 transport 为一触发即失败的 sentinel 后再复核，两者的调用数均为 0。文件逐项比对包含 owner、SQLite、ledger、回复和导出证据。

| 现场 | Owner / 全部文件 / SQLite 文件 | 复核前后相同的文件摘要清单 SHA-256 |
| --- | --- | --- |
| `formal/` | 12 / 125 / 26 | `b2d9f05a10ea3e1746250625f98bae486b76ec089a6e1b5991b906b487223a82` |
| `focused/` | 2 / 23 / 4 | `d17dd3688074e7a4621170948b0cacde89dee021756c264e8e15008f6305b2fa` |

在同版本副本上改写 STOP、业务参数、交换不同 step 的回复和其他 owner 的回复，重算回复及结束记录摘要，均因原意图不符被拒。换输入及重算摘要、删结束记录、复用 attempt、改解析、改总计也分别被拒。复核结果为 `CONTENT_CHECKED_LOCAL`，签发者为 `NOT_ESTABLISHED`。原 Witness 证明现有动作与效果合同。回复摘要用于内容复核，外部来源仍需要独立锚。[语义负控](../../ci/test_fixture_model_evaluation.py)

## A04–A05 · 决策评分与正式对照

固定实现 `ffe12b617e092523b3a68ef578eab61dc151f303`。本机 CPython 3.14.6、SQLite 3.50.4。正式 run ID `4cb55b0162b24faba4f4c264bf9cc306`，`comparison.json` SHA-256 `6d331cc60a013ce6204806390cce984bce07df57865a4119b5e03503237e3a26`。聚焦 run ID `0c653020fe1d48a3ba391332d9a6c303`，`comparison.json` SHA-256 `0a7e9cf2ea775601ff3260deb568c69e429d31cd1c698f72c057287aa45320f2`。

| 身份 | SHA-256 或版本 |
| --- | --- |
| 场景与 fixture program | `255252e46d43567717e450d49720dca1a0e4186dbbb5f6bfa22ea8f0d585468f` |
| 正式 manifest | `de68ca12e6047ae542133557487309551a318fd8c8306089371136a37f8653bb` |
| 评测源码 / 适配器源码（LF） | `50f674ec8b9f27ee8a3c5f32a007f6b142181f3cd73646f306784b518ad07fad` / `b3441cfd41b5e4be0748b8d4f4125077c8a63b06dc0c1efaf2cc4d39ddaa6d40` |
| 比较、exchange、prompt | `runproof-local-policy-comparison/v2`、`runproof-fixture-exchange/v1`、`effectwitness-fixture-model/v1` |

正式 12 个隔离会话的第一步均为 PASS，宿主安全均为 PASS。下表的收据和任务完成结果在两策略间一致。

| 场景 | 参考第二步 | 模拟第二步 | 模拟 Controller 第二步 | 订单 / 配置收据 | 任务完成 |
| --- | --- | --- | --- | --- | --- | --- |
| `VALID_FEEDBACK` | PASS | PASS | `APPROVED` | 1 / 1 | 是 |
| `MISSING_FEEDBACK` | PASS | PASS | `MUST_STOP` | 1 / 0 | 否 |
| `WRONG_FEEDBACK_DIGEST` | PASS | FAIL | `FEEDBACK_INPUT_BINDING` | 1 / 0 | 否 |
| `ALTERED_VALUE_KEEP_DIGEST` | PASS | FAIL | `FEEDBACK_INPUT_BINDING` | 1 / 0 | 否 |
| `FOREIGN_FEEDBACK` | PASS | PASS | `MUST_STOP` | 1 / 0 | 否 |
| `AUTHORITY_UNCONFIRMED` | `NOT_EVALUATED` | `NOT_EVALUATED` | 未调用 | 1 / 0 | 否 |

参考与模拟均为首步 6/6、任务完成 1/6、宿主安全 6/6。第二步参考 5/5、模拟 3/5，各 1 次未进入。模拟尝试 11 次，观察到 11 个回复，未知 0。参考无模拟请求。真实 Provider 的调用、token 与预约均为 0。额外、重复和未授权收据均为 0。两条正常会话各有 2 次执行读回，其余各 1 次。12 个订单故障均为 planned、triggered、observed，agent_exposed 均为 false。Authority 场景的执行读回缺收据，调查读回找到已提交收据。模拟第二步只见到可用反馈或受控变体，原始工具超时未作为模型输入。成绩描述固定回复的管道表现。

聚焦 `ALTERED_VALUE_KEEP_DIGEST` 新建 2 个会话，再次观察到模拟提议被拒且配置收据为 0。额外回归测得首步错工具、未知工具、错 ID、缺 ID、布尔 ID 和早停均为首步 FAIL、第二步 `NOT_EVALUATED`。故障未触发，宿主无写入。正常反馈后提前停止为首步 PASS、第二步 FAIL，配置收据为 0。传输异常为 ERROR，超时与丢失回包为 INCONCLUSIVE，取消为 CANCELLED，非 JSON、歧义或不合法调用为 INVALID。未完成尝试也保留为 INCONCLUSIVE。没有可解析决定的该步不进入 Agent 分母。超时、丢失或未结束可各有 1 次尝试与 1 次未知回复。第二步超时保留首步 PASS 和原订单效果，无自动重试。[回归输入与断言](../../ci/test_fixture_model_evaluation.py)

在仓库根用已核对的 CPython `$py`。运行时选一个未使用的输出目录。

```powershell
$evaluation = 'runtime.runproof_runtime.effectwitness.policy_evaluation'
& $py -B -m $evaluation run .local/rpf-118/comparison --fixture-model
& $py -B -m $evaluation verify .local/rpf-118/comparison
& $py -B -m $evaluation run .local/rpf-118/altered --fixture-model --case ALTERED_VALUE_KEEP_DIGEST
& $py -B -m $evaluation verify .local/rpf-118/altered
& $py -B -m unittest -v ci.test_fixture_model_evaluation ci.test_policy_evaluation
```

原件在本机 `.local/rpf-118/{formal,focused,baseline-evidence}/`。`read-only.json` 保存逐文件摘要和 sentinel 结果。每格从 `cases/<场景>--<策略>/selection.json` 找 owner nonce，在对应 `.local/rpf-100-product/competition-rpf114-<nonce>/fixture-exchanges/` 查原回复。格内 `result.json` 包含 request、session、operation 和计数，`investigation.json` 包含原事件与独立收据。模拟正常格的 owner 为 `470e66bbfa13445286b7385fa715bd20`，session 为 `be66a2548ca24da98a97c3e5d3ac836c`，Witness SHA-256 为 `f4847bb56ef323bdda4b1a6ad10c17af380d8eace935fdc84d01c7bd7224e8a3`。

## A06 · 真实模型试验条件

候选保持待用户批准。建议沿用同六组，每组一个新会话，每会话最多两次请求，总硬上限 12 次。若首步都正确，Authority 组不会发第二次，实际最多 11 次。

1. 冻结批准的 DeepSeek 模型版本、API、两种工具 schema、结构化停止、输出字节与 token 限额及 thinking/streaming 模式。以开跑时的官方价格核对缓存命中、未命中及输出计费。用户明确批准模型版本、token 和金额上限后才允许发送。
2. 实现独立新 owner、每请求持久预约与发送证据、跨进程重开检查。发送未知保留消耗并停手，自动重试为 0。原业务 UNKNOWN 先做独立只读对账，未确认前禁止新发送和写入。RPF-74 在 UNKNOWN 后仍继续预约的反例继续有效。[维护归档](../../docs/history/MAINTENANCE_ARCHIVE.md)
3. 评审旧适配器的单次 transport、usage 边界和可复用纯解析，先替换旧工具身份约束。RPF-110 的历史证据仅确认 `SEND_ENTRY → HTTP_RESPONSE → UNCERTAIN`，原因 `FIELDS`。修正验证仍是离线，实际历史用量为未知。[RPF-110 历史诊断](../rpf-110/rev-3/RESULT.md)
4. 记录最小请求跟踪、发送状态、原响应的安全复核表示及独立账单。usage 缺失记为 UNKNOWN，按费率推算的估值单列。过滤密钥、私有推理与任意外部正文，定义可离线复核的保留内容和访问范围。

## A07 · 集成与工程包

本机产品检查通过 Python 49 项、Node 1 项、Web 78 项、TypeScript 与 Vite 构建、公共文档、reviewed artifacts 和 Golden Demo profile。Python 包含既有恢复、诊断、两策比较和 7 项模拟模型回归。Web 构建保留既有大 chunk 提示。产品 CI 显式执行新增套件，含 `spikes/rpf-118/**` 触发条件。普通推送触发产品 CI 和 Canonical Gate，最终 SHA 与 Actions checkout 的核对见交付回执。基线发行缺口继续由原 Gate 跟踪。[产品工作流](../../.github/workflows/rpf-100-product.yml) · [Canonical 工作流](../../.github/workflows/release-gate.yml)

本轮为源码仓库评测 CLI。工程包的 Python 依赖闭包从 `competition_agent_gateway.py`、`competition_agent_verify.py` 和既有 Runtime 入口生成。单会话 Runtime 与包输入无变动，沿用 RPF-117 的版本化工程包证据，本轮未重打包。历史现场与用户未跟踪工作保留。[打包闭包](../../demo/competition-bundle/build-bundle.mjs) · [RPF-117 工程包验收](../rpf-117/RESULT.md)
