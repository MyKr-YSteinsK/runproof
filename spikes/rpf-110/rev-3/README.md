# RPF-110/rev-3 响应字段取证

本轮依据失败 Run 的公开摘要修复诊断。非流式响应仍要求 tool call、function 和 arguments 各自符合固定字段集。新错误码同时区分校验层及多字段、少字段或两者混合。非法 JSON、工具数量和终止原因也使用独立代码。代码由固定字符串生成，可直接进入既有 `status.json.reason`。摘要不附返回字段名、值或原文。

DeepSeek 非流式 schema 的 tool call 包含 `id/type/function`，function 包含 `name/arguments`。流式 delta 的工具 `index` 不进入本轮非流式白名单。业务参数仍仅接受 `candidate_id`。[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)

[封存结果](RESULT.md) · [验收](acceptance.json) · [验证诊断](verification-diagnostic.json) · [源码映射](source-map.json)
