# RPF-110/rev-2 封存结果

整体为 `PARTIAL`。B0 本机完成，远端和 hosted CI 待封存后读回。B1 为 `NOT_RUN`。执行基线为 `225dcebe3c51b0fb2c85dafef0842efaff223ad5`。

| Gate | 封存状态 | 实测 |
|---|---|---|
| G0 | PASS | 本地与远端 main 同 SHA，16 个新增目标空闲，2 份 workflow 的基线已核对 |
| B0-A01 | PASS | 冻结 DeepSeek 请求形状、seed、候选、源码和预算，旧 view、源或额度不匹配即拒绝 |
| B0-A02 | PASS | 两进程争抢同 owner 仅一方预约。预约、发送意图、模拟入口前后直接退出均不能重开 |
| B0-A03 | PASS | 实际 loopback 单 POST，跳转与截断不重试；DNS、TLS、超时为注入负控 |
| B0-A04 | PASS | Order、Ops、STOP 与固定 B0 共 7 笔 SQLite 事务。只读对账后未新增预约、发送或写入 |
| B0-A05 | PASS | 4 份 Witness 与 1 份比较包由独立进程复核，篡改拒绝，缺资料为 UNAVAILABLE |
| B0-A06 | PASS（本机） | 13 项新增、12 项历史回归、编译、严格 JSON 和公共文档。Hosted 为 NOT_RUN_AT_SEAL |
| B0-A07 | NOT_RUN_AT_SEAL | 普通 Push、远端和 CI 由最终回执补充 |
| B1 | NOT_RUN | 未授权，未 Dispatch，真实 Provider、SDK、usage 和费用均未运行 |

四组封存 case 各用新 owner，共 3 个 loopback POST 和 7 笔业务事务。STOP 和固定 B0 分别只有 seed 与 seed 加一笔退款。模拟发送入口与原生 SEND_ENTRY 使用不同事件类型。终态的拒绝记录来自本机主动准入探针。第一轮 Windows 测试发现 Connection: close 的响应读取不能在 getresponse 提前移交套接字后继续更新时间限制。修复后完整回归通过，失败 owner 保留。

外部 Provider 请求为 0，密钥未探测。原生接线固定 DeepSeek 非流式 `deepseek-flash`，使用命名 `select_experiment` 并关闭 thinking。原生证书和服务端 ID 尚无本轮实测。预算上限是经审批的估算，账单由 Provider 结算；实际请求、模型 token、费用和版本需 B1 现场确认。[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)

历史 RPF-74 缺口与 Canonical 发布规则保持有效。Architect 独立接受证据后，B1 仍需用户明确批准唯一 Run 和费用合同，维护者配置环境与凭据。本任务未修改远端环境或批准发布。
