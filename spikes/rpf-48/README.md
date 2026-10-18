# RPF-48｜外部 Target Agent 的受限执行闭环

本分支已用 **Pydantic AI 2.57.0 + DeepSeek `deepseek-flash`** 完成一条真实订单退款闭环：Agent 自己选择 `inspect_order → refund_order`，SDK 执行工具并将返回值带入下一次模型请求；独立 SQLite Authority 和确定性 Oracle 核验了 `PAID → REFUNDED` 与唯一收据。证据级别为 `EXTERNAL_AGENT_EFFECT_VERIFIED`。

本轮一共预留两条新鲜 Trial：第一条在工具封装校验时被拒绝，未执行业务工具；第二条完成退款。总计 4 次真实 Provider 请求、3,467 tokens，按人民币高峰价估算上界 ¥0.009472，自动重试为 0。两条 Trial 额度已用完，均完成 reset/readback/remove。完整结果见 [RESULT.md](RESULT.md)。

## 先离线检查

从仓库根运行，不需要 SDK、数据库、API key 或旧付费账本：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.target_evidence spikes/rpf-48/target-agent-summary.json --expected-sha256 c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2
```

返回 `CONTENT_VERIFIED_ANCHORED`、`EXTERNAL_AGENT_EFFECT_VERIFIED` 和本次合同结果，exit 0。省略锚返回 `CONTENT_CHECKED_UNANCHORED` / exit 2；错误锚或损坏结构返回 `REJECTED` / exit 3。锚应从用户信任的 Git 提交/独立渠道取得，不能仅信任被检查文件自己的摘要。

[target-agent-summary.json](target-agent-summary.json) 是新的 `rpf-target-evidence-v1` 去敏封装，保存第二条成功 Trial 的冻结合同、SDK/工具身份、调用/返回引用摘要和 Authority 前后状态；跨 Trial 的完整预算与首条失败见 RESULT 和本机账本。它不包含模型消息、自由响应、隐藏推理、凭据或本机绝对路径。离线 verifier 重算内容一致性与业务规则；`issuer_authenticity=NOT_ESTABLISHED`，SDK 来源是控制器的本机观察，没有 PKI 或 OS 级远程证明。它不替换旧 Witness v1/v2。

## 组件与接口

| 组件 | 职责 | 权限边界 |
| --- | --- | --- |
| `TargetContracts` | `rpf-target-execution-v1`、`rpf-target-experiment-v1`；冻结 role、框架/版本、配置、工具、Effect、环境及预算 | 显式静态注册；支持 `pydantic-ai` 与不同标签的 `deterministic-reference`，无动态 import |
| `TargetAgentDriver` | 显式 `run(contracts, host, ledger)` Port；首个实现为 `PydanticAgentDriver` | SDK 子进程没有 Provider key；真实调用来自 SDK 的 `RunContext.tool_call_id` |
| `TargetToolHost` | 绑定 Provider intent、call ID、参数 hash；执行工具、验证结果回注 | 工具仅 inspect/refund/reconcile；先观察、至多一次 mutation；UNKNOWN 只允许 reconcile |
| `ProviderLedger` / `TaskLock` | 单控制器、请求前持久预留、累计请求/token/成本与 Trial 状态 | 每任务 ≤6 HTTP、15k tokens、¥2、2 Trial；每 Trial ≤12 steps/20 分钟；任务窗口 ≤45 分钟；usage unknown 冻结 |
| `AuthorityReader` / 订单 Oracle | 独立只读 SQLite 连接与唯一业务收据；重算 full-refund 合同 | Agent 不能写数据库、改合同/Oracle 或签发业务结果 |

实际 Tool Host 协议是 `rpf-target-loopback-json-v1`，仅绑定 `127.0.0.1` 随机端口，使用父进程通过私有 stdin 传入的短期 token。`/ready` 绑定框架/core hash/配置，`/v1/chat/completions` 只代理固定 DeepSeek 请求，`/tool` 只接受此前 Provider 发出的合法 intent。它没有 shell、任意 URL、MCP discovery、浏览器或生产服务工具。

Python audit guard 限制 SDK 的文件写入和连接；Windows 解释器只读路径别名与事件循环内部 socketpair 在代码中定向处理。这是受审代码上的额外保护，不是任意恶意 Python/管理员环境的 OS 沙箱。Windows venv launcher PID 可与 SDK PID 不同，证据记录两者；绑定依据是私有 stdin capability 与本机 token，而非 OS attestation。

## SDK 选择与实际边界

- 首选 [WorkSwarm 0.2.7 官方发布](https://github.com/openJiuwen-ai/jiuwenswarm/releases/tag/v0.2.7) / [PyPI](https://pypi.org/project/workswarm/0.2.7/)：Apache-2.0，Python `>=3.11,<3.14`；发布 wheel 32,123,505 bytes，SHA `723e8373d2288d60cad09f1aaf813f65bb2b245769c17808e0090b81ae3fb13e`。本轮只下载并静态检查，未安装或启动该应用。
- 其 CLI/service 与默认工具、Home 配置、后台组件耦合。本轮没有证实一条同时具备窄工具列表与逐次计费约束的 WorkSwarm 入口，因此 **WorkSwarm 集成仍为 `NOT_PROVEN`**，不由 import/注册工具推导成功。
- Plan 允许调查一个替代 Runtime。本轮选择 [Pydantic AI 官方 Agent](https://pydantic.dev/docs/ai/core-concepts/agent/) 和 [自定义客户端设置](https://pydantic.dev/docs/ai/models/openai/)：`pydantic-ai-slim==2.57.0`（MIT）、`openai==3.35.1`，已有 Python 3.12.13 隔离环境。OpenAI 客户端只连接本机代理，实际 Provider 是 DeepSeek。
- Pydantic wheel SHA `a07d732e09df8d51f22bd3be2ad45ab644721a904809a2481146bf5d7bb47c67`，其 Agent core 文件与安装文件逐字节一致，SHA `70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa`。启动握手会检查版本/core hash/配置摘要。
- [DeepSeek 官方示例](https://api-docs.deepseek.com/guides/thinking_mode/)含 `index=0` 的 Tool Call 封装。适配器只兼容这一明确扩展，未知字段、非法 index、参数和调用身份仍拒绝。

Explorer 未参与本轮；原 RPF-46 Explorer 不被当成新 Target。当前新增适配器只有订单领域和一个外部框架；运维共享的旧 DomainPort/Oracle 仍通过回归，新增 Target 合同没有声明 ops Live 支持。正常 Live 没有计划故障；UNKNOWN_OUTCOME/reconcile 是本轮负控验证范围，不是第二条 Live 的故障事实。

## 可复现入口

SDK 安装仅可在有授权的任务目录内进行。使用已存在的 Python 3.12 解释器创建 `.local/rpf-48/venv`，将包缓存、TEMP/TMP 和临时 Home 指向 `.local/rpf-48`；固定安装 `pydantic-ai-slim[openai]==2.57.0`、`openai==3.35.1`，不修改系统 Python、项目根依赖或全局配置。

已有该隔离环境时：

```powershell
# 真实 SDK + 模拟 Provider 响应，只检查传输/回注，不进行业务退款
python -B spikes/rpf-48/probe.py --transport-only
```

该入口醒目标为 `FIXTURE_TEST_ONLY`，Provider calls/tokens/fee 为 0；合成 usage 另标 `FIXTURE_SYNTHETIC_NOT_BILLED`，不能算 Live Gate。固定测试只读观察而不退款，其合同目标未完成的 Oracle 输出不能当成发现业务漏洞。

`--live` 是显式付费入口，只有在当前任务重新确认预算与副作用授权后才能使用。它从父进程 `DEEPSEEK_API_KEY` 读取密钥，使用本任务不可重置账本；本机已消耗两条 Trial，再执行会拒绝。程序没有额度重置入口，不接管 RPF-46 账本。费用按 [2026-10-18 核对的 DeepSeek 人民币高峰价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)保守计算：缓存未命中输入 2 元/百万 tokens、输出 8 元/百万 tokens；费用是估算，不是发票。

单测：`python -B -m unittest runtime.tests.test_effectwitness_target_agent -v`。本轮完整 Runtime 测试使用 `.local/rpf-48/regression-src` 中不含 `.git` 的逐字节源码副本，避免旧测试向真实 `.local/rpf-40..47` 写入；实际命令/结果及留存见 [RESULT.md](RESULT.md)。本分支不合并主线、不提供发布权限，也不改变 RPF-47 的未完成演示验收事实。
