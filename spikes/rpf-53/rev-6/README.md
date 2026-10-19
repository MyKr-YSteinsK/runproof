# RPF-53 rev-6｜Live Witness 修复与有界自主验收

本轮修复了 Verifier 对同级 Experiment 合同的两处错误访问，完成无付费的证书生成、独立锚验证和篡改预演，再以一次新真实 Provider + config-center Trial 生成有效 Live Witness。

实际业务 Oracle 为 `CONTRACT_SATISFIED_IN_RUN`；独立离线 correct/missing/wrong anchor 退出码为 `0/2/3`，四类重新计算摘要的篡改负控全部拒绝。rev-5 缺失的逐请求 Live 可见性记录无法复原，原结果保持 `PARTIAL`；rev-6 记录新的 Run ID、来源、可见性哈希与发行时间。

- [TASK_RESULT](RESULT.md)：唯一中文主结果、验收、根因、旧证据缺口、回归、费用及交付边界。
- [verification-diagnostic.json](verification-diagnostic.json)：离线预演、历史来源矩阵、SDK Fixture、回归与新 Live 验收摘要。
- [live-summary.json](live-summary.json)：新真实运行摘要；健康检查仅公开总状态，组件细节留在 task-local 快照。
- [config-live-evidence.json](config-live-evidence.json)：本轮通过独立离线验证的新证书。

固定的外部锚应由本报告或独立审查渠道取得；不能从待验文件本身临时计算后当作可信来源：

```powershell
python -B spikes/rpf-53/probe.py --verify spikes/rpf-53/rev-6/config-live-evidence.json --sha256 f5e46947ae2a2583db51727e85c4f9e3d6c9d6499a1b24833dfffe1799438b43
```

本轮已完成一个新 Live Trial，选择的编排上限为一个 Trial；没有第二次自动重试入口。禁止复用、删除或重置本轮及旧版 marker/ledger。SDK Fixture 不表示真实模型效果；合成证书仅用于 ignored 本地预演。发行者真实性、数据库独立权威及独立复现仍未建立，PGE/WorkSwarm 未执行或未证明。
