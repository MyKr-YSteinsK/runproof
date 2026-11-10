# RPF-108/rev-1 封存结果

封存状态为 `PARTIAL`，待远端交付和 CI。已验证基线为 `be485bdefd359578c4f050fb222d5edb08b16974`。

| Gate | 封存状态 | 本轮实测 |
|---|---|---|
| G0 | PASS | 本地和远端 main 同 SHA，18 个允许目标未占用。实际新增 17 个文件 |
| A01 | PASS | 指定 RPF-107 Run 原始 ZIP 逐字节保存。验证公开投影，Issuer 未建立 |
| A02 | PASS | 仅模拟预发送。并发只预约一次，许可一次消费，故障和 UNKNOWN 后无新预约 |
| A03 | PASS | Order、Ops、STOP、固定顺序 B0 分开使用 fresh owner，候选域及收据可区分 |
| A04 | PASS | 4 份新 fixture bundle 由独立进程从输入字节重算。缺失材料为 UNAVAILABLE |
| A05 | PASS（本机） | 15 项测试、公共文档、编译及严格 JSON。远端与 hosted CI 为 NOT_RUN_AT_SEAL |
| A06 | NOT_RUN | 真实 Explorer、外部 Provider 请求和 usage 未运行 |

RPF-107 Run `42764310121` 的 Artifact `13738564981` 保留 4,492 字节，SHA-256 为 `67de0b59a2336a9ad577fedd74e99b0d4f800a48ba0f7a855e7730beb74be7fb`。内层 ZIP 和公开 JSON 分别为 13,872 和 13,516 字节，摘要见诊断。为了跨平台验证，直接对照固定字节及成员契约，避免 Python 在不同系统上重打包产生不同 ZIP 元数据。历史公开投影没有原始账本或 Authority 输入，保持 `PUBLIC_PROJECTION_VERIFIED`。

4 个独立 SQLite 对照合计 7 笔业务提交。STOP 只有 seed。模型返回、动态工具 ID、发送入口和用时均为模拟数据。故障由确定性中断点注入，未验证断电和外部传输。可移植复算使用实测结构化快照与收据，不需要原库文件，也不证明第三方签发或真实模型决策。真实 Provider 请求为 0，usage 和费用为 `NOT_RUN`。

生成逻辑位于 `pge_r108_replay.py`，验证逻辑位于 `pge_r108_verify.py`，故省略白名单中单独的 `pge_r108_capsule.py`。Canonical 覆盖门禁保持原样，发布及部署未执行。
