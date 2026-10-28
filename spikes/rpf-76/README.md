# RPF-76：离线策略泛化与独立停止评估

证据等级为 `OFFLINE_GENERALIZATION_AND_METRIC_EVALUATION_ONLY`。本模块没有模型、网络、SDK、Java、数据库或业务执行适配器。抽象 domain 不是已接入的新业务域。RPF-74 保持暂停，RPF-75 的历史源码、报告和指标没有改写。

新 ABI `rpf76-offline-generalization-v1` 使用有界 `lab-*` domain、1～6 个候选和每 case 12 个事实键。候选池在 snapshot 时刻 0 全部可见，候选固定来源/合同摘要、成本、风险、权限、事实前提、effects 类别和 repeat 模式；无 URL/path/callable 扩展字段。候选排序和证据输入迭代顺序不影响最终轨迹。

完整 roster 在两份输入 catalog 中预先冻结。Replay 只从该输入取 roster，不从待验证 visible records 现场签发可信 roster。Policy 只接收当前 snapshot、当前可见记录、完整 roster 的摘要映射、anchor 和状态；不接收未来 outcome 或 utility label。该信任仍是 **closed-world synthetic integrity**，不是第三方 attestation。

PGE-v2 的整数评分为 `gain*未知事实键数 + priority*优先级 - cost*成本 - risk*风险`。B0 固定 order，B1 只消融评分中的反馈，三者保留相同安全过滤和可见输入。PGE 的“预计 gain 为零则停止”是待评价启发式，可能错失仍值得评估的候选。

独立 Stop Oracle 只读取冻结 case、当前可见记录和决策前状态。它以预定义 fresh worthwhile IDs 及准入规则给出 SHOULD_SELECT / MUST_STOP / INCONCLUSIVE_ALLOWED，不接收实际 Decision。Verifier 不导入 policy、replay、metrics 或 oracle，独立重算准入、排序、状态转移、Oracle 和指标。共享 schema/规则常量及合成标签仍有共同概念错误风险。

`correct_stop` 只统计 STOP 且 Oracle=MUST_STOP；`total_stop` 统计所有 STOP。Oracle=SHOULD_SELECT 的 STOP/INCONCLUSIVE 是 missed_opportunity；Oracle=INCONCLUSIVE_ALLOWED 的 STOP 标 NOT_DETERMINABLE，不自动算正确。`stop_correctness` 的分母排除这种不确定 STOP；报告同时保留原始 total_stop。INCONCLUSIVE 的合理性另计分子和分母。

24 development 和 12 holdout case 身份不重叠。Holdout 使用开发集未出现的抽象 domain 和 5～6 候选形状。数据由本任务生成，明确 `HOLDOUT_EXPOSED_NOT_BLIND`，没有独立盲测或随机总体抽样。首次正式 holdout 评价在 source/catalog freeze 之后；评价后没有调权重或修改输入。

在冻结的本任务工作树根运行：

```powershell
python -X utf8 -B -m unittest discover -s runtime/tests -p test_effectwitness_pge_r76.py -v
python -X utf8 -B spikes/rpf-76/probe.py verify --file spikes/rpf-76/decision-traces.json --sha 4c05d2ea0b67b6fdef1e104f73c4952607c5bfe8336d6d170871fb9b0ac55e1a
```

CLI：正确 raw anchor 退出 0，缺 anchor/文件退出 2，错误 anchor、结构或语义退出 3。只允许本任务私有 JSON 或公开 decision-traces.json，拒绝任意用户路径和链接目录。`freeze` 仅适用于全新、确认拥有的任务根，不可覆盖既有 freeze。`run --file .local/rpf-76/<new>.json [--reverse]` 以排他方式创建新轨迹。

`negative --file ... --sha ... --directory .local/rpf-76/<new>` 只准备独立变体和 controls.json，返回 `PREPARED_NOT_EXECUTED`；必须逐个运行 `verify` 并记录真实进程 exit/reason，才能称负控已执行。本轮 76 个内置变体及 2 个 task-owned 补充变体均由独立 CLI 进程运行，结果见 metamorphic-controls.json。

Source identity 绑定 exact raw layout，另存 LF SHA/Git blob。CRLF checkout 转换可能改变 raw identity，不能仅凭 commit 相同保证任意 clean checkout 直接复验。真实 Explorer/Target/Authority、第三方 Issuer、L2/L3 因果增益和跨平台复验均未建立。

`RESULT.md` 为主报告；完整逐例表、分母和负结果见 evaluation-report.json，独立停止反例见 stop-oracle-audit.json，原始 108 policy replay / 182 decisions 见 decision-traces.json。
