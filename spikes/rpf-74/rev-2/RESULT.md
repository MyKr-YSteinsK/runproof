# RPF-74 rev-3 TASK_RESULT

Status: PARTIAL

Base：`15f82aeb33bd828cf40fe0accba07dc6fb9ecbc1`；工作分支：`codex/rpf-74-rev2-native-slot-tickets-usage-replay`。Plan revision 是 rev-3，沿用的版本化模块 ABI 名仍为 `pge_r74r2`。冻结 Source identity：`aff9b4b1c87c0562ae96fbd70f100b4bcab84357188ea60c1c5429e0b6d813f7`；源码提交 `1863044d8927ca71a443a63f32199f950a29f509`。报告自身的最终提交 SHA 不写入本文；交付状态为 `PENDING_FINAL_RECEIPT`。

| Gate | 状态 | 依据与限制 |
|---|---|---|
| G0 | PASS | 基线、远端、34 路径、隔离与固定依赖核验；旧组件 Context 为依据原调用参数与 WAL 内 Source 哈希重建，摘要匹配原 OWNER 后通过原 WAL replay，原 WAL 未修改。 |
| R3-A01 | PASS | 15 个执行/测试文件、49 个闭包文件 raw/LF 身份已冻结；旧源码未改。 |
| R3-A02 | FAIL | 逐票 native 预约与结算存在，但四个 scripted Explorer 响应缺少独立 response ID，且 UNKNOWN 后仍预约同域新票。 |
| R3-A03 | FAIL | 组件负控通过，但没有覆盖业务 UNKNOWN 后新票；正式 F 反证该守卫不足。 |
| R3-A04 | FAIL | 两组真实本地业务和故障四态均有现场证据，但 F 的新票违反 UNKNOWN 后预约限制。 |
| R3-A05 | PASS | 两组同一 WAL 中 Config 独立验证与反馈冻结先于 Order scripted choice；Explorer 非真实模型。 |
| R3-A06 | FAIL | +1 深层重锚和 8 个用量联动反例被语义拒绝，但 verifier 接受含 UNKNOWN 后新票的 F，且未读取独立持久化的 `launch-receipt.json`。 |
| R3-A07 | PASS | 121 个真实 CLI 负控有效拒绝，其中 47 个票据/用量、8 个联动；零 TEST_INVALID。该集合未覆盖上述实际 UNKNOWN 新票反例。 |
| R3-A08 | PASS | 冻结后聚焦 8 测试通过；第二次未过滤 Runtime exit 0、731 tests、2 个 Docker 类跳过覆盖 5 项，精确对账 736 发现 ID；979 个快照/源文件零漂移，净化环境读回一致。第一次因配额冲突主动停止并保留原日志；第二次为用户明确追加授权。 |
| R3-A09 | UNAVAILABLE | 24 个公开 verifier 及 RPF-69 的 0/2/3 共 27 条均通过；原有运行证据未改。真实 junction 测试通过，Windows 真实 symlink 因权限 1314 不可用；进程轮询有漏检短进程的限制。 |
| R3-A10 | NOT_RUN | 源码提交已普通 Push 并读回；报告提交和最终双读在本文件生成时尚未发生。 |

正式 N/F 各完成一个新 session，并各通过原件 CLI `0/2/3`。独立业务 Reader 在两组均观察到 Config v2 与一次 2500 minor 退款；N 的 9 张 provider 资源票预留 314000，F 的 11 张票预留 474000。F 两域的内部 HTTP 均发生 `RemoteDisconnected` 并回注 UNKNOWN，之后未重复业务写。它们是合成模型资源票，不代表付费请求；实际外部 Provider HTTP、真实模型 token、费用和宿主 Key 读取为 0，固定 SDK 净化环境内 Key 缺席探针另行计数。

**阻断反证：**F 的 Config `UNKNOWN_OUTCOME` 在 WAL seq 199 后，同域仍有 provider `RESERVE` seq 205、233；Order `UNKNOWN_OUTCOME` seq 427 后，同域仍有 provider `RESERVE` seq 433、461。当前逻辑禁止该域重复业务写，但没有禁止新的模型槽预约。新 Order SDK 报告输入用量 +1，在重锚 stdout、manifest 内嵌回执、WAL 和外锚后，新 CLI 以 `SDK_USAGE_SUM_MISMATCH` 返回 3；独立实体 SDK 回执没有参与该重锚或 verifier 校验。

首次完整 Runtime 观察到 181 个测试 ID 后，为防止历史 fixture 突破原共享额度而主动停止，未生成终结 summary。用户随后追加授权一次完整回归，最多 25 个 SDK child 和 4 个 JVM，包含虚构沙箱写入。第二次轮询观察到 13 个固定 SDK Python 进程、4 个 JVM；快照 WAL 可核对 11 个 SDK 和 4 个 JVM，轮询可能漏掉极短进程，不把观察值当完整审计证明。

## VERIFIED_FINDINGS

- `pge_r74r2_budget_gate.py:117` 的 `claim_slot` 不检查业务 `unknown_domains`；`pge_r74r2_domain_ports.py:52` 仅登记受影响域，`pge_r74r2_sdk_harness.py:69` 随后仍申请模型槽。上述 F WAL 帧为直接反证。
- `pge_r74r2_session.py:27` 的 scripted Explorer choice 未生成 response ID；N/F 各两个 Explorer 票均缺该字段。
- `pge_r74r2_slot_contract.py:36` 独立求和 wire usage；`pge_r74r2_verify.py` 绑定 manifest 内嵌回执与 WAL，但未读取 `launch-receipt.json`。
- Windows 真实 junction 测试通过；真实 symlink 创建因 `winerror=1314` 不可用，不能称真实 symlink 验证通过。

## CODEX_ENGINEERING_JUDGMENT

- **HIGH：**synthetic source kind 可使用 native `provider` 类别做本地预算票据，不能解释为外部收费调用。实测 Target 输出均为 20，位于各票 256/512 上限内；wire 请求 512 不证明真实外部模型的 256 预留安全。
- **HIGH：**先修业务 UNKNOWN 后预约守卫和离线验收，再补 Explorer response ID 及实体回执绑定。当前 F 是必须保留的失败证据。
- **MEDIUM：**离线用量求和与在线检查分开，但仍共享固定槽合同和本地 fixture；自签哈希不能证明任意共谋重写、第三方 Issuer 或真实模型行为。

## ALTERNATIVE_PATHS_AND_TRADEOFFS

任务专用 v2 隔离明确但复制较多（15 文件、2164 行、49 文件闭包）；薄公共 Factory/DomainPort 可减少重复，却需要新兼容性与回归证据。修改固定 SDK/Guard 会扩大信任边界和维护成本，也需独立授权。本轮未修改公共默认 Launcher。

## NEXT_DECISION_RECOMMENDATION

先决定 UNKNOWN 后如何在不发放新模型槽的前提下完成只读对账和终止，例如由受限宿主执行确定性对账；若需要额外模型槽，则须明确修订合同并重新评估权限。修复并取得新身份的语义反例通过后，才考虑授权真实 Explorer 与真实 Target。

## POTENTIAL_GENERALIZATION_DEBT

版本复制、业务 DomainPort 与预算策略的共同接口、合成 Provider 类别与真实 Provider 费用边界、固定 SDK Guard、无第三方签名及性能比较均仍需后续验证。`EVIDENCE_ACCEPTED`、`STAGE_ADVANCED`、真实 Provider、L2、main 合并和生产部署均未建立。
