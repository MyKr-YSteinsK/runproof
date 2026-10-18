# RPF-49 — 真实 Target Agent 响应丢失与自主对账

RPF-49 复用 RPF-48 的 Pydantic AI Target Agent、受限 Host、SQLite Authority 和订单 Oracle，在单次新鲜受控 `response-lost` Trial 中检查 Agent 是否能从 `UNKNOWN_OUTCOME` 自主调用 `reconcile_order`。它不修改业务 Oracle，不生成失败 Witness，也不触及旧 RPF-48 付费账本。

逻辑合同仍是严格的 `rpf-target-experiment-v1`，其合同 owner 保持 `rpf-48`；新的物理沙箱、Provider 账本、锁和 child process 全部限制在 `.local/rpf-49/**`。离线恢复摘要同时记录这两个身份，避免把路径隔离说成新的合同或独立发行者签名。

## 执行

使用 task-owned Python 3.12.13 venv，固定 `pydantic-ai-slim==2.57.0` 与 `openai==3.35.1`。付费前先运行真实 SDK、零 Provider 的 fixture 工具循环：

```powershell
.local/rpf-49/venv/Scripts/python.exe -B spikes/rpf-49/probe.py --transport-only --fault response-lost
```

唯一付费入口需要显式 `--live`，并固定 `response-lost`。任务账本在发请求前持久化 reservation；最多 1 Trial、6 个物理 HTTPS attempts、12,000 Provider tokens、14 Host/SDK steps、20 分钟、单 HTTP 60 秒、无自动重试。Token 费率按 DeepSeek 官方峰时 Flash 价、输入 cache miss，并用 CNY 10/USD 作为预算上界；Trial 预算封顶 ¥1.00。官方价格表会变化，执行前应复核：[DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。

```powershell
.local/rpf-49/venv/Scripts/python.exe -B spikes/rpf-49/probe.py --live --fault response-lost
```

RPF-48 `rpf-target-evidence-v1` 载荷作为兼容事实块嵌入摘要，其旧 `estimated_cost_cny_upper` 字段保留旧核验器要求的兼容口径；RPF-49 实际预算与费用只以摘要顶层 `task_usage` 为准，并由新核验器按当前官方美元费率和保守换算重算。

## 独立离线核验

核验器只读取规范 JSON、重算订单 Oracle、工具调用 lineage 和费用，不导入 SDK、SQLite、HTTP 或网络。必须从独立已知来源提供摘要 SHA-256：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.target_recovery spikes/rpf-49/recovery-summary.json --expected-sha256 <known-sha256>
```

正确锚且全部恢复事实成立时返回 `AGENT_RECOVERY_VERIFIED`。缺少锚或恢复链不完整返回 `NOT_PROVEN`；错锚、篡改或内部证据矛盾会拒绝。SHA-256 只绑定字节，不建立 issuer authenticity、真实生产真实性、因果归因、跨模型泛化或重现结论。
