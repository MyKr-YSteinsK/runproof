# RPF-49｜真实 Target Agent 响应丢失与自主对账验证

**Plan:** RPF-49 / rev-2（rev-1：`UNEXECUTED / SUPERSEDED`）

**Status:** `COMPLETE`
**结论：** 一条真实 DeepSeek + Pydantic AI Target Trial 中，Agent 在 refund 已提交但响应丢失、工具返回 `UNKNOWN_OUTCOME` 后，自行发起 `reconcile_order`，接收真实工具返回并完成恢复。独立 Authority、确定性 Oracle 和锚定离线核验均支持 `AGENT_RECOVERY_VERIFIED`。全部 A-01～A-08 Gate 通过。

## 1. 身份、边界与交付

- 仓库：`D:\CS\runproof`，remote：`https://github.com/MyKr-YSteinsK/runproof.git`（`MyKr-YSteinsK/runproof`）。
- 精确 base/parent：`8241ebb1a96be54ec56ce384b63b4789efc4dac9`，分支：`codex/rpf-49-target-agent-recovery`。
- 预检观察的 `main`：`bda0cd49e50e3181f604324e94877a24b9885334`；该分支起始时远端不存在。提交和推送后会在最终聊天回执给出独立核验的 remote SHA。
- 初始工作区在 Plan parent 上；只见到既存、未跟踪的 `docs/reviews/`。该目录未读取、枚举、修改、移动或暂存，始终保留原状。
- 仅修改 Plan 白名单中的 10 个文件：4 个既有 EffectWitness 模块、1 个 Recovery 模块、1 个针对性测试文件、`spikes/rpf-49/{README.md,RESULT.md,probe.py,recovery-summary.json}`。无依赖/lock、Web、Java、CI、Project State、历史证据或 RPF-00～48 文件改动；未触及相邻仓库。
- 未创建 PR、未合并 main、未发布、未部署、未提交赛事材料。没有生产或真实支付操作。

## 2. 实现与身份语义

- `target_driver.py` 将 RPF-48 沙箱、锁、账本和 Agent driver 的本地存储位置显式参数化；默认仍为 `rpf-48`，本次新 Trial 的物理所有权为 `storage_task="rpf-49"`。`contracts.py` 与 `orders.py` 仅增加该精确任务路径许可。RPF-48 已有业务事务、Tool guard 和 Oracle 语义未改。
- `target_contracts.py` 只为本任务建立窄预算入口，未放宽历史 v1 身份。逻辑合同仍为 `rpf-target-experiment-v1`、owner=`rpf-48`；物理账本/沙箱 owner=`rpf-49`。证据同时记录两者，没有声称新的独立 issuer。
- 新增纯离线 `target_recovery.py`，在兼容 `rpf-target-evidence-v1` 的事实基础上严格验证真实恢复顺序、Agent reconciliation、Tool Call ID 与参数/返回摘要、SDK 后续请求回注、唯一 receipt、Authority 和 Oracle、预算及清理。只在外部 SHA 锚定且事实全部成立时返回 `AGENT_RECOVERY_VERIFIED`；缺锚为 `NOT_PROVEN`。
- 新增 `test_effectwitness_target_recovery.py`。RPF-48 的 Target verifier、驱动/Host 和业务 Oracle 沿原实现复用；没有修改历史证据或旧 verifier。
- SDK：`pydantic-ai-slim==2.57.0`、`openai==3.35.1`；隔离环境为任务目录 `.local/rpf-49/venv`、Python 3.12.13。摘要记录 SDK source SHA-256 `70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa`、Pydantic AI wheel SHA-256 `a07d732e09df8d51f22bd3be2ad45ab644721a904809a2481146bf5d7bb47c67`，以及执行文件摘要、版本与 wheel/许可证核验记录。`uv pip check` 通过（26 packages）。
- 实施路线偏离：没有改写 `target_evidence.py` 或复制第二套 Driver；保留 v1 兼容事实块，并在单独的窄恢复 verifier 中追加恢复断言。

## 3. 零费用 Fixture 与协议负控

- 付费前以固定 SDK 执行了零 Provider fixture Tool Loop：4 个模拟模型请求、`inspect_order → refund_order → reconcile_order`、3 个工具结果回注；408 个合成 tokens、Provider HTTP attempts=0。Fixture 明确标为 `FIXTURE_TEST_ONLY`，不算 Live 证据。fixture 摘要 SHA-256：`409d29c4d45acdb14603a0f3c065bb0b38c774a55059a35256fa91af2076d86e`。
- 新增 8 项 Recovery 定向测试覆盖 v1/物理 owner 分离、Trial/HTTP 预算、未知 usage 阻断后续调用、Agent 必须 reconciliation、工具返回绑定、缺/错锚与篡改、锁和崩溃隔离。原 Target Agent 16 项测试覆盖 observe-first、未知结果禁止盲目重复 refund、伪造/重复 call ID、超时、未知 usage、预算、child guard 和 loopback 授权。
- 三种重算并重新锚定的对抗样本分别删除 reconcile 事件、伪造 reconcile call ID、篡改 reconcile 结果摘要，均被拒绝（退出码 3；分别为 `TARGET_FAULT_MISMATCH`、`TARGET_TOOL_ORIGIN`、`TARGET_TOOL_CONTENT`）。这不修改正式 summary。

