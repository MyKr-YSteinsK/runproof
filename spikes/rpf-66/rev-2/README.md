# RPF-66/rev-2：严格 Provider 响应与安全形状取证

本修订保留固定 Provider parser 和 SDK 输出 cap256，在新 Host adapter 中先记录受限 shape，再验证响应。实际运行状态见 RESULT、session-summary 和 verification-diagnostic；只有真实两轮完整且新 Verifier 通过才创建 dual-agent-witness。

## 技术选择

| 选项 | 本修订选择 | 边界 |
|---|---|---|
| strict + safe diagnostics | 实施 | 一次 transport，不改 Provider JSON；原 strict validator 再加 ID/arguments/usage 前置核对 |
| evidence-backed benign compatibility | 不启用 | rev1 没有足以定位具体条件的安全 shape，不猜字段兼容需求 |
| bypass / forced stop | 禁止 | length/content_filter/null/非法 choice 均不能伪造 stop；不扩输出、不改固定 SDK |

`Host._provider_request → 原 HTTPS transport → safe_shape → ctx.once(provider-shapes/ticket.json) → PROVIDER_SHAPE_OBSERVED → 原 strict parser / 有限前置校验 → PROVIDER_PARSE_ACCEPTED/REJECTED → RECEIVED 或 UNKNOWN`。transport/超限/非JSON等没取得可用JSON时记录 NOT_OBSERVED，不能补造 message 或 usage。全部 role/resource/receipt 绑定同一 fsynced hash-chain WAL。

`Explorer → 合法选择与 usage → explorer-selections/selection-round.json + CHOICE_FROZEN → Target`。回执保留真实 ToolCall ID、候选、response ID、usage/hash；失败轮只生成 NOT_COMPLETE Session receipt，没有 DomainVerified/FeedbackFrozen。第二轮必须消费真正已验证的第一轮反馈。持久化的 request 证明使用 source-bound 可重建模板的 hash/feedback ID，不持久化自由 Provider 内容。

## 安全 shape Schema

`rpf66-provider-safe-shape-v1`：最多2个 choice、每个最多2个 tool 摘要，shape≤8192 bytes，receipt≤12288 bytes；完整 Provider HTTP body 原 transport 上限262144 bytes。只记录已知字段名字、未知字段数量、容器类型/有界计数、index是否整数0、finish_reason安全枚举、message role、工具名允许集、参数键是否合法、合法ID不可逆hash、usage类型/非负性/有界数字hint。任何未知字符串只输出OTHER，不导出其原文或可逆编码。

不保留 content、reasoning_content、原始 function.arguments、原Provider JSON、Authorization/Key、系统/用户消息。usage 在形状中始终为 UNTRUSTED_OBSERVED_HINT；只有完整接收验证之后 WAL 的 RECEIVED 才提供可信计量。成功证书核对 shape 的独立精确 schema、scope、ID、calls、usage、哈希和先后顺序；checkpoint 的 shape hash 一旦出现不能改写。

旧 `PROVIDER_CHOICE` 条件分别为：choice必须object；仅index/message/finish_reason/logprobs字段；index/message/finish_reason必有；index类型必须int且为0；finish_reason仅stop/tool_calls。新 diagnostics 对这些条件分别给出 CHOICE_TYPE / CHOICE_UNKNOWN_FIELDS / CHOICE_REQUIRED_FIELDS / CHOICE_INDEX_TYPE / CHOICE_INDEX_NONZERO / CHOICE_FINISH_REASON；不能从旧的单一故障代码回填rev1实际条件。

## 单次 staged 入口

```powershell
python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_r66 -v
# 完整Runtime、合成负控、18历史锚、Reviewed/Public通过并冻结source后：
python -X utf8 -B spikes/rpf-66/rev-2/probe.py init
python -X utf8 -B spikes/rpf-66/rev-2/probe.py metadata
python -X utf8 -B spikes/rpf-66/rev-2/probe.py cold
# 独占paid-gate核对Source/Verifier/价格/预算/唯一权限后：
python -X utf8 -B spikes/rpf-66/rev-2/probe.py live
```

唯一根`.local/rpf-66-rev-2/`，旧root、WAL和quota从未读取/复制；旧unknown永久保持未知。本轮预算14个Provider/35000永久预约tokens/¥0.75守卫，metadata/cold各1，真实两轮JVM/SDK各≤2，POST总≤4，retry0。Java/SDK仍由原 ProcessSupervisor 管理。新正式端口35000–39999，经loopback可用性核对；G0本机TCP动态范围1024–15000，与旧bind(0)选端口实现分开，未读取旧私有端口记录。

若有真实完整证书：

```powershell
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_r66_verify spikes/rpf-66/rev-2/dual-agent-witness.json --sha256 <external-raw-sha256>
```

正确/缺失/错误锚exit0/2/3；没有证书时真实CLI和真实负控均NOT_RUN，不创建占位Witness。Source Freeze后不修改source/test/probe，不重复live或清额度。报价按[官方定价](https://api-docs.deepseek.com/quick_start/pricing/)与[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)复核，高峰USD0.30/1.20每百万乘15守卫；非汇率或账单。

## 继续保留的能力边界

配置单域、同服务只读HTTP Authority；模型可重复选择，完整真实两轮时允许L2=false，只有一轮则L2=NOT_RUN。没有第三方Authority、签名Issuer、独立新环境复现、订单真实Target、Web LIVE、L3/统计因果/生产SLA或部署授权。复制/版本化adapter仍在，见 capability-assessment。main/PR/deploy/赛事均不在本次授权内。

## 免费回归的解释器与已观察环境限制

仓库 `.github/workflows/release-gate.yml` 的 canonical Python 为3.12。本修订免费回归分别记录系统Python3.14与锁定Python3.12.13的真实结果，详见 RESULT 和 verification-diagnostic。系统3.14的完整444项回归曾在未修改的 `ConfigTargetDiagnosticBackendTests.test_fixture_http_4xx_preserves_first_enumerated_rejection_code` 遇到 `WinError10053`；同快照该单项在3.14复现、在锁定3.12.13通过。完整Gate使用后者重新独立运行，不能用单项结果代替完整结果。

历史fixture在拒绝鉴权时先发送400并关闭连接，代码路径未读请求body；这与当前TCP关闭问题相关是待证假说，尚未确证根因。未修改历史fixture、Windows安全策略或全局Python配置。保留所有取消/失败记录，不对旧证书与源码补丁。

锁定3.12.13的完整回归最终也未通过：444项中1 failure、21 errors、2 Docker skips。错误包括时间顺序拒绝、ACTUAL_CALLABLE、SESSION_LINEAGE 与缺少 traceparent；新增R66响应负矩阵的一项严格时间比较同样遇到两个相等的 monotonic_ns，不能隐去。故本修订 Source Freeze、metadata、cold、paid admission、live 和真实Witness均未执行。源码目前是待审查候选；完整运行条件须由后续明确授权处理，不能将SDK子进程的3.12 pin直接推为Windows父Runtime环境兼容证明。
