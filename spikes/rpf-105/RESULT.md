# RPF-105/rev-1 · 证据封存

基线为 `4f52e9595d55f1ea6a683f7ad7f1f814db452d04`。本地 main、远端、限定路径 index/占用、忽略和父路径检查通过。封存时新提交、Push 与 CI 为 `NOT_RUN_AT_SEAL`。

GitHub [Run 42647430199](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42647430199) 为 attempt 1，Job 129264384616 成功，`rpf-104-physical` 审批和 `verify --require-complete` 均有远端记录。Artifact `13687917824` 的原始外层 ZIP 以同一字节归档。GitHub 的保留截止时间为 2026-11-23 15:44:29 UTC。

| 证据层 | 字节 | SHA-256 |
| --- | ---: | --- |
| Actions 外层 ZIP | 11072 | `c917ce175f1fb56c4ee768ab1aee184e2d710cdba65fa0390d10d79807bd67b3` |
| 内层 public.zip | 11050 | `763d9d5faec3a2fbee5322df80c8e2256d4edeba4ba9b0a1345d6146313e960b` |
| Manifest | 2217 | `8288f4b301ca3feefbe7472be93133b074de7320975c2db7060d3b2fd8356052` |

外层 Git blob 为 `a0f4175634f377b5145ce8606ee8bd53795d16f2`。成员结构和敏感字段扫描通过，范围仅限已公开的两层 ZIP。公开 Oracle 复算了 36 行 NORMAL 和 28 行 UNKNOWN WAL。历史 NORMAL 有 3 次 SDK POST、2 次工具回调、2 次 SQLite 提交、3 次转发与 2854 接收字节。历史 UNKNOWN 有 2 次 SDK POST、1 次订单提交、1 次转发与 582 接收字节。UNKNOWN 标记在 seq 12，后续预约、发送入口和业务写入事件均为 0，且记录只读对账和 DENY。

新增准入 gate 的结果为纯数据决策，接受时仍需要 Host 核对账本版本并原子消费。用同一续轮提案、同一预算的合成数据，将缺失反馈替换为已锚定的同 Run 反馈后，结果从 `MUST_STOP` 变为 `ACCEPT`。UNKNOWN 闩锁即使完成只读对账仍停止。固定顺序策略在同一 gate 上受相同约束，本轮没有比较策略效果。

本机 CPython 3.14.7 的 15 项新增测试、8 项 RPF-103 回归与文档检查通过。新增测试覆盖两层 ZIP 结构、CRC、源身份、换回执、重锚后 UNKNOWN 副作用、过期反馈、越权参数、预算和重复提案。新增离线工作流仅自动执行测试和文档检查。历史文件及原证据不改。

本轮实际物理 Run、SDK/Receiver、真实 Provider、业务写入、工具执行和费用均为 0。历史样本为 `SCRIPTED_LOCAL`，公开复核是 `PUBLIC_PROJECTION_CHECKED`。真实 Explorer、R-01/R-02、Web Live、独立 Issuer 与 Release 均未验收。`EVIDENCE_ACCEPTED` 与 `STAGE_ADVANCED` 由 Architect 裁定。
