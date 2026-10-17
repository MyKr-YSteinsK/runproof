# RPF-42｜订单域两轮证据反馈探索

Runtime 入口仍为 `runtime.runproof_runtime.effectwitness`。RPF-42 增加真实 Exploration Agent 的结构化实验选择、权威反馈回注、共享预算及固定 B0。目标业务由 **DETERMINISTIC_CONTROLLED_TARGET** 执行真实 SQLite 事务；本轮没有把每个退款 target 称为 live LLM。

## 运行

从仓库根使用已有 Python 3.12+，仅需标准库。Windows 本次 live 用已有 uv Python 3.12.13：

```powershell
$pilotPython = Join-Path $env:APPDATA 'uv/python/cpython-3.12.13-windows-x86_64-none/python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP = Join-Path (Get-Location) '.local/rpf-42'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
[void][IO.Directory]::CreateDirectory($env:TEMP)
& $pilotPython -m runtime.runproof_runtime.effectwitness --help
& $pilotPython -m runtime.runproof_runtime.effectwitness --self-check
& $pilotPython -m unittest discover -s runtime/tests -p 'test_effectwitness_*.py' -v
```

没有该解释器时选用自己已有的 Python。`--help` / `--self-check` 不写文件、不联网。默认、`--demo` 和原 `--live` 的 RPF-41 业务语义、默认路径与单次 live 账本保持兼容；RPF-42 不应操作旧 `.local/rpf-41/`。旧 Pilot 测试仅在 fixture 生命周期临时重定向本包的 workspace 常量到 RPF-42，避免测试碰旧任务产物，产品配置没有改变。

免费 CLI 演示为：

```powershell
& $pilotPython -m runtime.runproof_runtime.effectwitness --pge-demo
```

它运行 `normal → response-lost` 的 **MOCK_POLICY_ONLY** 选择夹具，然后运行 B0，四个新沙箱都真实执行和清理；Provider 为零，不能充作 L1/L2 live 证据。本 Plan 已完成4/4轮非单元测试实验，执行期间仅在 unit fixture 中验证这个演示命令，没有额外跑一组真实 CLI 演示来超用额度。未来执行须遵守当时任务的实验预算。

显式付费入口（仅在已有 API/费用授权和进程已安全持有 `DEEPSEEK_API_KEY` 时）：

```powershell
& $pilotPython -m runtime.runproof_runtime.effectwitness --pge-live
Get-Content -LiteralPath .local/rpf-42/live-result.json | ConvertFrom-Json
```

本 Plan 的唯一 live 已完成。存在 `.local/rpf-42/live-result.json` 时，入口在发请求前拒绝，不能删账本或换会话绕过额度。没有自动重试或崩溃后自动恢复。不要为重跑本轮而调用旧 `--live`。

完整 Runtime 回归使用已有 OTel 1.44.0 的 Python 3.14.6，无须安装依赖：

```powershell
python -m unittest discover -s runtime/tests -p 'test_*.py' -v
```

本次111项测试成功，2个 Docker 组因 provider unavailable 跳过；新增12项 PGE + 原19项 EffectWitness 测试在3.12.13通过。精确事实见 [RESULT.md](RESULT.md)。

## 冻结、预注册与选择空间

`pge_contracts.SessionPlan` 在请求或实验之前冻结 canonical bytes、UTC 时间和 SHA-256，包含候选全集、额度、目标、指标版本、adapter revision、source digest 和 B0 顺序。`rpf-exploration-session-v1` 不允许外部新增候选/脚本/路径/网络参数。

| ID | 业务执行与故障控制 | 可观察事实 |
|---|---|---|
| `normal` | fresh PAID 订单，退款一次，无注入 | NOT_PLANNED；真实退款/收据 |
| `planned-untriggered` | 原 `planned-not-triggered`，故意抑制触发的负向控制 | planned=true，NOT_TRIGGERED；不得宣称触发过故障 |
| `response-lost` | 原 post-commit response-lost；提交后隐藏业务响应 | UNKNOWN → 独立 receipt reconcile；无盲重放 |

预注册 B0 固定为目录顺序前两项 **`normal → planned-untriggered`**，冻结位置是 SessionPlan 的 `baseline_order`；live ledger 的 `plan`/`plan_digest` 保存实际时间和摘要。B0 在 PGE 完成后才执行，其顺序与实际结果都不交给模型。这个简单固定前缀不是优化过的最佳基线，单案例差异不能推导算法优势。

模型唯一工具是 `select_experiment(candidate_id)`，枚举始终含全部3项，两轮同样注册。可以重复同一候选；不硬过滤重复、不指定第二候选、不把免费 demo 顺序用于 live selector。初始可见内容为候选规格、固定业务合同摘要、2轮额度、空反馈和覆盖目标，不含候选未来 outcome/B0 结果/authority 路径。

