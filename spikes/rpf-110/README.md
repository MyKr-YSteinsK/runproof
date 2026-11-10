# RPF-110 竞赛 Explorer 交接

Phase A 提供 Provider-0 的本地闭环。可信 Controller 先在 SQLite 写入 seed，再由独立只读 Authority 和 Oracle 固定反馈。Explorer 仅能返回订单退款、配置变更或 STOP。Host 以当前账本重新判定，持久记录写意图，随后使用一次性业务许可。续轮结果丢失后进入 UNKNOWN，只读证据可确认提交，原运行不获得新许可。

Explorer 与 B0 使用相同候选、反馈字段和一次续轮机会，各使用独立 owner。B0 固定选 Order，且不消费模型预约。Fixture 的协议形状采用 DeepSeek Chat Completions 的非流式命名工具，关闭 thinking。模型、请求 ID 与工具 ID 均按来源标注。[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)

## 独立验证与演示交接

在仓库根执行 `python -B -m runtime.runproof_runtime.effectwitness.pge_r110_verify <bundle> <expected-source-sha> <expected-content-sha>`。验证器从包内账本、模拟协议字节和实际 Authority 快照重算事实。结果包含 `rpf110-demo-v1` 投影，分开记录候选、反馈、业务效果、闩锁及 Provider 状态。只有新 fixture 生成了 Witness。后续 Web/PPT 可读取诊断中的四份投影和包摘要。

Phase B 手动入口处于锁定状态。启用前须独立批准实际 Provider、端点、Secret 合同、唯一运行、token 与费用上限和停止条件，并完成原生发送审计。外部调用、真实 usage、独立 Issuer 和发布均保持独立验收。

[封存结果](RESULT.md) · [验收记录](acceptance.json) · [诊断与演示投影](verification-diagnostic.json) · [源码映射](source-map.json)
