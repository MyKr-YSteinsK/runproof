# RPF-53｜真实 Provider 配置变更与独立 Effect 验证

本 Spike 为 config-center 新增了独立的 REAL_PROVIDER 合同、预算账本、三工具 Host、固定 SDK child 和离线 verifier。当前交付状态是 **PARTIAL**：无付费 SDK 诊断按 Plan 使用了两次 attempt，均在 SDK import 阶段被 child 文件访问审计拒绝；因此没有启动真实 Provider Scenario、Java 服务或业务 HTTP 写入，也没有生成 Live Evidence。

## 产物与当前状态

- `RESULT.md`：本 Plan 唯一主结果，包含 A-01～A-08 状态和完整失败边界。
- `live-summary.json`：脱敏的 Partial 摘要。没有 `config-live-evidence.json`；不得把 Fixture 测试当作真实模型、Effect 或 Live Witness 证据。
- `probe.py`：一次性 preflight、最多两次 fixture-only SDK 诊断、单一受控 Provider Scenario 与 verifier 入口。当前两次诊断额度已用完，且 A-03 未通过，`--run-scenario` 不满足启动前提。
- 新实现位于 `runtime/runproof_runtime/effectwitness/config_live_*.py`；不复用或改写 RPF-52 Fixture schema 与历史证据。

## 隔离与预算设计

真实 Scenario 代码固定 DeepSeek Chat Completions 与 `deepseek-flash`，限制一个 Trial、最多 6 次 Provider HTTPS、12,000 tokens、每次输出最多 256 tokens、估算费用不超过 ¥1、最多 8 次 SDK Tool Call、12 次业务 HTTP（其中最多 2 次 POST）、3 次 health GET、20 分钟、自动重试 0 次。父进程代理 Provider 和业务 HTTP；SDK child 只经 loopback 连接受限 Tool Host，且不接收 Provider/API key。Python audit hook 仅为 defense in depth，不是 OS sandbox。

预检采用 DeepSeek 官方价格页的 Flash 峰时 cache-miss 输入价 USD 0.30/M、输出价 USD 1.20/M，并以预算换算系数 ¥15/USD 形成 ¥4.5/M 输入、¥18/M 输出的保守上界。换算系数不是实时汇率报价。真实请求计费必须以实际 Provider usage 为准。

- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek Chat Completion API](https://api-docs.deepseek.com/api/create-chat-completion/)

## 当前复核

- 定向测试：`python -B -m unittest runtime.tests.test_effectwitness_config_live -v`。
- 全 Runtime：在 `.local/rpf-53/tests/` 下的干净隔离镜像运行 `python -B -m unittest discover -s runtime/tests -t . -p 'test_*.py' -v`；结果与两项 Docker 跳过见 `RESULT.md`。
- 旧证据 verifier、Reviewed Artifacts、Public Docs 和 `git diff --check` 的结果见 `RESULT.md`。
- 只有修复并重新审查文件访问边界、由新的任务计划授权新的诊断/Provider Trial 后，才可开展后续 Live 验证。当前 rev-1 不授权第三次 SDK attempt、真实 Provider 请求、Java 启动、PR、merge、release 或 deploy。
