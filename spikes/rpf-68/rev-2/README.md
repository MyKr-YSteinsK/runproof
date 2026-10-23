# RPF-68 / rev-2：跨域逐槽预算修复与合法输入验证

状态 **BLOCKED**。配置4/5及可达总额已升级；普通双域四配对、有限终止阶段正控通过，但订单3/早期配置2仍有合法输入反例。真实Provider、正式Freeze/cold/admission与真实Witness未运行。

## 版本及安全边界

- owner `rpf-68-rev-2`，ABI `rpf68-shared-real-cross-domain-v2`；新根 `.local/rpf-68-rev-2/`，不能复用rev1账本。
- 配置 `[3000,2400,2400,4600,4300]`，订单 `[3000,2600,2600,4200]`，Explorer每轮2500；最多34100可达预约/35000全局/11请求，900余量不赋权。
- 单物理fsync/hash-chain WAL、receipt-before-WAL、typed Port与独立Oracle不变；Slot proof绑定version/role/domain/round/ordinal/output/可达额。
- 接受协议保留ID160/mixed512/arguments8192、完整ToolReturn、output512与guard512；未为适配额度压缩或截断。
- 新证书/Verifier schema v2，拒绝升级历史fixture或拼接两份独立证书。

## 显式命令

```powershell
# 会启动受控Java/固定SDK，并写入新的ignored synthetic子根
python -X utf8 -B spikes/rpf-68/rev-2/probe.py free
python -X utf8 -B spikes/rpf-68/rev-2/probe.py max-envelope
python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_r68 -v
# 独立外部raw锚；合法0/无锚2/非法重锚3
python -X utf8 -B spikes/rpf-68/rev-2/probe.py verify --witness <file> --sha256 <sha256>
```

`init/preflight/metadata/cold/admit/live` 不会隐式满足免费门禁；本次P1 FAIL禁止进入。不得改额度、JSON编码/消息长度或旧Source以补发。`max-envelope` 的采样只报告有限SDK案例，不是绝对worst-case证明。

[RESULT.md](RESULT.md) 为唯一TASK_RESULT；[slot-budget-diagnostic.json](slot-budget-diagnostic.json) 记录正控/反例；[architecture-decision.json](architecture-decision.json) 区分工程事实、判断与路线。真实 `cross-domain-witness.json` 必须不存在。
