# RPF-101/rev-1

封存时本机 Host Barrier 与回环切片通过，Git 和 hosted CI 为 NOT_RUN_AT_SEAL。基线为 `938d39d977e3271f1e9571c192ac683042d30dd8`。任务 owner 在运行前为空，预注册 8 案例，实际 4 个独立接收进程与 2 个独立恢复进程，峰值同时 2 个子进程。正式矩阵在 CPython 3.14.7 Windows 完成，unittest 2 项通过，14.783 秒。

| 案例 | 持久与传输结果 |
|---|---|
| ready-restart | 正常退出后另一个进程成功消费旧票。1 个 sendall 返回，独立 receiver 收到 42 字节 |
| unknown-restart | UNKNOWN 恢复后全域全角色拒绝，旧票拒绝。0 发送入口，接收 0 字节 |
| send-first | 发送持锁先完成，后到 UNKNOWN。1 个 sendall 返回，独立 receiver 收到 42 字节，归为 PRE_UNKNOWN_IN_FLIGHT |
| unknown-first | UNKNOWN 持锁先完成。0 发送入口，接收 0 字节 |
| unknown-empty | UNKNOWN 前有空余票，四种域与角色组合全部拒绝，WAL 无 RESERVE |
| flush-failure / write-failure | 注入持久化失败后保持安全闩，当前进程与重启均拒绝 |
| torn | 截断 WAL，拒绝恢复与离线验收 |

汇总 2 次应用载荷发送，84 字节被独立接收。UNKNOWN 记录后新增 RESERVE 与 SEND_BEGIN 均为 0。发送与接收分别使用进程、可执行文件摘要、nonce、字节和时序回执。只读对账验证 RECEIVED 与 NO_BYTES_OBSERVED。后者不支持重发。

独立 Oracle 拒绝重新计算哈希链后的 UNKNOWN→RESERVE 与 UNKNOWN→SEND_BEGIN，另拒绝换接收回执、缺字节、换 nonce、伪造 PID/source、重复 JSON 键与错误外锚。CLI 以同批证据摘要进行本地传输校验，该摘要不代表独立签发。

SDK 为 UNAVAILABLE，隔离解释器内没有 OpenAI 或 PydanticAI 安装元数据。SDK 调用、真实 Provider 请求、密钥探测和业务写均为 0。Windows 文件 fsync、进程退出恢复与注入故障已验收，硬件断电与整个本地 owner 被特权参与者回滚仍未验证。旧 RPF-74 与 RPF-100 产品接入分别等待后续验收。
