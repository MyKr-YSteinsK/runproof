# RPF-46｜实时订单 PGE 与 Web 反馈闭环

订单 Explorer 使用真实 DeepSeek Tool Calling，在冻结的三项候选中作两次选择；每轮复用共享订单执行器、独立只读 SQLite Authority 和确定性 Oracle。Target 为 `DETERMINISTIC_CONTROLLED_TARGET`，实验来源为 `LIVE_LOCAL_SIMULATION`，Explorer 为 `LIVE_EXPLORER_DEEPSEEK`。运维仍支持免费确定性捕获。

## 启动与额度

已有 Python、Node、node_modules 和进程环境中的 `DEEPSEEK_API_KEY` 是前提。不安装依赖、不打印密钥。默认启动不启用 Provider：

```powershell
powershell -NoProfile -File spikes/rpf-45/local-lab.ps1 -Action Start -Task rpf-46
# http://127.0.0.1:4185/effectwitness/explorations 显示 DISABLED
powershell -NoProfile -File spikes/rpf-45/local-lab.ps1 -Action Stop -Task rpf-46
```

**付费 opt-in**（只在当前任务有调用及费用授权时使用）：

```powershell
powershell -NoProfile -File spikes/rpf-45/local-lab.ps1 -Action Start -EnablePaidPge
# 浏览器进入 http://127.0.0.1:4185/effectwitness/explorations
powershell -NoProfile -File spikes/rpf-45/local-lab.ps1 -Action Stop -Task rpf-46
```

RPF-46 整个任务最多一个会话、2 次请求（低于 Plan 4 次硬上限）、2 次物理实验、16 共享步骤、12,000 tokens、¥1.50 估计上界、1,200 秒、请求 timeout ≤90 秒、auto retries=0。输入按 UTF-8 bytes+1024 及128输出 tokens 预留，按官方峰值 cache-miss USD 0.30/M 输入、1.20/M 输出、USD/CNY=10 估计费用上界。未知 usage 为 null 并阻断后续操作；估计值不是账单。

**本轮唯一付费会话完成后不能再运行一次演示。** 额度保存在 `.local/rpf-46/explorations/{reservation,ledger}.json`；取消、错误、刷新、换 request_id、重启均不恢复额度。不得删除、移动或替换账本来重跑。启动后仅读回既有会话不会调用 Provider。

## 协议与共享所有权

旧 `POST /effectwitness-api/sessions` exact schema 不变。新接口使用 `rpf-lab-exploration-v1`：

| 路由 | 合同 |
| --- | --- |
| GET `/explorations/capabilities` | AVAILABLE / KEY_MISSING / DISABLED、实际启用、busy、独立余额、预算 |
| POST `/explorations` | exact `{domain:"order",mode:"PGE_LIVE_ORDER",request_id}`；幂等、202；不能提交候选、路径、金额或模型 |
| GET `/explorations/{exploration-id}` | 同一冻结身份、模型选择、经过校验的 trial/feedback、研究结论及用量 |
| GET `/explorations/{id}/witness/{1\|2}` | 只提供符合既有 v2 规则的真实证书 bytes；每次复验 |
| POST `/explorations/{id}/cancel` | exact `{}`；安全边界前停止，不盲目中止已提交的事务 |

所有路径都以 `/effectwitness-api` 开头。Gateway/Vite 保留 server-only bearer、固定 loopback、Host/Origin/Fetch-Site、大小/JSON/路由限制。旧 Store 的 OS 锁和同一个 RLock 管两种模式，跨模式只有1 active/0 queued；旧3次额度和新1次会话额度独立。旧 RPF-45 账本按原服务行为保存，新业务 DB、缓存、日志全部在 RPF-46。

先独占写 reservation marker，再 atomic ledger→flush/fsync，才启动线程。每次请求先记 ATTEMPTED 和未知 usage，再开 socket；每次物理试验先预留7步骤/Run/Operation，再开 SQLite。持久化失败、损坏或遗失已预留账本、未决重启一律 fail closed，不恢复执行。已提交但无法确认终态的 DB 按独立 owner/generation 读回隔离，无法确认则保留原位。没有管理员 reset/reconcile 接口。

冻结计划预先保存两轮各自全部候选的合同、运行身份、source digest、预算、反馈白名单和指标；实际每轮只执行模型选择的一项。两轮始终暴露同一完整候选集，允许重复。首轮不含未来结果/B0；第二轮只提交首轮校验反馈的精确 canonical bytes 与原 tool_call_id。不保存自由响应、prompt 或隐藏推理；只留输入摘要、协议身份及白名单事实。

## 证据与离线检查

Session 的 `rpf-lab-trial-v1` 包装绑定 plan digest、round、candidate、冻结合同、权威快照、实际收据、fault、反馈及事件。此包装不改变旧证书：normal/未触发轮为 `NOT_ISSUED_PROFILE_NOT_ELIGIBLE`；response-lost 经 reconcile、九事件和既有 verifier 完整通过才提供 `rpf-effect-witness-v2`。旧 Witness 的 `DETERMINISTIC_CAPTURE` 描述 Target 捕获；它的 Session 关联由独立包装建立，不修改旧 Witness schema。

把通过合法 GET 获得的 Session JSON 保存在本任务目录后：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.lab_evidence .local/rpf-46/session.json
# CONTENT_CHECKED_LOCAL，exit 0；无网络/DB/Provider；不建立外部锚或 issuer authenticity
python -B -m runtime.runproof_runtime.effectwitness.witness_verify .local/rpf-46/explorations/<id>/trial-2.json
# 仅当该轮实际有证书；无外部锚时 UNANCHORED_INCONCLUSIVE，exit 2
```

L1 要求真实两轮选择及反馈链；L2 另需候选改变且第二轮新增有效 activation 事实。随机 Run/Receipt 身份不计增益，重复选择可合法得到 H1 `NOT_PROVEN_IN_THIS_RUN`。无去反馈反事实，仅 `CORRELATIONAL_ONLY`；不证明一般策略优势。自然语言理由为 `RATIONALE_NOT_RECORDED`。

## 验证和边界

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path (Get-Location) '.local/rpf-46/tmp'
$env:TMP=$env:TEMP; $env:TMPDIR=$env:TEMP
$env:RPF_EW_LAB_TASK_OUTPUT='1'; $env:RPF_EW_LAB_TASK_ID='rpf-46'
python -B -m unittest discover -s runtime/tests -p 'test_*.py' -v
npm test
npm run build
```

免费 mock 测试不会调用 Provider，其临时账本与真实唯一额度隔离；旧测试仅把 fixture 根定向到 RPF-46。实际 Live/browser/Git 与清理事实见唯一 [RESULT.md](RESULT.md)。

官方协议/费率核对：[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/?model_version=DeepSeek-V4-Pro-0813)、[2026-10-17 模型更新](https://api-docs.deepseek.com/zh-cn/news/news261017/)。请求名为 `deepseek-flash`，官方映射 V4.1-Flash-1017；响应身份单独记录，未宣称能从 API 别名独立证明内部权重。

未证明 ops Live PGE、WorkSwarm、正式 Worker、RPF-28 Docker 接入、PKI、真实支付、生产能力或公开部署。本分支交付不代表 main 接受或发布。
