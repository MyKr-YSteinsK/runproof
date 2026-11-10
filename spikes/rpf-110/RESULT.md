# RPF-110/rev-1 封存结果

整体为 `PARTIAL`。本机 Phase A 已验证，Git/CI 待封存后读回。Phase B 保持 `NOT_RUN`。基线为 `39f19b20db5175f44bf73e971094d5a0807bb5a0`。

| Gate | Phase A 封存状态 | 实测 |
|---|---|---|
| G0 | PASS | 本地和远端 main 同 SHA，19 个 create-only 路径均未占用 |
| A01 | PASS | 冻结两域候选、seed 反馈、工具枚举、运行和源码身份 |
| A02 | PASS | 双线程和双进程只得一个预约。一次性票、进程直接退出与重开拒绝已验证 |
| A03 | PASS | Order、Ops、STOP 分开执行，两域各有真实 SQLite 收据。伪造及已用业务许可拒绝 |
| A04 | PASS | 固定 B0 与 fixture 共用输入合同和续轮机会；B0 无模型预约 |
| A05 | PASS | 4 份 Witness 由独立进程复算。缺失 Authority 标 UNAVAILABLE；重锚、身份与次序篡改拒绝 |
| A06 | PASS | 12 项聚焦与历史回归、编译、严格 JSON、公共文档通过 |
| A07 | NOT_RUN_AT_SEAL | 普通 Push、远端 blob 和 hosted CI 在提交后读回 |

四个正式 fixture owner 共 7 笔 SQLite 业务事务，3 次模拟模型预约。Order 读回退款 2500 CNY 最小单位，Ops 读回配置 `release-v2`，STOP 只执行 seed。固定 B0 读回同合同的 Order 退款。两个子进程争抢同一 owner，其中一个持久预约后直接退出，另一个与后来重开均被拒绝。注入点覆盖预约前后、发送意图后、模拟发送入口后、写意图、SQLite 提交后及闩锁窗口。此处未验证断电、真实外部发送或真实 Provider 回执。

RPF-106 的 Target 路径绑定在旧任务根。新适配沿用其账本、判定、`Target.arm()` 与意图检查，在新 owner 的写事务中再次校验同一张许可。本轮无 SDK 子进程、监听或实际 Provider 请求，usage 和费用为 `NOT_RUN`。官方文档支持 Chat Completions 的命名工具形状、完成 ID 与 usage。独立 HTTP request ID 仍需实际响应取证；请求字节上限仅用于 fixture，Phase B 的 token 与费用上限尚未绑定。[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)

本轮实现的发送入口只消费内存 fixture。历史 HTTPS 路径尚无本轮原生 SEND_ENTRY 与回执证据。手动 workflow 即使通过审批绑定也保持停机，直到 Phase B 的密钥合同和发送审计获批并接线。未触发该 workflow，未改 GitHub Environment。Canonical 覆盖门禁未改动。证据接收、阶段推进、发布与赛事提交各自独立。
