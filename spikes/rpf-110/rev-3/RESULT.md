# RPF-110/rev-3 封存结果

本机零 Provider 修复与验证完成。封存状态为 `PARTIAL`，Git 交付和 hosted CI 待独立读回。基线 `7953e9aafc1aa48b073e4d96b049120fc49223b5`。

## 历史失败

Run `42789183082` attempt 1 的预算预检通过，唯一出站执行步骤退出 3。Artifact `13751197164` 共 976 字节，SHA-256 为 `11adaf92fb11374a78a2f3a5382f0f857aaecca13315efc3002c49c18245d779`，已按原字节校验。仅有 `status.json` 和 `failure-summary.json`。摘要记录 `SEND_ENTRY → HTTP_RESPONSE → UNCERTAIN` 和原因 `FIELDS`，未生成比较包。[失败作业](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42789183082/job/129737943130) · [失败 Artifact](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42789183082/artifacts/13751197164)

旧源码中，响应在记录 `HTTP_RESPONSE` 后进入 parser，可能在 tool call、function 或 arguments 的精确字段检查拒绝。公开摘要不含原始响应或 WAL，无法判定具体层、缺少或多出的字段。历史请求总数、usage 和费用保留 `UNKNOWN`。

## 验收

| Gate | 封存状态 | 实测 |
|---|---|---|
| G0 | PASS | main 与远端固定 SHA 对齐，2 个目标源码干净，5 个新增目标空闲 |
| A01 | PASS | 层级与字段差异有固定拒绝码。所有原字段集合和权限保留 |
| A02 | PASS | 九种层级与差异组合、动态 ID、用量、JSON、终止原因、HTTP 错误和工具数量覆盖。额外业务字段只获 loopback 回执，未新增业务账本事件。重锚后仍拒绝 |
| A03 | PASS（本机） | CPython 3.14.7 的 30 项聚焦与历史回归、编译、严格 JSON 和公共文档通过 |
| A03 hosted / Git | NOT_RUN_AT_SEAL | 由 Ubuntu Python 3.12、远端 HEAD 和 blob 回执补充 |
| Live retest | NOT_RUN | 本轮新增 Provider 请求为 0，旧运行未重跑 |

既有状态摘要只接受符合安全正则的 `Denied` 固定码，无需修改 Session 或工作流。非流式文档未为 tool call 额外字段提供依据，流式 `index` 继续拒绝。下一次付费运行仍需 Architect 独立审查、用户批准新 SHA、Run 和预算。[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
