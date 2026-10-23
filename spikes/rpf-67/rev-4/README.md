# RPF-67 rev-4：订单终止阶段预算与独立 Witness

本任务保持真实固定 SDK、严格 Provider JSON 和原 SQLite 业务方法；Session 在初始化数据库前绑定新 owner。只修改 Plan 白名单五个文件。

预算槽为 `[3000,2600,2600,4200,1400,1200]`，总额15000；合法协议最多四次响应，第5/6槽不可达。首轮按完整规范化请求 UTF8 字节计上界；后续为可信前次 prompt tokens + canonical suffix bytes +512。终止输出保持512。

`PRE_SEND_BUDGET_REJECTED` 在 Provider 预约及 HTTPS 前 create-only/fsync 落盘，再绑定同一 WAL。两侧断裂均永久 `TORN_PRE_SEND_RECEIPT`；该错误是 Platform 预发送拒绝，不补记 Provider UNKNOWN，也不返还既有预约。

## 离线复核

```powershell
python -X utf8 -B spikes/rpf-67/rev-4/probe.py verify --witness spikes/rpf-67/rev-4/order-target-witness.json --sha256 <原件raw-SHA256>
```

缺外部锚返回2，原件通过返回0，错锚或语义篡改返回3。仅在条件 Witness 实际存在时执行该命令。测试可使用 `python -X utf8 -B -m unittest runtime.tests.test_effectwitness_pge_r67 -v`；写入本轮 ignored tests 根，不续跑旧会话。正式 init/metadata/cold/admit/live 是本次冻结与一次性预算入口，不能据此重新授权运行、换 root 或补发。

完整实际命令、PID、版本、失败和原始外部锚见 verification-diagnostic.json；真实调用及费用边界见 session-summary.json；官方价目观测见 preflight-diagnostic.json。合成模型明确为 SYNTHETIC_TEST_ONLY。单订单成功不证明同一真实双域 Session、因果优势或生产发布能力。
