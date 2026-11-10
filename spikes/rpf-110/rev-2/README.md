# RPF-110/rev-2 一次真实 Explorer 发送接线

B0 实现并验证单次发送边界。Host 用真实 SQLite seed 和独立只读反馈生成固定请求。新 owner 的 WAL 独占创建并依次同步预约、发送意图及发送入口，才允许建立连接。原生路径固定 DeepSeek 主机和路径，使用系统证书验证、不走代理，也不跟随跳转。失败保留不确定态，原运行无写恢复。B0 的测试仅连接 `127.0.0.1`，使用独立的 stub 事件。

手动工作流需要维护者先配置 `rpf-110-live` 的 Required Reviewers，并绑定唯一源码 SHA、首次 Run ID、预算 JSON 及其 canonical SHA-256。预算 schema 为 `rpf110-live-budget-v1`，字段定义见 [冻结合同](../../../runtime/runproof_runtime/effectwitness/pge_r110_live_contracts.py)。将 canonical JSON 放在 `RPF110_APPROVED_BUDGET_JSON`，摘要放在 `RPF110_APPROVED_BUDGET_SHA256`。价格记录必须来自当次批准的官方查询。金额用批准币种的百万分之一单位，费率用每百万 token 的相同金额单位。凭据仅在审批和预检通过后的发送步骤注入。

若 B1 正式成功，工作流发布通过独立进程复核的比较包。验证入口为 `python -B -m runtime.runproof_runtime.effectwitness.pge_r110_live_verify <bundle> <source-sha> <content-sha> --comparison`。比较结果保留 Explorer、固定 B0、领域事实和来源，单例不支持因果优势。真实 Provider 原始响应留在忽略的 owner 中，公开投影的 Provider 来源不能独立认证。

[封存结果](RESULT.md) · [验收](acceptance.json) · [诊断](verification-diagnostic.json) · [源码映射](source-map.json)
