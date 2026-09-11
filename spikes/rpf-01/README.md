# RPF-01 — DeepSeek Agent Contract Spike

结论：真实 `deepseek-flash` 的 non-thinking 正常路径、响应丢失后的 reconcile，以及 thinking 正常多轮 Tool Calls 已通过最小实验。可以让下一阶段依赖以下受限 Provider 合同；不构成正式 Agent/runtime/environment 架构，也不证明长期稳定性。

## 复现与证据

使用 Node.js 24（本次 24.16.0）、内置 fetch/test，无安装依赖。这是利用现有本机工具链的 disposable probe，不改变 D-008 推荐 Java/Python 的决定。

在仓库根目录运行：

```powershell
node --test spikes/rpf-01/probe.test.mjs
node spikes/rpf-01/verify-evidence.mjs
# 仅下列命令调用真实 API 并产生费用；从进程环境读取 DEEPSEEK_API_KEY。
node spikes/rpf-01/probe.mjs --live
```

14 项本地合同测试不访问网络。证据校验器只离线核对源码身份、重放记录的 Tool intent/state/result 和计算，不等于重新验证模型。源码 hash 接受原始字节或 Windows checkout 的 LF 等价内容。

live 每次输出独立文件到忽略的 `.local/rpf-01/`；不自动覆盖或提交历史样本。[reviewed-evidence.json](reviewed-evidence.json) 是本次人工审查后选定的脱敏固定样本，包含 15 次请求元数据及 3 条状态路径；不是默认采集的普通运行产物。后续改变 probe 后不得用新代码冒认旧证据。

## 已观察与验证的结果

最终样本时间：2026-09-11 11:17:23.975–11:17:35.752 UTC。请求/返回 model 均为 `deepseek-flash`；返回 fingerprint 为 `aeb56401ca74e127821c4f9126dcb669`。文档将其对应到 DeepSeek-V4.1-Flash，但响应没有独立不可变 version identity，不能把文档标签当响应事实或永恒模型版本。

| 实验 | 真实请求数 | 观察到的路径/结果 | Usage total tokens |
| --- | ---: | --- | ---: |
| non-thinking 正常 | 4 | read → apply → read-back → stop；revision 0→1，mutation_count=1 | 2,984 |
| non-thinking response lost | 5 | read → apply 成功但仅返回 UNKNOWN_OUTCOME → reconcile → read-back → stop；没有重复写入意图 | 3,957 |
| thinking 正常，effort=low | 4 | read → apply → read-back → stop；后续请求分别回传 1/2/3 条 continuation | 3,113 |
| 安全参数错误 | 1 | max_tokens=0，真实 HTTP 400；分类 Provider ERROR，未执行 Tool | 未提供 |
| JSON Output | 1 | 200/stop；解析并验证固定对象成功，仅为格式实验 | 69 |

正常/故障成功由程序检查目标状态、唯一 mutation、read-back、无未解决 outcome、无 blind retry 决定，不依赖模型最终回答。记录的 Tool intent 可以离线重建所有本地状态转移。

最终样本的 14 个 HTTP 200 共 9,366 input + 757 completion = 10,123 tokens；LLM 成功请求耗时范围 523–1,314 ms。这只是该次调用时延，不是性能基准。

按当天人民币价格页和请求时间推导为空闲时段：缓存输入 0.02 元/百万、非缓存输入 1 元/百万、输出 4 元/百万。已报告 usage 的最终样本估计费用 **0.00574568 CNY**，标记 Derived Value，pricing identity=`deepseek-flash-CNY-2026-09-11`；不是账单事实。真实 400 未提供 usage，成本为 unknown，不记作 0。若缓存拆分缺失/不一致或跨时段，返回 unknown/范围；reasoning token 是 completion 的细分，不重复收费计算。

开发中曾先完成一轮 15 请求/10,028 tokens 的验证；为补齐 Agent 实际收到的 Tool result 证据，再对最终代码复验。两轮已报告 usage 合计 20,151 tokens，派生成本约 0.01209444 CNY；早期临时样本留在忽略目录，不作为最终源码身份的证据。

## 可进入 Prototype 的最小合同（本 Spike 建议）

1. 使用 GA `POST https://api.deepseek.com/chat/completions`、non-streaming、显式 thinking 开关、单一 choice。第一条 Prototype 路径建议 non-thinking；请求模型可配置于后续 adapter，不作为平台身份。本 probe 固定用户授权的 Flash，防止意外模型切换。
2. 请求包含标准 messages、tool schema、model/mode、输出/步数/时间预算；credential 仅在 HTTP header 由环境注入。此次未使用 Beta strict、Responses/Anthropic surface 或 streaming。
3. 响应先验证 envelope、finish_reason、Tool ID/name/arguments，再进入执行。仅完整 stop/tool_calls 可推进；length/content_filter/insufficient_system_resource/aborted 等均不可作为已完成行为执行。不完整 JSON、未知 Tool、schema/类型/额外字段不通过时，边界拒绝且不改变状态。
4. schema 合法后还须做业务校验：观察前置条件、允许目标、expected revision、operation identity、是否已有未解决副作用。前一调用可安全发给模型重试，不意味着某个已执行 Tool 可以重试。
5. Tool 返回 UNKNOWN_OUTCOME 后，loop 保留不确定状态；只在 receipt/read-state reconciliation 后决定下一动作。Agent 若仍请求盲目重复写入，runtime guard 拒绝，行为记 Agent FAIL；不能因为 guard 保住状态而把危险行为算 PASS。
6. 输出事实包含 requested/returned model、可用 fingerprint、response ID、provider-created、client start/end/latency、finish/status/error、数值 usage、经过验证的 Tool intent 及受控状态证据。usage 或版本缺失必须明确，不补造。价格表及计价时间独立标记，不能把 derived cost 冒充 Provider 原始账单。

