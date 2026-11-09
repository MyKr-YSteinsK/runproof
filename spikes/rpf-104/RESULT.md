# RPF-104/rev-1 · Phase A 封存结果

**PARTIAL**。Base 为 `06d0c3ff6449ad237b24df510ca7f4460cd2781e`，封存前核对本机与远端 main 一致。7 个新模块、2 个测试、2 个工作流和 5 个报告文件均为新增。RPF-103 ZIP、旧业务和 SDK 源码没有改动，归档验证器仍通过。

| Gate | 封存时事实 |
| --- | --- |
| G0 / A01 | PASS，限定路径核对基线、index、路径、ignore、上游和自动工作流副作用。新合同和源码摘要已冻结。 |
| A02 | PASS，合成 NORMAL 需要无故障的真实形状反馈，错域、伪故障、缺反馈或 UNKNOWN 闩锁均停。 |
| A03 | NOT_RUN 正式案例。本地数据控制通过；本机没有已准入的临时测试根，磁盘 SQLite 夹具留给自动 Ubuntu CI。 |
| A04 | NOT_RUN 物理发送。离线持久写故障、并发预约、重锚后 UNKNOWN 新预约/写入/发送和不可用对账负控通过。实际落盘夹具留给 Ubuntu CI。 |
| A05 | NOT_RUN，真实 SDK 和 Receiver 未启动。 |
| A06 | PASS 离线 Oracle 语义与篡改控制，独立物理 Oracle NOT_RUN。 |
| A07 | NOT_RUN 物理公开 capsule，离线 schema、摘要、敏感字段和未完成拒绝控制 PASS。 |
| A08 | Python 编译和 6 段 Bash 语法检查 PASS。本地合计 22 项通过、1 项跳过。提交、远端读回、自动 CI 为 NOT_RUN_AT_SEAL。 |
| A09 | NOT_RUN，`rpf-104-physical` 的只读 GitHub 查询返回 404，用户侧准入待建立。 |

封存时没有正式 Run 或 Artifact。本任务本机执行的物理事务、真实 SDK child、Receiver、listener、外部 Provider 请求和费用均为 0。正式 case 的事务数、SDK 请求数、应用发送数和接收字节实测为 `null`。UNKNOWN 后零新副作用仅在合成控制中由 Oracle 证明，正式 case 待验收。

RPF-100 会自行完成两域且要求订单 UNKNOWN 反馈才能选 Ops。新 NORMAL 策略接受经独立读回的订单成功且四态全 false；UNKNOWN 将对账与闩锁分离。目标事务和 WAL 之间的非原子窗口只能停止并保留证据，尚无真实进程崩溃复现实测。

具体准入步骤、可重验命令与剩余边界见 [README](README.md)。`TASK_COMPLETE` 的全任务条件仍待物理验收，`EVIDENCE_ACCEPTED` 和 `STAGE_ADVANCED` 由 Architect 裁定。
