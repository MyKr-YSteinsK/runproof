# RPF-58 — Shared PGE Session Core

**Status: Partial。** 新共享执行核心已实现，双域完整合成证书通过独立校验；配置冷启动的收尾诊断丢失实际 SDK 回执，未取得正式配置入口必需的前置 PASS。一次冷启动额度已经消耗，未补跑。真实现场及交付结论以 [RESULT.md](RESULT.md)、[session-summary.json](session-summary.json) 为准。

## 实际接口与职责

| 已有位置 | 观察到的接口 | 本轮处理 |
|---|---|---|
| `orders.py:95` / `:143` | OrderSandbox 初始化与退款事务 | 新路径构造封装，复用原事务，不调用原受限路径构造器 |
| `orders.py:30` / `:43` / `:65` | 独立只读 AuthorityReader/HMAC snapshot | 新任务路径构造封装，复用只读连接及环境/收据校验 |
| `cross_trial.py:22` / `:144` | 旧 run_trial / 旧预算入口 | storage_task 白名单不含 rpf-58，未调用 |
| `cross_core.py` / `ops.py` | order/ops SQLite Witness 与业务 | ops 不是 Java config，不作为本轮 Java 证明 |
| RPF-57 coverage/session/verify | 上轮真实配置域覆盖闭环 | 全部冻结；不重标旧证书，不读旧运行根 |
| `config_pge_target.py:42` | TargetHost 的稳定工具/Fixture 协议 | 继承方法，仅新增本轮合同构造函数 |
| `config_live_runtime.py:267` | 固定 localhost HTTP 和业务映射 | 新 wrapper 接共享账本；实际 Java 业务本轮 NOT_RUN |
| `config_experiment_verify.py:52` | Fixture/HTTP/Tool/版本历史域 Oracle | 在新 ConfigPort 中复制精确谓词，绑定新合同验证器；测试函数逐字一致 |
| `spikes/rpf-55/probe.py` / RPF-53 固定 helpers | SDK/JAR/JDK 只读身份与生命周期 | 不调用其 preflight/live/旧 marker 入口 |

本轮唯一共用流程为：

```text
SharedSession.execute_trial(frozen contract)
  → Ledger reserve (same task/session)
  → static DomainPort.execute
  → domain_verdict (explicit domain Oracle)
  → shared_feedback.project
  → Ledger feedback + settlement
```

静态端口只有 `order-refund`、`config-java-http`，不接受自由 import、exe、URL 或 DB 路径。订单 Authority 是独立 SQLite 只读连接与收据；配置 Authority 是同一个 Java 服务的 GET current/history/list，二者不混级。事实含 domain/Effect/Authority 名称；不计算跨域统一信息增益。

## 离线测试与证书接口

```powershell
python -B -m unittest runtime.tests.test_effectwitness_pge_shared_core -v
python -B -m runtime.runproof_runtime.effectwitness.pge_shared_verify <envelope.json> --sha256 <trusted-external-raw-sha256>
```

正确 / 缺失 / 错锚或非法证据退出码为 `0 / 2 / 3`。完整合成正控标为 `SYNTHETIC_TEST_ONLY`，不提升为真实等级。签发者真实性未建立，自己计算文件哈希不等于可信第三方签名。两域完整真实证明缺失，因此本轮**不创建** `cross-domain-portability-evidence.json`。

## 一次性入口与现状

```powershell
python -B spikes/rpf-58/probe.py preflight
python -B spikes/rpf-58/probe.py offline
python -B spikes/rpf-58/probe.py fixture
python -B spikes/rpf-58/probe.py controlled-order
```

入口只适用于精确 Base 上本 Plan 的新任务根。`fixture` 已执行一次且不能再运行；其 SDK 收尾出现 `HOST_NOT_STARTED`，旧回执无法补造。修复代码将完整合同、SDK 报告和轨迹提前持久化，使用冻结合同里的端口核对清理；只通过零 SDK 的 mock 回归验证，未以之补记原冷启动 PASS。

`controlled-order` 是 Plan 建议的订单优先执行路径，只消耗同一 Session marker/同一本账的唯一订单 Trial；不绕过配置前置 Gate。`controlled-run` 仍要求新的合法同源冷 Fixture PASS，本轮未执行。正式配置 Java/SDK/POST 配额未消费，后续恢复需另行明确授权前置复验，不能删 marker 或换 Run 名重开。全部临时数据和快照位于 ignored `.local/rpf-58/`。

本轮 Provider=0、tokens=0、费用=¥0，无真实 Explorer/Provider Target；不能提升 RPF-57 L2 或声称真实跨域自主探索、统计优势、任意 MCP 兼容。main/旧证据冻结，未发布部署。