### Thinking 与私有 continuation

官方要求携带 tools 时持续回传历史 reasoning_content，甚至历史 assistant 消息没有实际 Tool Call；无 tools 的场景适用不同拼接规则。本 probe 只将该字段保留在内存中的传输消息，最终 assistant 的字段也保留到本次 loop 结束；Evidence 仅保存存在性与回传条数，不含私有内容。

**已验证范围**：单个 user turn 内的多轮 thinking Tool Calls，effort=low，正常状态变更。**未验证**：跨 user turn continuation、thinking lost-response 路径、重启后的 continuation 恢复、streaming。第一版 Prototype 默认 non-thinking；thinking 暂作为受限实验路径，不承诺 durable 支持。缺字段的拒绝与实际回传由 synthetic tests 验证，未另用真实请求测试“删除 continuation 后是否 400”。

### JSON/参数验证

JSON Output 的 200/stop 与合法 JSON 只证明格式，不证明 schema 或业务成功。空 content、截断 JSON、错误类型/额外字段以 synthetic samples 验证 fail closed；本次没有观察到真实模型生成非法参数，因此不能报告其发生率。Schema validator 仅支持 probe 已声明的 object/string/integer/enum/bounds 子集，不是通用 JSON Schema validator。

### Failure attribution 与 retry

| 来源 | 分类/结果 | 本次证据与处理 |
| --- | --- | --- |
| 400/422 请求格式、参数 | Provider ERROR；若请求由 harness 错误构建，责任在 harness 集成 | 400 真实样本；422 synthetic；修正请求后再运行，不原样自动 retry |
| 401/402 认证、余额 | Provider ERROR / 外部条件 | synthetic；停止对应 live 工作，不试图耗尽余额 |
| 429、500、503 | Provider ERROR | documented + synthetic；可成为有界退避重试候选，本 probe 自动重试为 0 |
| transport/timeout、非 JSON 200、截断/畸形 completion | Provider ERROR | synthetic；未返回可验证完整 Tool intent 时不执行；非 JSON HTTP 503 仍保留其 HTTP 分类 |
| schema 合法但盲目重复写、未读状态/版本冲突、无验证便结束 | Agent FAIL | synthetic guard/完整 loop 测试；安全拦截不掩盖行为失败 |
| 本地 Tool/Environment 读写失败 | Tool/Environment ERROR | 仅分类测试；本轮 live 未发生环境故障；不是正式隔离/恢复验证 |
| 无效实验、超出实验预算或未知 harness 异常 | Harness INVALID | synthetic；不计入 Agent Quality |

代码不自动重放 Provider 请求，不自动重启整个 Run。未来有界 Provider retry 必须明确尚无 Tool 被执行、成本/次数/deadline、退避与 response identity；已经发生的副作用仍走独立 reconcile 合同。

## 安全、证据与实验边界

- 本地内存状态和 receipt 是受控 deterministic oracle；Fault 在本地 Tool 边界抑制成功返回。模型只收到 UNKNOWN_OUTCOME，实际 after-state 由 harness 另行记录，直到 reconcile/read-back 才提供给模型。
- 正确路径依赖明确任务指示、schema/业务 guard 和本地真实回读；结果不是“模型自然保证安全”的证明，也不是网络/生产故障恢复证据。
- 原始 request/response、Authorization、自由模型回答、异常原文和 reasoning_content 不写入 evidence。采用字段选择、敏感键移除、实际环境 key 精确检查及 token 模式检查；这不是通用生产 DLP 保证。
- 串行执行；每轮上限 24 请求、单请求 2,048 output tokens/45 秒、每个 loop 6 步、整体 8 分钟；已观察 token 达 30,000 时阻止下一请求，不声称严格账单金额上限。
- Scope 不包含 Production credentials、正式 Environment reset/isolation、Fault framework、持久化 Run、Durable Resume、Provider benchmark 或发布系统。

## 决策影响、剩余未知与下一边界

D-004/D-005/D-006/D-009/D-010 得到有限实验支持；D-001～D-012 无需变更或重编号。non-thinking-first 是下一 Prototype 的证据建议，尚不作为新增永久 Decision。Node probe 不验证 Java/Python 分工优劣。

TU-001 的最小 single-turn/non-streaming Tool-Using 合同已获得真实证据，剩余上文明确的协议/稳定性边界；TU-002/TU-003/TU-004/TU-008 没有整体解决。有限成功样本不能推出长期成功率、模型版本不变或非确定性评估统计结论。

**下一工作优先 TU-002 Environment Execution Model Spike**：用当前 observed-state/receipt/reconcile 合同比较最少可行隔离与 restore/readiness 方案，验证独立起点、污染隔离和状态所有权。Provider 不再是最小路径的主要阻塞；正式 Prototype 仍需可信 Environment 合同。不要优先扩建 Queue 或 Durable framework，也不需先清空所有 Technical Unknowns。

## 官方依据（2026-09-11 核对）

- [首次调用：模型入口与 API surface](https://api-docs.deepseek.com/zh-cn/)
- [模型、版本对应及价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
- [Tool Calls 与 Beta strict 边界](https://api-docs.deepseek.com/zh-cn/guides/tool_calls/)
- [thinking 开关与 continuation](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)
- [JSON Output 注意事项](https://api-docs.deepseek.com/zh-cn/guides/json_mode/)
- [Chat Completions 请求/响应、usage 与 finish](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)
- [官方错误码](https://api-docs.deepseek.com/zh-cn/quick_start/error_codes/)

文档是外部事实来源，reviewed evidence 是本次实验观测，deterministic verification 是程序结论；本节建议属于基于这些证据的推断，三者不混写。
