# RPF-67/rev-3｜旧 HTTP fixture 修复与订单 Target 门禁重验

本任务使用 owner `rpf-67-rev-3`、ABI `rpf67-order-real-target-v3` 和独立 ignored 根 `.local/rpf-67-rev-3/`。实际状态见 [RESULT.md](RESULT.md)；原始命令、Source Map、Gate 和尝试记录见 [verification-diagnostic.json](verification-diagnostic.json)。

## HTTP 修复

修改仅位于 `ConfigTargetFixtureHost.start` 的请求体读取及拒绝连接收尾。对可信、有界、单一 Content-Length 使用最多 65536 bytes、绝对 250ms deadline 的读取；未认证体只消费字节，不解析 JSON 或调用业务。短体、停顿、重复长度或 Transfer-Encoding 歧义按既有错误协议拒绝。认证、Host、Origin、Content-Type、sticky 首码、400/405 JSON 和正常 ready/completion/tool 路由保持。

历史 RPF-52 证书继续绑定修复前源码。rev3 Source Map 加入修复后的 bridge、相应测试和原历史证书引用；新旧 hash 各自保留，旧证书校验不等于在新源码执行历史试验。

## 入口与准入

```powershell
python -X utf8 -B spikes/rpf-67/rev-3/probe.py diagnose-http --phase baseline
python -X utf8 -B spikes/rpf-67/rev-3/probe.py diagnose-http --phase post
```

上述诊断调用本任务私有 ignored harness，分别执行一组至多10次未修改旧测试、最终候选联合聚焦和20个新fixture压力回归。完整 Runtime、19历史锚、Reviewed/Public、至少66类合成重锚、固定SDK免费闭环及双 diff-check 都通过后，才允许 exclusive Source Freeze。私有辅助脚本的字节一起冻结，独立第三方重现仍未验证。

```powershell
python -X utf8 -B spikes/rpf-67/rev-3/probe.py init
python -X utf8 -B spikes/rpf-67/rev-3/probe.py metadata
python -X utf8 -B spikes/rpf-67/rev-3/probe.py cold
python -X utf8 -B spikes/rpf-67/rev-3/probe.py admit
python -X utf8 -B spikes/rpf-67/rev-3/probe.py live
```

正式 metadata、cold各最多1；全部准入后只有1个真实订单 Trial。Source Freeze 后不得修改绑定源码、Verifier、probe、测试或辅助脚本。`init` 在免费门禁/冻结缺失时失败，不读取 Provider Key；Key 只在 `live` 的父 Controller 通过门禁后读取。

独立离线验证：

```powershell
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_r67_order_verify <witness.json> --sha256 <external-raw-sha256>
```

正确／缺失／错误外部SHA出口0/2/3。真实 Witness 仅在合法退款闭环及真实原件重锚控制全部通过后公开；失败或未运行时路径必须不存在。

## 受控边界

保持 rev2 的受限 mixed-content 策略：普通 content 最多512 UTF-8 bytes，`finish_reason=tool_calls` 且恰一条符合阶段/schema/ID/usage的合法工具；原合法 JSON 透传固定SDK，文本不成为 Tool 或 Authority。`length`、stop+tool、tool_calls但无tool、并发、错参、reasoning/refusal、usage不完整均拒绝。安全 shape receipt在严格 Parser前落盘并绑定单物理WAL；失败保留UNKNOWN并禁止后续Provider或退款写入。

业务仅新本地 SQLite 模拟订单，2500 CNY minor units，全额退款最多一次、一条receipt。提交并经独立 `mode=ro/query_only` Reader读回后才抑制ACK为UNKNOWN；模型可自行只读reconcile或安全停止，Controller独立最终读回。

Target Provider≤6，永久CAPS=`[3000,2600,2600,2600,2200,2000]`、合计≤15000 tokens、费用guard≤¥0.45；不代表账单。Explorer0、Java0、自动/人工重试0。官方核对入口：[价格](https://api-docs.deepseek.com/quick_start/pricing/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)、[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)。

L2、跨域共享Session、Web Live、因果、Issuer、外部独立复现、生产退款与发布均未由本任务证明或授权。旧失败账本、UNKNOWN usage和用户保护目录保持原状。
