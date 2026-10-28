# RPF-77 — Offline Utility Policy Evaluation

本切片只支持 `OFFLINE_UTILITY_POLICY_EVALUATION_ONLY`。没有 Provider、SDK、Java、SQLite、HTTP/socket 或业务执行能力；不依赖 Daybreak。RPF-74 保持暂停，旧 RPF-75/76 源码、输入与证据均未修改。

ABI 为 `rpf77-offline-utility-v1`。候选 snapshot 在时刻0公开有限候选及预测特征：verification_need、freshness_need、value_update_kind、feature_status、成本、风险、权限及事实前提。完整 roster 来源于先冻结的输入 catalogue；来源 SHA 只提供合成闭世界完整性，不是第三方 attestation。

PGE-v3 的评分是 `2*novelty + 4*verification + 3*freshness + 3*value - cost - 2*risk`。value 对 UPDATE/REVALIDATE/NONE 分别为2/1/0；已尝试候选的验证、新鲜度和值更新项归零。UNKNOWN 特征不猜分，全部合法候选特征都未知时 INCONCLUSIVE；最高分不大于0时 STOP。硬准入在评分前执行，正分不能解锁权限、预算、风险或同域 UNKNOWN。

`KNOWN` 表示预测字段来源和数值在决策前已公开，不保证预测正确。kind9/10 的反例分别展示过高和缺失估计。Policy API 不接收 future outcomes、worthwhile IDs、规范标签或 Oracle 决定。

PGE-v2 对照保留 RPF-76 的数学语义：`10*key_gain + 2*priority - cost - risk`，所有 gain=0 时停止。B0 按 order 固定选择。三策略使用完全相同的新候选、合法性、预算、外生反馈时序和 outcome lookup；没有导入旧 Runtime 或运行旧 Driver。

独立规范 Oracle 只接收冻结 case、当前 records 和决策前状态，计算 MUST_STOP / SHOULD_SELECT / INCONCLUSIVE_ALLOWED / NOT_DETERMINABLE。Verifier 不导入 policy/replay/utility/baseline/oracle，单独重算效用分解、准入、转移、规范评价和指标。共享 schema/常量仍可能产生概念共模误差。

数据是30个 development、18个 challenge 新手工合成案例（seed7701/7702）；challenge 标记 `CHALLENGE_AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND`，没有随机总体抽样或外部盲测。另将3个已曝光 RPF-76 公开输入投影到 diagnostic76，缺失效用字段保持 UNKNOWN；这9次诊断策略运行单列，不计入新 challenge。

冻结工作树中可运行：

```powershell
python -X utf8 -B -m unittest discover -s runtime/tests -p test_effectwitness_pge_r77.py -v
python -X utf8 -B spikes/rpf-77/probe.py verify --file spikes/rpf-77/decision-traces.json --sha d96874f815f7486ba392fac0868373211b0a13f38f06fdef2a6c4244e30db8a1
```

正确锚 exit0，缺锚/文件 exit2，错锚或语义异常 exit3。路径只限本任务私有 JSON 和公开 trace，不接受任意用户路径或链接目录。`run --file .local/rpf-77/<new>.json [--reverse]` 要求 freeze 一致并排他创建；不要覆盖已有根或 Source Freeze。

`negative` 只准备变体和 controls.json，状态 PREPARED_NOT_EXECUTED；必须逐项实际运行 verify CLI 后才记执行结果。本轮78个独立 CLI 负控（12组合）均被拒绝，原始/变体SHA、PID、exit、reason与日志SHA见 negative-controls.json。两次候选/反馈反向迭代的 replay 原字节SHA相同。

Source identity 绑定 exact raw checkout layout；另存 LF SHA/Git blob，未证明任意 CRLF/跨平台 clean checkout 可直接复验。实际 outcome 事实对数、预测键新颖性、规范效用、实际因果效果严格分开；真实 Agent/Target/Authority、第三方 Issuer、L2/L3和普遍策略优势均未建立。完整结果见 RESULT.md 和 evaluation-report.json。
