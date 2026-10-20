# RPF-58 rev-2 — controlled cross-domain closeout

本修订使用全新 `.local/rpf-58-rev2/`、owner/run/schema v2 和唯一 Session/WAL。旧 rev-1 的 Partial、已消费订单及冷启动失败保持原样。实际结果、额度与交付身份见 [RESULT.md](RESULT.md)。

## 独立离线验证

从外部可信渠道取得完整证书原始字节 SHA-256 后：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.pge_shared_verify spikes/rpf-58/rev-2/cross-domain-portability-evidence.json --sha256 <external-raw-sha256>
```

正确/缺失/错误外部锚退出码为 `0/2/3`。CLI 不运行 SDK、Java、Provider 或业务写入。内部摘要不能代替外部锚，文件哈希不是发行者签名。合成样本仅可标记 `SYNTHETIC_TEST_ONLY`，旧版、混源、假冷回执和缺失领域不能成为新真实证书。

## 实际共享路径

`SharedSession.execute_trial` 对两个静态域使用同一条冻结输入→预约→调用→领域 Oracle→反馈→结算流程。dispatch 事件绑定当前入口和实际 Port 函数的 bytecode SHA/模块名，调用前后均留事件；不是仅记录相同函数名。订单使用 SQLite 事务与独立只读连接/收据，配置使用 Pydantic AI **scripted Fixture** 和 Java17/H2 服务 GET current/history/list。事实保留 domain/Effect/Authority 命名空间，不比较或汇总跨域信息增益。

## 回执与不可返还额度

`run_sdk` 在 Host 关闭和清理后置检查前写入 `sdk-process-started.json`、`sdk-received.json`，另写 `sdk-cleanup.json`。畸形或缺失报告只保留结构和 hash，不能取得 PASS。cold 每次使用新目录、一次性 fsync capture、明确 Tool/回注/gate/PID/cleanup 校验；成功后禁止第二次。失败仍消费额度，只有明确修复、新 source 和重新离线验证才允许第二次，最多2次。

TaskGuard 将 metadata（≤4）、cold（≤2）和正式 Session（≤1）预约保存在不可覆盖的 hash 链，正式两域资源另由**同一个** Session Ledger 负责。订单退款≤1，正式 JVM/SDK各≤1，业务HTTP≤12、POST≤2，health预留3槽；未使用槽保持 `UNUSED_RESERVED_NO_IO`，不冒充实际GET。Session单调时限1200秒。未知写入停止，不返还、不重发POST、不另开Run。

## 一次性入口

以下是原授权入口；已有 marker 和配额不得删除或重置，重跑业务需要新授权：

```powershell
python -B spikes/rpf-58/probe.py offline
python -B spikes/rpf-58/probe.py preflight
python -B spikes/rpf-58/probe.py fixture
python -B spikes/rpf-58/probe.py controlled-run
```

rev-2 删除了订单绕过冷 Gate 的独立业务入口。代码要求 cold/preflight/offline/执行/签发的 Source Map 相同，先获得 cold PASS 才能启动**任何**正式业务。只有一个 fresh order→config Session 全部通过，才签发本目录完整证书。

Provider=0、tokens=0、¥0；不读取或使用现有 Provider key，不运行真实 Explorer/LLM Target。`BOTH_REAL_CONTROLLED` 只代表这两种受控 Port 的实际执行；不代表两个真实LLM Agent、跨域自主探索、统计优势、外部数据库独立认证或任意MCP兼容。Issuer真实性、独立复现与WorkSwarm边界仍保留。无main写入、PR、合并、发布或部署。
