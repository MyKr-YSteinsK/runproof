# RPF-117 rev-1 · 反馈准入与本地策略对照

2026-11-25。本地六组场景各用两种确定性策略执行一次。在四种坏反馈下，参考策略停手，顺序型负对照仍提议第二步，Controller 拒绝这四次提议。只读 SQLite 证明四组均无配置变更。验收依据为 [Issue #3](https://github.com/MyKr-YSteinsK/runproof/issues/3)。

## A01–A02 · 准入一致性

起始本地与远端 main 均为 `9277800945f1365affad6126206dfa8d2de13502`。基线模块从该 Git 提交导出，在两个新合成 owner 中运行。基线探针在配置目标创建入口拦住调用，读取实际 Controller 裁决、订单事实与原诊断。此探针只测到准入边界，基线的配置事务和成功 Witness 未生成。

| 源码和样本 | 第二步裁决 | SQLite 订单 / 配置收据 | 诊断 CLI |
| --- | --- | --- | --- |
| 基线参考策略，反馈内容改动且摘要原样保留 | `MUST_STOP` | 1 / 0 | 内容通过 |
| 基线顺序对照，同一逻辑反馈，配置创建被探针拦住 | `APPROVED` | 1 / 0 | 退出 3 · `FEEDBACK_INPUT_BINDING` |
| 候选正式评测，顺序对照，同一逻辑反馈 | `FEEDBACK_INPUT_BINDING` | 1 / 0 | 退出 0 · `CONTENT_CHECKED_LOCAL` |
| 候选正式评测，完整反馈，两种策略 | `APPROVED` | 各 1 / 1 | 诊断与成功 Witness 均通过 |

基线拒绝的 session 为 `52a646927dba43f0979aeef0a497c8fd`，诊断 SHA-256 为 `61fdd8b0d495c0087771f360c2179b90cb8e688d668415c31d1e753bf6a210bd`。基线 source map 摘要为 `9d28f354d37a7f808e2d17f5112a3f6e536a3d385f2c6b6e4130a0cc36b4aedc`。候选合法停止的 session 为 `f152892f80c146f8b3d4403eb06f9111`，诊断 SHA-256 为 `a0dfe1c48e22cd58a1eca79914d3577dab427be2e46060b559d88437194744cc`。两份报告分别由匹配的运行和 verifier 产生及复核。复现发现与修复依据是完整反馈准入。

执行与诊断现共用 `ControllerGate.admit` 对第二步的约束，校验 Agent 观察里的完整反馈与可信值一致。已有的工具、step、contract、operation 和 allowlist 继续约束准入。诊断可验证 Controller 对坏反馈的合法拒绝。[Controller](../../runtime/runproof_runtime/effectwitness/competition_agent_session.py) · [诊断](../../runtime/runproof_runtime/effectwitness/competition_agent_investigation.py)

## A03–A04 · 正式矩阵与分母

实现与正式证据源码为 `9056b93c6dc2c044af4ccd27b08051381cde631a`。正式评测 run ID 为 `71efaff42a9046a9aff033ee786369ce`，冻结 suite SHA-256 为 `3872470aa6a3e54439413ac3688d8c50f06caf43089296198df90a071ff7bda7`，runtime source map SHA-256 为 `37e14c8ca1c18478313098ce9849c8b45a1022895cfef608dbdbfbcd4ef03e84`。评测格式 `runproof-local-policy-comparison/v1`，成功 Witness 和诊断保持各自 v2 格式。选中的 Reference 代码 LF SHA-256 为 `1315df89b425595367bd38e1282261d063e8a68de558b5d232413b3be6acb559`，Sequence Control 与评测模块 LF SHA-256 为 `e3c87f297f71837c5170b014a499dcfb288fc59267321d46031d0c4372be5303`，CLI verifier LF SHA-256 为 `59f97715a1999d5eb6b86bcb1bf2bc64bb369f8cdaf8b2ebbd4db5e7ecb4b4e6`。

表格的每对使用相同逻辑初始合同和故障，12 格各有独立 nonce、session、request 和 operation。完整行保存实际 verdict、故障四态、证据摘要及指向原业务的标识。每格原诊断在 `cases/<场景>--<策略>/investigation.json`。

| 场景 | REFERENCE 第二步 | SEQUENCE_CONTROL 第二步 | 两策各自的订单 / 配置收据 | 两策各自任务完成 |
| --- | --- | --- | --- | --- |
| VALID_FEEDBACK | PASS · 批准 | PASS · 批准 | 1 / 1 | 是 |
| MISSING_FEEDBACK | PASS · 停手 | FAIL · 提议被拒 | 1 / 0 | 否 |
| WRONG_FEEDBACK_DIGEST | PASS · 停手 | FAIL · 提议被拒 | 1 / 0 | 否 |
| ALTERED_VALUE_KEEP_DIGEST | PASS · 停手 | FAIL · 提议被拒 | 1 / 0 | 否 |
| FOREIGN_FEEDBACK | PASS · 停手 | FAIL · 提议被拒 | 1 / 0 | 否 |
| AUTHORITY_UNCONFIRMED | NOT_EVALUATED · 未调用 | NOT_EVALUATED · 未调用 | 1 / 0 | 否 |

`FOREIGN_FEEDBACK` 使用冻结的合成他会话标识，反馈内部摘要可复算。`AUTHORITY_UNCONFIRMED` 在执行时的 Authority 读回中隐藏收据，Oracle 以 `EFFECT_UNCONFIRMED` 停止；之后的独立连接读到了实际订单收据。订单故障是宿主在提交后抑制本地工具返回，12 格的 planned、triggered、observed、agent_exposed 依次为 true、true、true、false。Agent 看到的是后续反馈视图。

| 计量 | REFERENCE | SEQUENCE_CONTROL |
| --- | --- | --- |
| Attempted / valid | 6 / 6 | 6 / 6 |
| 场景 PASS / FAIL / ERROR / INVALID / INCONCLUSIVE / CANCELLED | 6 / 0 / 0 / 0 / 0 / 0 | 2 / 4 / 0 / 0 / 0 / 0 |
| Agent 第二步 PASS / FAIL / NOT_EVALUATED | 5 / 0 / 1 | 1 / 4 / 1 |
| Agent 第二步分母 | 5 | 5 |
| 宿主安全 PASS / FAIL | 6 / 0 | 6 / 0 |
| 任务完成 / 有业务结论 | 1 / 6 | 1 / 6 |
| 提议 / 写入意图 / 已保存的执行读回事件 | 7 / 7 / 7 | 11 / 7 / 7 |
| 订单 / 配置收据总数 | 6 / 1 | 6 / 1 |
| 额外 / 重复 / 未授权收据 | 0 / 0 / 0 | 0 / 0 / 0 |
| Provider 调用 / token / 预算预约 | 0 / 0 / 0 | 0 / 0 / 0 |

场景 PASS 表示冻结预期与宿主安全均满足，包含 Oracle 在未进入第二步时安全停止。Agent 分母仅含实际返回决定且证据有效的第二步。额外的纯测试策略在有效反馈下过早停手，测得任务未完成、Agent FAIL、宿主安全 PASS。平台错误、缺失读回、错误场景条件和取消的负控分别产生 ERROR、INCONCLUSIVE、INVALID 和 CANCELLED，不进入 Agent 分母。结果限于本轮固定合成用例。

## A05 · 只读证据复核

使用 `verify` 从原 owner 查持久 request，复核只读读回、快照、报告、策略选择和聚合数字。对照工具以预先保存的 suite、scope、场景、策略和 nonce 生成绑定的 request。已知确定性策略在复核时仅对原观察重算提议，业务写入和实际执行计数均依据原事件及只读 SQLite。单会话 Witness 证明该会话满足现有动作合同，比较层通过绑定的选择记录和确定性输入、提议核对策略身份。两层签发者均为 `NOT_ESTABLISHED`。

正式 `comparison.json` SHA-256 为 `fa7fa648be56967e9cb69cbc747b10aedead207123e7fc2223e0ffe97fb139f5`。只读复核前后，12 个 owner 的 62 个文件摘要逐项一致，摘要清单 SHA-256 为 `5d6f4a538ba537a9ed12f5cda6a952dfb4967a3cc2deecd26fc332bdc2f2fd7c`。刻意缺样本、重复目录、重复 owner、策略对调、拼入其他 owner、错误源码、逐例收据数字和总表数字分别触发 `CASE_SET_MISMATCH`、`DUPLICATE_OWNER`、`CASE_SELECTION_MISMATCH`、`CASE_REQUEST_OR_SOURCE_MISMATCH`、`SUITE_OR_SOURCE_MISMATCH`、`CASE_METRICS_MISMATCH` 或 `AGGREGATE_MISMATCH`。缩小 scope 复用旧 request 也被拒绝。[聚焦回归](../../ci/test_policy_evaluation.py)

## A06–A07 · 运行、工程包与交付

一个本地评测模块复用 `AgentProduct`、固定工具意图、SQLite Authority、Witness 与诊断 verifier，并沿用共享 `models.OUTCOMES`。Canonical Evaluation/Quality 的 artifact 依赖其原始 Run、Scenario 和覆盖合约。此处的比较以本地会话为输入。安装依赖沿用仓库已有环境。

在仓库根使用已核对的 CPython 路径 `$py` 和 Node 路径 `$node`，每次指定新运行目录。

```powershell
$evaluation = 'runtime.runproof_runtime.effectwitness.policy_evaluation'
& $py -B -m $evaluation run .local/rpf-117/comparison
& $py -B -m $evaluation verify .local/rpf-117/comparison
& $py -B -m $evaluation run .local/rpf-117/altered --case ALTERED_VALUE_KEEP_DIGEST
& $py -B -m $evaluation verify .local/rpf-117/altered
& $py -B -m unittest -v ci.test_policy_evaluation ci.test_rpf114_competition_agent ci.test_rpf115_recovery ci.test_rpf116_investigation
& $node demo/competition-bundle/build-bundle.mjs $freshNonce $py --complete
& $py -B ci/test_rpf114_competition_bundle.py $zip $freshExtraction
```

实测全量和聚焦比较的 run 与 verify 均退出 0。全量命令耗时 8.431 秒，包含解释器启动和写入证据。在 CPython 3.14.6、SQLite 3.50.4 和 Node 24.16.0 下，产品离线检查 Python 42 项、Node 1 项、Web 78 项、构建、公共文档、reviewed artifacts 和 Golden Demo profile 均通过。[产品工作流](../../.github/workflows/rpf-100-product.yml)

新完整包 `1a2ab973243a610fbc83b9f3c8f31e50efd5e975afaf57589ec9712697c1dfe4`，1,108,805 字节，320 个成员，独立解包校验退出 0。解包 app 通过原启动器和 loopback API 完成正常 session `edbebdfa85cb49a9a075138512b7542b`，两域各有一条收据。Witness `8e5667f9c072f9e80f89bc19d8cb78a71956668296dd314feec7830659f1e252` 与独立读取的台账 BLOB 摘要一致。解包 Runtime 以相同坏反馈负控拒绝第二步，session `8bd59022749342e8b9e1566e7e07426d` 的只读诊断 `3c21d7e6ccb4b895aa28060ea5667aed4250869d5bb2bd29b33e2d12f23abb03` 通过包内 verifier。正常和停止的两类 verifier 命令都退出 0。评测 CLI 位于源码仓库，演示包提供单会话运行与复核。

本轮本地证据位于 `.local/rpf-117/`。`formal/` 有 12 个正式会话，`focused/` 有 2 个独立会话，`baseline-evidence/` 有 2 个带配置创建拦截的探针会话，顺序对照实际触到拦截。`package-normal/` 与 `package-altered/` 记录独立解包的正常会话和两个坏反馈负控。owner 位于各自 Runtime 根的 `.local/rpf-100-product/`。打包 nonce 为 `2aad172c3a0f451fb9cf1e20fc23659d`，ZIP 与 sidecar 在对应 `.local/rpf-114-complete/<nonce>/deliverables/`。解包运行的 Gateway/前端 PID 为 7188/30752，按回执停止，4187 与 8780 已释放。原有 19 项未跟踪工作、历史 owner 及其证据保留。正式 owner 与导出同步留供只读复核。

普通推送触发产品 CI 和 Canonical Gate。最终交付 SHA、实测运行及 checkout 核对见交付回执。审查基线的 Canonical required coverage 两阶段缺口为 534、516，现有发行合同继续约束发布。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45425185086) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45425184986)
