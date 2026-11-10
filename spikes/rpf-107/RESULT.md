# RPF-107/rev-1 封存结果

状态为 `PARTIAL`。已实现 Provider-0 SDK 接线及离线验证。本机已核验的 CPython 3.14.7 没有两个固定 SDK 包。本轮未获 hosted 手动审批，未执行正式 SDK 或 localhost 链路。封存基线为 `611e05d8d3f4cd3d99a6c704c35d2981368b2612`。

| Gate | 封存状态 | 核对结果 |
|---|---|---|
| G0 | PASS | 本地和远端 main 对齐，17 个 create-only 目标无冲突 |
| A01 | PASS | 外层身份与内层 LOCAL scope 分离，候选和反馈投影有精确合同 |
| A02 | NOT_RUN | 真实 SDK 子进程、应用字节、工具回调和包身份均待运行 |
| A03 | PASS（离线） | SQLite 直调保留独立收据。并发回调只消费一次，STOP 不产生续轮写 |
| A04 | PARTIAL | Host 直调在 UNKNOWN 后拒绝模型请求与跨域工具请求，底层 WAL 未变。真实 POST 未发生 |
| A05 | PARTIAL | 执行了身份、Authority、输入、持久化中断与 audit event 负控。真实 SDK 超时、服务关闭和断网未验证 |
| A06 | PARTIAL | 离线验证拒绝重锚、截断、缺成员及伪造 Issuer。新物理证书和公开 ZIP 未生成 |
| A07 | 本机 PASS，hosted NOT_RUN_AT_SEAL | 11 项新增测试、7 项 RPF-106 回归、公共文档和静态校验 |
| A08 | NOT_RUN | 本机无已准入固定 SDK，hosted 无审批 |
| A09 | NOT_RUN_AT_SEAL | 本轮仅做一次源码与离线证据提交，最终 HEAD、CI 在交付时另报 |
| A10 | NOT_RUN | 真实 Provider 与自主 Explorer |

订单对照实测退款 2500 CNY 最小货币单位。运维对照实测配置更新至 `release-v2`。两份库分别读回一条对应收据。工具和模型请求来自测试构造的应用字节，未调用真实 SDK、HTTP 或 Receiver。正式业务事务数、SDK 启动数、监听数及外部 Provider 请求数均为 0。离线用例产生的 SQLite 写入保留在新 owner 中，与正式资源分账。Provider usage 和费用为 `NOT_RUN`。

Canonical 必需覆盖规则保持有效。证据接收、阶段推进和发布需要独立结论。