## 4. 唯一真实 Trial

- Run：`target-recovery-b5312514b08b4dadbb1594a64eece8a3`；受控故障固定为 `response-lost`。真实模型 `deepseek-flash` / `DeepSeek-V4.1-Flash-1017`，通过父进程固定 HTTPS 代理；Target Agent 子进程没有 Provider key，使用受限 loopback Host。进程退出 0、stderr 0 bytes、自动重试 0。进程绑定证据声明为进程内能力/loopback token，**不是 OS 级来源证明**。
- UTC `2026-10-18T07:39:35.518Z` 至 `07:39:46.162Z`，10.641 秒、7 Host steps。Provider 共 4 次 HTTP requests；3,571 input + 390 output = 3,961 tokens，usage 全部已知。
- DeepSeek 官方峰时 `deepseek-flash` cache-miss 输入价 `$0.30/百万 tokens`、输出 `$1.20/百万 tokens`；按 ¥10/USD 上界换算为 ¥3/百万输入、¥12/百万输出。本次 RPF-49 顶层估算上界为 **¥0.015393**（低于 ¥1.00 上限）；这是估算，不是账户实际账单。嵌入的 RPF-48 v1 兼容事实块保留旧口径 ¥0.010262；费用判断只用顶层 RPF-49 `task_usage`。价格来源：[DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。

真实 SDK Tool Call 与回注链如下（参数和结果均以 SHA-256 绑定）：

| Provider response | Tool Call ID | 工具与结果 | 参数 SHA-256 | 结果 SHA-256 | 返回给模型请求 |
|---|---|---|---|---|---:|
| `b1708bf5-ed54-4b89-8a9f-aabb6ad451e8` | `call_00_KwfPbU8O5BbXLUsaoySd9265` | `inspect_order` → `PAID`, revision 0 | `a070497e207d2c1360ce9e8848a13e26bb128a313f8f4122114f77d75f2ce31f` | `a7caa6f4d04f793dde47deb43f3f4079ca5de58bc7150a11a07609c62617f273` | 2 |
| `08f1a111-d736-4225-a9f7-17aab6ab4afd` | `call_00_7Ym1lR32BfpgC2lDva7H5493` | `refund_order` → `UNKNOWN_OUTCOME / CONTROLLED_POST_COMMIT_RESPONSE_LOSS` | `6157868d20a53c1185cee321f9f2965bb36bfb2886dccbd4bae741e3ce41324a` | `727b1f772db42ab7771396fd5abfc2f351ce03e347bd9daed6fb3d91f27e49b7` | 3 |
| `1215d35f-83fb-4f20-b171-afa78d12ba98` | `call_00_bJyRdDhjooZKvPQGK7fn8278` | Agent 发起 `reconcile_order` → `RECONCILED_COMMITTED` | `e6344fa74f141207349ef1f07b5adbe18ec59b1e14aeedf63b439432a6dea3f2` | `b9682907839055d152443e04dbf0984f293c89d07de6fc871fa05b551963c250` | 4 |

第 4 个模型请求无工具调用，并包含前述三个 Tool Call ID 与返回摘要。故障 `planned / triggered / observed / reconciled` 全为 true；reconcile 发起者为真实 Target Agent，`controller_reconciliation=null`，没有 Controller 代替 Agent 成功。

独立 Authority 的提交前状态为 `PAID`、revision 0、退款 0、receipts 0；提交后为 `REFUNDED`、revision 1、退款 2,500 CNY minor，且仅有一个 committed receipt：`receipt-8a58a40ea6d958736db56db2`，金额 2,500 CNY minor。独立 Oracle 为 `CONTRACT_SATISFIED_IN_RUN`，无 evidence gap、无 violated rule。

四个结果维度分开记录：`fault_activation=TRIGGERED_AND_OBSERVED`；`agent=RECOVERED`；`business_effect=CONTRACT_SATISFIED_IN_RUN`；`recovery_verdict=AGENT_RECOVERY_VERIFIED`。没有据此生成违规结论或失败 Witness。

## 5. Recovery Evidence、离线核验与信任边界

- 唯一提交的实际恢复摘要：[`recovery-summary.json`](recovery-summary.json)，13,399 bytes，SHA-256 `04ac629bbfb54a4b85eddf902bbf765db7c57ea0c509e0b539280858c7d4bc9b`。提交前该 SHA 被作为独立已知锚传给核验器。
- 正确外部锚：退出码 0，`CONTENT_VERIFIED_ANCHORED`，verdict=`AGENT_RECOVERY_VERIFIED`。缺锚：退出码 2，`CONTENT_CHECKED_UNANCHORED`，verdict=`NOT_PROVEN`。错误外部锚：退出码 3，`REJECTED / RECOVERY_EXTERNAL_ANCHOR_MISMATCH`。
- 正确锚的实际摘要命令：

  ```powershell
  python -B -m runtime.runproof_runtime.effectwitness.target_recovery spikes/rpf-49/recovery-summary.json --expected-sha256 04ac629bbfb54a4b85eddf902bbf765db7c57ea0c509e0b539280858c7d4bc9b
  ```

- verifier 的纯离线导入检查通过；测试导入阻断 `sqlite3`、socket、HTTP、urllib、SSL、Pydantic AI、OpenAI 与 Pydantic。验证只读取 JSON 并重算内容，不访问 SDK、数据库或网络。
- SHA-256 锚绑定文件字节，不建立 issuer authenticity、OS 级进程来源证明或生产真实性；本结果只适用于本地受控模拟订单，不宣称因果归因、独立重现或跨模型泛化。

## 6. 预算、清理与验证结果

- Trial 账本 reservation 在网络调用前持久化；不可重置。最终账本为 1/1 Trial、4/6 Provider requests、3,961/12,000 tokens、¥0.015393/¥1.00 估算上界、7 steps、retry=0，状态 CLOSED；usage known。没有超限、未知 usage、错误或未决业务结果。
- 仅 RPF-49 task-owned Provider、订单、锁与 child process 路径参与本次执行。Authority 核实终态和 receipt 后执行 reset generation 1 并移除 Trial sandbox；reset 后 receipt count=0，锁、SQLite 和 Trial 目录均已移除。账本保留为不可重置审计状态，没有缓存或 unresolved 业务 quarantine。
- 新定向测试：

  ```powershell
  py -3.14 -B -m unittest runtime.tests.test_effectwitness_target_recovery -v
  ```

  退出码 0，8 tests passed。
- RPF-48 Target 回归在隔离镜像 `.local/rpf-49/regression-src` 执行，避免旧 `.local` 被测试写入：`py -3.14 -B -m unittest runtime.tests.test_effectwitness_target_agent -v`，退出码 0，16 tests passed。
- 完整 Runtime 回归同样在 `.local/rpf-49/regression-src` 执行：`py -3.14 -B -m unittest discover -s runtime/tests -p 'test_*.py' -v`，退出码 0，共 189 tests：187 passed，2 skipped。Docker 不可用导致 Docker integration 与 RPF-05 Docker 测试 SKIP，不计为通过。
- 历史 RPF-48 成功摘要以 SHA-256 `c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2` 核验为 `CONTENT_VERIFIED_ANCHORED`；RPF-43、RPF-44 原 Witness 分别以既有锚通过 `VERIFIED_ANCHORED`（退出码均为 0）。未读写旧付费账本。
- `git diff --check` 通过。最终只对白名单 10 个文件定向暂存并检查；未使用宽泛暂存。无密钥或 Provider credential 被写入源代码或证据。

## 7. A-01～A-08 验收

| Gate | 状态 | 证据摘要 |
|---|---|---|
| A-01 身份与权限 | `PASS` | parent、main、分支、remote 和精确写入白名单已核实；受保护目录和旧付费区未访问；独立分支交付。 |
| A-02 Task-owned 兼容 | `PASS` | 默认 RPF-48 路径保持；RPF-49 使用隔离存储；v1 owner 与 storage owner 明确分离；旧 Target tests 16 passed，RPF-48 旧摘要锚定通过。 |
| A-03 恢复协议与负控 | `PASS` | Fixture 0 Provider requests；Agent reconciliation、回注和 Host guard 测试通过；缺/错锚及三类伪造/删改控制按预期拒绝。 |
| A-04 Live Target 自主恢复 | `PASS` | 唯一真实 Trial 中故障确已触发；`UNKNOWN_OUTCOME` 后由模型发起 reconcile 并收到回注；Authority/Oracle 和新 verifier 成功。 |
| A-05 独立 Recovery Evidence | `PASS` | 13,399-byte 摘要、SHA、外部锚、离线 verifier、缺锚降级和错锚/篡改拒绝均已核验；issuer 仍未建立。 |
| A-06 硬预算和不确定态 | `PASS` | 1 Trial、4 requests、3,961 tokens、¥0.015393 估算、7 steps、retry=0；usage 均已知，账本 CLOSED。 |
| A-07 回归与清理 | `PASS` | 新测试 8 passed，Target 回归 16 passed，完整 Runtime 187 passed/2 Docker SKIP；RPF-43/44/48 历史摘要核验；本轮 sandbox 已精确清理。 |
| A-08 Git 与结果 | `PASS` | 本文件为唯一正式 `RESULT.md`；定向白名单提交、普通 Push 和独立 remote SHA 复核在收口阶段完成。无 PR、main merge、deploy 或 publish。 |

## 8. 下阶段建议

仅将“受控业务真实违规 → 失败 Witness”作为后续候选。没有创建 RPF-50 或其它 Plan；是否接受证据、推进阶段及后续范围由 Main 审核。
