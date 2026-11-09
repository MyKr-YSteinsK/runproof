# RPF-105 rev-1 · 物理证据保全与 Explorer 提案准入

[原始 Actions 外层 ZIP](evidence/rpf104-run-42647430199-actions.zip) 来自 [Run 42647430199 / Artifact 13687917824](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42647430199/artifacts/13687917824)。它包含一个 `public.zip`，不能直接作为 RPF-104 内层校验器的输入。用本提交的源码复验：

```text
python -B -m ci.rpf105_verify_archive
python -B -m unittest -v ci.test_rpf105_verify_archive ci.test_rpf105_explorer_admission
python -B -m runtime.runproof_runtime.effectwitness.pge_r105_replay
```

验证入口在内存里读取两层 ZIP，核对其原始摘要、公开成员和冻结源码身份，再重放 WAL 和 RPF-104 Oracle。公共证据的级别为 `PUBLIC_PROJECTION_CHECKED`，私有 Receiver 原件仍不在归档中。

## 准入接口

`pge_r105_gate.admit(proposal, catalog, feedback, ledger_view)` 是纯函数。提案只提供候选 ID、候选摘要、提案 ID 和当前账本摘要。受信控制器冻结目录和首轮 seed，维护预算、已消费提案、已完成案例、UNKNOWN 闩锁和当次独立验证后的反馈摘要。候选目录只含 `rpf104/NORMAL`、`rpf104/UNKNOWN` 和 `STOP`。

首轮以冻结的 NORMAL seed 准入，无需上一轮反馈。续轮绑定同一 run、owner、源 SHA、账本 revision、上轮 case、operation、环境和合同。反馈摘要必须与受信账本中预先登记的摘要相等。摘要保证对指定内容的绑定；控制器负责在登记前获取真正的 Authority 与 Oracle 结果，不能接受提案方提供的账本或反馈锚。历史公开投影和合成反馈不可充当真实续轮 Authority。

返回 `ACCEPT`、`REJECT`、`MUST_STOP` 或 `INCONCLUSIVE`，附固定原因、输入锚、候选合同锚、预算请求和决策摘要。即使接受，Host 仍须核对同一账本版本并原子消费提案和预算，才进入它自己的写入准入。当前模块没有账本写入或执行接口。UNKNOWN、对账未决或对账已确认提交均不解闩锁。

| 合成场景 | 准入结果 |
| --- | --- |
| 冻结首轮 seed | ACCEPT |
| 续轮缺少反馈 | MUST_STOP |
| 同一续轮提案获得已锚定的合成反馈 | ACCEPT |
| UNKNOWN 闩锁且对账确认已提交 | MUST_STOP |

合成策略与固定顺序都经过同一个 gate，使用同等预算。可重放记录包含提案、候选过滤、反馈质量与摘要，实际执行字段均为 `NOT_RUN`。后续真实 Explorer 仍需独立授权、真实运行和验收。
