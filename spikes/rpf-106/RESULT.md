# RPF-106/rev-1 封存结果

封存状态为 `PARTIAL`。此时本机 Gate 已验证，Git 交付及 hosted CI 待执行。固定 Base 为 `7be3fe057df5ce2e45af81180c8983c9647fc975`，目标为 `main`。本机运行另以实际执行的 7 份新模块和 6 份直接依赖的 LF 摘要绑定源码；Base SHA 单独标识起点。

| Gate | 封存状态 | 本轮观察 |
|---|---|---|
| G0 | PASS | 本地与远端 main 同 SHA，精确 15 个新路径可用，索引与路径状态无冲突 |
| A01 | PASS | 已验证的 seed 后，两种续轮均可准入，另有 STOP |
| A02 | PASS | 同 revision 竞争中只有一个 continuation 消费预算。写口校验持久意图与一次性许可 |
| A03 | PASS | 两个独立比较 owner 各有 seed 和一个续轮。两库各自读回独立业务事实与唯一收据 |
| A04 | PASS | 两次比较均在 UNKNOWN 后零新增业务事件；只读对账保留闩锁 |
| A05 | PASS | 同轮竞争、错身份、跨运行、重锚/截断、单次许可、缺读回、五种中断及原 owner 写恢复均验证预期拒绝 |
| A06 | PASS | 同候选、同反馈字段和值、同预算，fixture 选 Ops，固定顺序选 Order |
| A07 | PASS | Provider 请求和真实发送均为 0。SDK、Receiver、业务 HTTP、模型 usage 和费用为 NOT_RUN |
| A08 | 本机 PASS，hosted NOT_RUN_AT_SEAL | 7 项新增测试、3 项历史纯准入回归、9 份 Python 编译、严格 JSON 和公共文档验证 |
| A09 | NOT_RUN_AT_SEAL | 普通 Push、远端 HEAD/blob 和 hosted Run 另行读回 |
| A10 | NOT_RUN | 真实 Explorer 与物理端到端 |

## 观察到的事务

两个对照使用相同的 seed 结果结构及 `case_slots/write_slots/send_slots = 1/1/1` 的续轮余额；每个 run 的 feedback pin 与各自身份绑定。

| 策略 | owner | 续轮实际状态 |
|---|---|---|
| Fixture | `3eb1cc86119648c39d7194bc2270b76d` | 配置 `release-v2`、revision 1、effect count 1、1 条收据 |
| 固定顺序 | `7e60846b3add461897931e610bef34f3` | 退款 2500 CNY 最小货币单位、`REFUNDED`、revision 1、1 条收据 |

两组共 4 笔比较事务。封存测试及负控共 12 个新 owner、20 个初始化库、19 笔观察到的业务提交，其中 15 笔已固定 Oracle verdict，另有 4 笔在注入中断后只读确认提交。用于初始化的 SQLite 操作与退款/配置变更事务分别记账。冻结前还执行过一次 6 项聚焦调试，独立占用 11 个新 owner、18 笔业务提交。原始 WAL 和 SQLite 保存在任务 owner 中。

写意图失败后读回 `NOT_COMMITTED`。SQLite COMMIT 后 Host 记账前、UNKNOWN 落盘前、Authority 读回前、Oracle verdict 前四个注入点都读回 `COMMITTED`，未新增反馈 pin。前三种未完成或未落闩锁的阶段仍由原 owner 拒绝写恢复。真正缺失的库返回 `UNAVAILABLE`。另一个本机进程以只读连接重验封存的 12 个 owner，观察数和 WAL 摘要一致。

两次续轮的 fault 四栏均为 planned/triggered/observed=true，agent_exposed=false，指控制器内部的本地结果抑制。中断由确定性故障点注入。没有执行断电、强制杀宿主、实际 SDK/HTTP 丢包或真实 Explorer。逻辑 send_slot 只记预算。对照只支持候选选择与证据差异，不用于估计策略收益。RPF-74 历史反例与 Canonical 门禁规则均继续有效。证据接收、阶段推进和发布仍待各自权限与验收。
