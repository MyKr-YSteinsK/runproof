# RPF-53 rev-3 TASK_RESULT

- Plan：`RPF-53 rev-3` — 真实 SDK 结果报告修复与 Provider 跨域补验收。
- **Status: Partial**
- 仓库：`runproof`；父提交 `456ffdf27e363a78f6e24579deccf6345f81f2c5`；执行分支 `codex/rpf-53-rev3-sdk-report-live-closeout`。运行前远端同名分支不存在，远端 `main` 为 `bda0cd49e50e3181f604324e94877a24b9885334`。
- RPF-53 rev-1/rev-2 的既有结论仍为 `PARTIAL`，旧运行目录、marker 与证书未改。

## 结果与 Gate

| Gate | 状态 | 实际结果 |
|---|---|---|
| A-01 身份与隔离 | PASS | 在用户指定的 RunProof 仓库和新分支上执行；父提交、`main`、origin URL 与 Plan 相符。仅触及白名单源码/测试和本 rev-3 四份结果文件。`docs/reviews/` 只在 Git 状态中保留为既有 `??`，其内容未读取、枚举或更改。旧 rev-1/rev-2 本机 marker 未访问。|
| A-02 SDK usage、协议与边界 | PASS | 固定 Pydantic AI 2.57.0 / OpenAI 3.35.1。现场 SDK 源码确认 `result.usage` 是 `RunUsage` 属性，真实字段为 `requests/tool_calls/input_tokens/output_tokens`；新增严格类型/字段验证和反例测试。三次 child 报告均为 `COMPLETED`，usage 为 4 requests / 3 tool calls / 3 callbacks，guard denial 为 0。|
| A-03 完整真实 SDK Fixture Loop | FAIL | 新鲜 attempt 共 3 次，均观察到 4 completions、3 SDK-origin calls、3 个唯一 Tool Return，回注位置为 2/3/4；无 Host error、无 guard denial，所有 child/Host/loopback port 均清理成功。attempt-01 曾把累计历史中的 6 个 tool-message 观察误算为 6 次 return；attempt-02 修正计数但未持久化逐项 check；attempt-03 仅 `sdk_report_complete` 为 false，其余持久化验收项均为 true。完整报告门包含 SDK child PID 绑定；Popen PID 未写入 marker/result，无法离线核对。三次预算耗尽，按 Plan 停止。|
| A-04 真实 Provider Target Agent | NOT_RUN | A-03 未通过，不进入付费阶段；Provider HTTPS=0，自动重试=0，费用=0。环境只检查了 API key presence 布尔值，child 环境没有 Provider key；未读取、传递或打印密钥。|
| A-05 真实 Java/H2 HTTP Effect | NOT_RUN | Java/config-center 未启动；业务 HTTP=0；无 POST、无业务副作用。|
| A-06 新 Live Evidence 与离线锚 | NOT_RUN | 未生成 `config-live-evidence.json`，不以 Fixture 冒充 Live Witness；未运行本轮 Live Evidence 的 correct/missing/wrong anchor 与篡改负控。|
| A-07 回归、预算与历史证据 | PASS | 定向套件 27 tests PASS；三次隔离全 Runtime 快照各为 281 tests、exit 0、0 failures/errors、2 Docker-related tests SKIPPED。七个历史 anchored verifier、Reviewed Artifacts、Public Docs、`git diff --check` 均通过。|
| A-08 TASK_RESULT 与 Git | PASS | 本文件为唯一 rev-3 主 TASK_RESULT；本轮白名单产物以 focused commit 普通 push 到该新分支，并通过 fresh remote ref 核验。无 PR、merge、release 或 deploy；精确最终 SHA 在任务回执中给出。|

**整体判定：Partial。** A-03 未通过，故不满足整体 Complete；A-04～A-06 按停止条件保持 `NOT_RUN`。未把 4/3/3 Fixture 观察升级为真实模型行为、业务效果或 Live Evidence。

## 实现变更

