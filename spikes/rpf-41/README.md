# RPF-41｜受限订单退款 Effect Pilot

这是 `runtime.runproof_runtime.effectwitness` 的复现入口。默认免费，在任务所有的 SQLite 沙箱中退款一次，通过独立只读连接读回后判定，再 reset 并移除数据库。所有订单与金额均为虚构模拟数据；没有支付服务连接。

## 从仓库根运行

仅需 Python 标准库。新包在 Windows Python 3.12.13 和 3.14.6 均经过测试。本次 live 使用 uv 已有的 3.12.13；不要为了运行本包安装 WorkSwarm 或依赖：

```powershell
$pilotPython = Join-Path $env:APPDATA 'uv/python/cpython-3.12.13-windows-x86_64-none/python.exe'
& $pilotPython --version
$env:PYTHONDONTWRITEBYTECODE = '1'
& $pilotPython -m runtime.runproof_runtime.effectwitness --help
& $pilotPython -m runtime.runproof_runtime.effectwitness --self-check
& $pilotPython -m runtime.runproof_runtime.effectwitness --demo
& $pilotPython -m unittest discover -s runtime/tests -p 'test_effectwitness_*.py' -v
```

若该解释器不存在，使用自己已安装的 Python 3.12+；`python` 在本次机器上是 3.14.6。`--help` / `--self-check` 无文件或网络副作用；无参数等同 `--demo`。免费演示 JSON 输出到 stdout，数据库位于 `.local/rpf-41/<fresh-run-id>/orders.sqlite3`，正常结束自动清理，不保存额外结果文件。

旧 Runtime 完整回归需要仓库既有 OTel 依赖。本次直接使用已有 Python 3.14.6 + OTel 1.44.0，没有安装新依赖：

```powershell
[void][IO.Directory]::CreateDirectory((Join-Path (Get-Location) '.local/rpf-41'))
$env:TEMP = Join-Path (Get-Location) '.local/rpf-41'
$env:TMP = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s runtime/tests -p 'test_*.py' -v
```

## 显式 live 与单次会话门禁

```powershell
# 仅在已有明确 API/费用授权、DEEPSEEK_API_KEY 已安全设置的进程内执行：
& $pilotPython -m runtime.runproof_runtime.effectwitness --live
Get-Content -LiteralPath .local/rpf-41/live-result.json | ConvertFrom-Json
```

RPF-41 的必要 live 已完成，现存账本会让再次 `--live` 返回退出码 2，网络请求为零。不要删除该账本以绕过本 Plan 的一次会话限制；未来重新授权的会话需要明确的新任务预算。没有自动重试或恢复执行接口。

会话启动以独占创建 `.local/rpf-41/live-result.json` 预留资格；每次连接前在同一文件写入请求序号和预算预留，并 flush/fsync。请求经 `http.client.HTTPSConnection` 直连固定 DeepSeek 端点，不读取代理配置。最多 4 requests、8 Provider/Tool steps、10,000 tokens、¥1 估算、20 分钟；socket timeout 最多 90 秒，输出每请求最多 256 tokens。UTF-8 请求字节数加 1024 framing tokens 作为本 ASCII 协议的保守输入预留；未知 usage 关闭后续请求，累计 tokens/费用显示 null 并保留已确认部分。此输入上界针对当前窄模板，不是任意聊天 tokenizer 的一般证明。

费用按执行时官方 Flash peak cache-miss input $0.30/M、output $1.20/M，采用 USD→CNY=10 的保守换算上界；不是账单或市场汇率。来源：[官方定价](https://api-docs.deepseek.com/quick_start/pricing/)、[官方 Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)，核对日期 2026-10-17。`WORKSWARM_NOT_PROVEN`；使用经过本轮实际验证的窄 HTTP driver。

## 合同和职责

```text
CLI → FrozenContracts → Budget / Orchestrator → DomainPort.invoke
                                                ↓
                                         SQLite 业务事务
                                                ↓ 独立只读连接
                 OrderEffectVerifier ← AuthorityPort.read / reconcile
```

`contracts.py` 严格验证并以 canonical JSON bytes 冻结三合同，各自 SHA-256；Experiment 绑定 Execution/Effect 摘要。`rpf-agent-execution-v1` 限定 driver、tools、budgets；`rpf-order-effect-v1` 定义 PAID 的 CNY 全额退款、固定订单/operation/amount、一次收据和 revision 0→1；`rpf-experiment-v1` 绑定 owner、run、scenario、environment revision、generation 0 和 fault。版本语义规定 UNKNOWN 先 reconcile，reset 后必须新建 Experiment。当前没有任意外部合同文件/路径入口。

`orders.py` 用 `BEGIN IMMEDIATE` 将订单更新与收据插入置于同一事务，operation 主键及 order 唯一约束支持幂等、拒绝第二笔退款。业务 Tool 只接冻结参数；Authority Reader 的路径不交给模型。Reader 从另一个 SQLite `mode=ro` / `query_only` 连接读事务快照；Verifier 不读取 Tool response 或 Agent 文本。

Authority 快照包含 reader/version/source/environment 身份和内容 hash。每个 Reader 的临时 HMAC seal 用于拒绝通过普通接口伪造的快照对象，密钥与 seal 不持久化。它只隔离代码职责与数据来源，**不提供同进程恶意 Python/管理员的安全隔离，也不能离线验证签发者**。保存的 JSON/hash 是运行事实摘要，不是正式 Witness Certificate。

`engine.py` 的 `DomainPort` / `AuthorityPort`、预算和 UNKNOWN 门禁可供后续领域复用。RPF-28 接入需要新的领域合同校验、受控运维 `invoke/tool_definitions`、实际状态/receipt `read/validate/reconcile` 以及领域 Verifier；本轮没有接入旧 Runner/Worker，没有实现第二域。当前 reset/业务 oracle 保留在订单模块，不建设通用插件注册系统。

## 结果、故障和清理

`run_outcome` 沿用既有 RuntimeFailure：Agent→FAIL、Provider/Environment→ERROR、Harness→INVALID。`effect.contract_outcome` 独立输出 `CONTRACT_SATISFIED_IN_RUN / VIOLATION_CONFIRMED / INCONCLUSIVE`，附规则、证据缺口与真实状态 diff；PASS 执行本身不代表业务满足。

确定性测试通过同一个持久沙箱/dispatcher 注入 post-commit response-lost：pending 时禁止任何后续工具，先查实际收据；不可读就停止为 INCONCLUSIVE/ERROR。`planned/triggered/observed/reconciled` 独立，`planned-not-triggered` 不冒充故障触发。故意错误业务状态是明确的 **TEST-ONLY NEGATIVE CONTROL**，不是模型自主发现。CLI 只暴露无故障演示/live；故障由确定性测试验证，测试不计 Plan 的最多三次有状态故障试验。

正常清理先验证 owner/identity/generation、reset、读回零收据，然后仅删除该 run 的确切 SQLite 文件并移除空目录。`OrderSandbox.reset()` 可供 API 检查；reset 后旧合同不能再退款。UNKNOWN 无法 reconcile 或清理失败时，仅将本 run 移至 `.local/quarantine/rpf-41/<run-id>/`；无法移动则原位保留并报告，不提供强制删除参数。进程硬崩溃后不会自动重跑：账本保留预算/合同，持久沙箱需要先按原身份调查与 reconcile，再由后续授权清理。

本轮事实、验收和边界见 [RESULT.md](RESULT.md)。不授予 release/deploy 权限，不改变旧 Runtime profiles、Reviewed Artifact 或 Project State。
