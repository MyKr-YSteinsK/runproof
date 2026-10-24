# RPF-68 rev-3：联合容量与真实跨域闭环

本目录保存本轮版本化输入预算、固定 SDK 联合容量试验、独立业务读回与一次真实会话结果。入口默认不联网、不付费；先阅读 RESULT.md 与结构化 Gate 状态。

## 可独立复核

```powershell
python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_r68 -v
python -X utf8 -B spikes/rpf-68/rev-3/probe.py max-envelope
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_r68_verify spikes/rpf-68/rev-3/cross-domain-witness.json --sha256 <外部原始文件SHA256>
```

max-envelope 在本轮 ignored task root 创建全新的合成 SDK/Java/H2/SQLite 实例，不调用 Provider。证书只在真实双域完整成功、独立离线核验及至少30类真实重锚负控通过后创建；路径缺失表示本轮没有达到该条件。无外部 SHA 的 CLI exit2、错误 SHA exit3；不能用重新计算的内部哈希替代外部原始锚。

## 合同

600000 全局不可回收 token 池；实际冻结全路径474000；每槽不高于160000；11次 Provider 上限；一次正式会话；费用守卫¥15。SDK 子进程读取并校验冻结分域累计预算 Config250000/Order160000；这是用户在本轮明确批准的一处白名单扩展。固定 SDK 安装与 guard 前缀保持原字节。Explorer输出128，Target前置256/终止512；参数8192字节、ID160、mixed512，原样回注。

## 文件

- RESULT.md：中文 TASK_RESULT、逐门禁与工程判断。
- protocol-budget-diagnostic.json：初始/最终槽、容量矩阵、前版失败与有限覆盖等级。
- verification-diagnostic.json：命令、PID、源码、日志SHA、历史锚、负控和清理。
- architecture-decision.json：发现、判断、三条路线、下一决策及泛化债。
- session-summary.json：正式物理WAL、真实usage/永久预约、业务及反馈；费用为guard estimate，账单未查询。
- capability-assessment.json：L2、Web、issuer、独立复现等边界。

正式 live 入口受 Source Freeze、metadata/cold、官方核价和唯一 Admission 门禁约束；已有根不能重置或换根续领配额。历史证书、旧 .local 运行现场与 docs/reviews/ 受保护。
