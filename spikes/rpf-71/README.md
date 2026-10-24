# RPF-71：BudgetPolicy 执行接缝

本目录记录版本化 BudgetPolicy 在两个具体受控域中的执行验证。新 `BudgetLedger` 代理原 `pge_r68_budget.Ledger`：每笔资源预约/结算先检查当前 Owner/Source 操作与不可变 Policy，再委托 native Ledger 写入唯一物理 `wal.jsonl`。计数、永久票与 UNKNOWN 均来自该 WAL 的回放，没有第二份余额或事实账本。

## 执行关系

`RPF71 Context/OwnerSource → AuthorizedOperation → BudgetPolicy → BudgetLedger → native WAL/replay → native Driver/Port/SDK → Authority Reader → local Verifier`

- `Gate` 和 `Guarded` 是 R70 方法的独立新版本，使用 `.local/rpf-71/`；没有调用旧 session 入口或改写旧 ROOT。
- `BudgetLedger` 使用 `INTENT / audit_type=RPF71_BUDGET` 留 CHECK、GRANTED、CONFIRMED、SETTLED。独立 auditor 验证与 native RESERVE/RESULT 的相邻序列、参数、原状态、票据和授权 scope。
- 新 Context 对 `wal.lock` 的写权限只交给已装配的 BudgetLedger。直接 native reserve/settle、无 Owner 操作和无 Policy 的 Port 装配都有执行前拒绝测试。
- 原 Driver、SDK child/guard、HTTP/SQL 业务算法和 native replay 保持只读。这里的对象约束面向可信 controller 装配，不提供对任意恶意 Python 反射或任意 user callable 的 OS 沙箱。

## 入口与边界

通过 G0 后，在仓库根运行：

```powershell
python -X utf8 -B spikes/rpf-71/probe.py normal
python -X utf8 -B spikes/rpf-71/probe.py fault
python -X utf8 -B spikes/rpf-71/probe.py component
python -X utf8 -B spikes/rpf-71/probe.py verify --path .local/rpf-71/normal-manifest.json --sha256 <原件rawSHA256>
```

原件 CLI 0、缺 SHA 2、错 SHA/语义拒绝 3。正式 N/F 各有独立一次 marker；额外纠错只准 Plan 授权的两个新 run。不得删除、重置、复制或改名旧 marker/WAL/DB 获取额度。`normal-corrective` / `fault-corrective` 各自也只能创建一次新 marker。

`component` 只产生独立目录内的 `SYNTHETIC_BUDGET_COMPONENT_ONLY` 纯数据模型。11 张模拟票及 474000/600000/¥15 等数字是冻结历史预算参考。组件不调用真实 Ledger.reserve、SDK、Key 或模型网络；不构成真实 tokens、费用或 Admission。

N/F 使用固定真实 SDK、scripted 响应及真实本地 Java/H2 与虚构 SQLite 效果。每个场景均须独立 Reader、原样 Tool Return、故障四态、cleanup 和反馈顺序。Provider/Key lookup/真实 usage/API 费用均为 0；不证明真实自主双 Agent、真实 Provider 故障、Issuer、L2、第三域或 Web。

## 结果

- [RESULT.md](RESULT.md)：中文单一 TASK_RESULT、Gate、对象图、验证与工程建议。
- [verification-diagnostic.json](verification-diagnostic.json)：命令、PID、来源、场景、WAL/manifest/Reader SHA 和清理记录。
- [budget-execution-matrix.json](budget-execution-matrix.json)：每笔 Policy 决定、native 预约与结算及回放投影。
- [budget-negative-controls.json](budget-negative-controls.json)：逐件独立重锚 CLI 攻击与有效性分类。
- [source-identity-map.json](source-identity-map.json)、[history-regression.json](history-regression.json)：当前新源/旧源身份与原生历史入口。
- [capability-assessment.json](capability-assessment.json)、[architecture-decision.json](architecture-decision.json)：迁移责任、替代路线、风险和待批准事项。

原始本轮 manifest、WAL、数据库、sidecar、日志和变异文件仅在 ignored `.local/rpf-71/`。RPF70 的私有原 manifest 本轮不可读取，使用 Base 跟踪源/测试/诊断与 raw hash 作可用回归，并明确 `R70_NATIVE_MANIFEST=UNAVAILABLE`。新 verifier 不给历史证书重签。