每轮 `Execution v1 / Effect v1` 保留原语义；新增严格 `rpf-experiment-v2`，绑定 `owner=rpf-42`、session ID/digest、policy/candidate。v1 仍只接受原 owner/字段。每次生成新的 Run/Environment/Order/Operation，使用 `.local/rpf-42/<run-id>/orders.sqlite3`，业务事务/Reader/Verifier仍是原实现。

## 执行、反馈与预算

```text
Frozen SessionPlan / shared SessionBudget / exclusive Ledger
  → real Explorer select_experiment
  → fresh v2 trial → OrderAdapter → SQLite transaction
  → AuthorityReader → OrderEffectVerifier → owner reset / cleanup
  → validated canonical Feedback + hash → role=tool in request 2
  → real second choice / fresh trial → preregistered B0 → comparison
```

`exploration.py` 不复制退款逻辑；`_TrialBudget` 把 Orchestrator 的业务 Tool step 转账到同一个 SessionBudget，没有每 trial 新满额度。所有物理 trial（含无故障控制）计入4轮总额，PGE/B0各最多2轮。总上限：4 Provider requests、16 steps、12,000 tokens、¥1.50估算、20分钟；socket timeout最多90秒，输出128 tokens/request，0自动重试。steps包括 Provider请求、每次选择及业务工具；成本只计 Provider，B0为零。原 `provider.drive` 保持单次 Pilot 行为，新增窄 `request_completion` 给 Explorer 复用原预算方法及同一HTTP限制。

Ledger 独占创建，并在任何 socket/业务副作用前 flush/fsync 预留。写入中崩溃可能留下损坏 JSON，但路径仍占用、重启不能开始新会话；这是 fail-closed 账本，不是通用事务恢复服务。未知 usage 关闭后续请求，tokens/费用为 null；保留已确认使用量。输入预留沿用本 ASCII 窄模板的 UTF-8 bytes+1024 framing 上界，非任意 tokenizer 通用证明。

`project_feedback` 在真实 authority/verifier 执行后检查合同/session/candidate、reader/verifier版本、owner、状态/收据 hash 和 fault provenance，再投影白名单。发送字段包括 candidate/run/experiment/source refs、before/after/receipts摘要、Run/Effect/Fault 分层结果、证据缺口、历史事实覆盖、新事实集合与剩余额度。第二次请求前保存精确 canonical feedback 内容/hash、message/body hash、Tool Call ID和顺序事件。模型的隐藏推理与自由文本不持久化，合法 Tool call仅保留必要字段并 canonical 化参数。

`observable-fact-set-v1` 的信息增益代理为本 policy 首次观察的有效 `effect:<outcome>`、`activation:<status>`、`recovery:RECONCILED_COMMITTED_RECEIPT` 事实数，不是 Shannon 熵。重复的全新 run/receipt ID 不算信息增益。来源/恢复未确认时停止，不通过“换 ID”增加信息。

L1要求两次实际选择/反馈链路；L2另外要求本案例候选不同、第二轮有新增事实及真实第一轮反馈输入关联。免费 Mock 永不标 L1/L2。合法重复或无增益即 H1 NOT_PROVEN，不能通过追加会话改结果。结果 attribution 仅 `CORRELATIONAL_ONLY`。

## 清理、证据和限制

每 trial 在确认业务终态后按 owner/generation reset、读回零收据，只删除其确切 SQLite 文件和空目录。UNKNOWN先 reconcile；失败时保留未决DB并移到 `.local/quarantine/rpf-42/<run-id>/`，停止后续 PGE/B0。无法移动则报告原位路径。没有强制删除入口。测试故障 fixture 会先恢复 authority、确认单笔收据，再清理其本次状态。

最后只保留 `.local/rpf-42/live-result.json`；含4轮实际摘要和两次请求/反馈链，未提交，也未保留原始Provider消息。Reader的临时HMAC不导出，因此这些hash与顺序是执行者提供的可复核摘要，Main不能由它独立重放远端Provider或离线证明签发者。本轮未签发Witness、没有LLM target费用、没有第二域/UI/WorkSwarm实装。

费率在2026-10-17核对：[官方 Pricing](https://api-docs.deepseek.com/quick_start/pricing/)、[官方 Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)。本次请求 `deepseek-flash`，官方映射 DeepSeek-V4.1-Flash-1017；按peak input cache-miss $0.30/M、output $1.20/M、USD→CNY=10估算上界，非账单/市场汇率。没有安装新依赖、SDK或WorkSwarm；`WORKSWARM_NOT_PROVEN`。