- `config_live_external.py`：读取 `result.usage` 属性，不再调用它；仅接受固定 `RunUsage` 类型和四个经 SDK 源码验证的非负整数计量字段。SDK `tool_calls` 与 SDK callback 数不一致时 fail closed。成功报告显式记录 usage 类型和字段集合。
- `config_live_contracts.py` / `config_live_verify.py`：合同和证据 schema 前进到 rev-3，离线 payload verifier 强制核对 `RunUsage` 类型与字段集合。
- `spikes/rpf-53/probe.py`：使用独立 `fixture/attempt-01..03/` 及不可覆盖 preflight/marker；每次失败必须有安全 cleanup 和变化后的 runtime source hash 才能进入下一 attempt。记录 4 次 completion、SDK call IDs、累计消息 Return IDs、唯一 Return IDs、逐项回注位置和 acceptance checks。
- `test_effectwitness_config_live.py`：27 项专项测试通过，覆盖 usage 类型/字段、错误类型、布尔计量拒绝、报告结构、4/3/3 和累计历史回注顺序。

最终 runtime source identity SHA-256：`ac652d88f945db591b942ebc7e650b49ab65b47b3b84a6ed22ea60a24aee1fec`。Fixture 的完整来源、Run ID、计数、报告摘要、cleanup 与失败 check 见 [`sdk-fixture-diagnostic.json`](sdk-fixture-diagnostic.json)。本轮未生成 `config-live-evidence.json`。

## 验证记录

- 专项命令：`python -B -m unittest runtime.tests.test_effectwitness_config_live -v` — 27 tests，exit 0。
- 全 Runtime：`python -B -m unittest discover -s runtime/tests -t . -p 'test_*.py' -v`，Python 3.14.6。三个独立 tracked-base + 白名单快照均为 655 files / 7,046,951 bytes、281 tests、exit 0、`OK (skipped=2)`；依次绑定 source identity `37f2511909997ef85dd460ec6996164b9635bd6cc6681aca44a95aecd6f38597`、`a5438160096c9c20f8805d246080198358a0b45b2f4035a0553d727406a20c84`、`ac652d88f945db591b942ebc7e650b49ab65b47b3b84a6ed22ea60a24aee1fec`。最终日志 SHA-256：`stderr=0d25418a24dc455c1450c973f0c6951c27c4cd8342316798cffac9c8b0b50147`；stdout 为空。每次快照的文件 SHA、命令与日志均保存在 `.local/rpf-53-rev3/tests/full-runtime-run-01..03/`。
- 历史锚验证均使用从既有 RESULT 固定的外部 SHA、exit 0：RPF-43、44、48、49、50、RPF-51 rev-4、RPF-52 rev-3。最终核验明细在 `.local/rpf-53-rev3/tests/historical-anchors-final.json`。
- `python -B runtime/verify-reviewed-artifacts.py` — PASS；`python -B ci/verify-public-docs.py` — `PUBLIC_DOCS_PASS files=18 pairs=7`；`git diff --check` — exit 0。

## Provider 预检、边界与未执行项

截至 2026-10-19，DeepSeek 官方文档将 `deepseek-flash` 列为 DeepSeek-V4.1-Flash，支持 Tool Calls；官方峰值 cache-miss 输入价 `$0.30 / 1M` tokens、输出价 `$1.20 / 1M` tokens，与 Plan 的 frozen USD 上界一致。任务按 15 CNY/USD 的保守换算得输入/输出上界 ¥4.5/¥18 每百万 tokens；该倍率不是汇率报价，未扩大 ¥1 / 12,000-token 预算。来源：[DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/)、[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)。本轮 Provider 请求数为 0，故价格信息仅是预检而非扣费事实。

Provider API key presence 检查为 true，但没有读取或使用密钥。无付费 Trial、无 Java 进程、无业务 HTTP、无 Evidence。本结论仅说明本地真实 SDK Fixture 与其验收探针状态，不声称生产安全、Live 业务违规、Provider 行为或独立发行者认证。

工作树唯一既存用户路径 `docs/reviews/` 始终未触碰；所有新运行产物仅在忽略目录 `.local/rpf-53-rev3/`，共 1,574 files / 21,375,648 bytes，保留审计复核。所有 Fixture child/Host 已退出、端口已关闭。本轮无 PR、无主线合并、无 release/deploy。Git commit 与远端分支 SHA 由最终任务回执提供。
