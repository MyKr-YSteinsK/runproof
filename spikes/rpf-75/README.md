# RPF-75：离线 PGE 决策实验室

本切片只支持 `OFFLINE_POLICY_SIMULATION_ONLY`。它没有网络、模型、SDK、Java、数据库或业务执行适配器。RPF-74/rev-4 保持暂停、未验收；本切片不能修复或提升它的证据等级。

候选 ID 和 domain 来自固定 Base 的 RPF-68 公开合同。本轮独立 ABI 为 `rpf75-offline-policy-v1`，不声称兼容旧 Runner API。Execution 投影限制权限、成本、风险、步数；Effect 投影描述有限事实键；Experiment 投影固定候选和重复模式。当前只有两个候选对、四个事实键和模拟整数成本。

策略接收当前 ContractView、当前可见记录及其冻结摘要、PolicyState；后续反馈内容和 outcome oracle 仅由 replay 持有。只有来源、合同、领域、时间和冻结字节均符合条件的 VERIFIED 合成记录影响事实。评分为 `gain*新增可见事实键数 + priority*优先级 - cost*成本 - risk*风险`；相同分数以 candidate ID 排序。UNKNOWN、超时、步数耗尽、矛盾、无可信证据或无法满足安全前提时终止。

B0 按显式 order 固定选择；B1 在评分中不消费后续反馈，但保留相同安全检查。三者使用相同候选、初始预算、7501 种子、外生反馈时间表和 outcome oracle。案例是手工构造，未做随机总体抽样；种子是固定数据集身份，不表示存在随机试验。

在本任务工作树根运行：

```powershell
python -X utf8 -B -m unittest discover -s runtime/tests -p test_effectwitness_pge_r75.py -v
python -X utf8 -B spikes/rpf-75/probe.py verify --file spikes/rpf-75/decision-traces.json --sha 58d905f6325587ee384f4e9f27e428d7f02092b57a4073ce517dd082c668ec67
```

正确原始锚退出 0；未提供锚或文件不存在退出 2；错锚、结构或语义失败退出 3。独立 verifier 不调用策略或 replay 的生成函数。内部 SHA 是完整性链接，不是来源签名；修改内部 SHA 并不能授权修改冻结 oracle。

`probe.py freeze` 仅用于全新、确认拥有的任务根；现有任务根不得覆盖或重新初始化。`run --file .local/rpf-75/<new>.json` 要求既有 freeze 一致并以排他方式创建新输出，`--reverse` 检验容器顺序变化。`negative --file ... --sha ... --directory .local/rpf-75/<new-directory>` 保留所有独立变体。

Source identity 包括明确的 raw/LF 字节布局，见 `source-identity-map.json`。Git 使用 LF blob，而 Windows checkout 可能转换 CRLF；因此相同 Git commit 并不自动保证 raw identity 相同。跨机器复验前需要核对该布局，本轮只验证现有冻结工作树及 Git LF blob 对齐，未证明任意 clean checkout 可直接复验。

结果和分母见 `RESULT.md`、`policy-comparison.json`；完整 48 个 policy replay、130 条决策见 `decision-traces.json`。`negative-controls.json` 保存 44 项重锚控制及额外聚焦输入校验。真实 Explorer、Target、Authority、Provider、历史完整 Runtime 和 L2/L3 因果优势全部未运行或未建立。
