# TASK_RESULT — RPF-58 / rev-2

Status: Complete

执行日期：2026-10-20。正式业务、冷启动、离线验收及 A-10 Git 交付已完成。`EVIDENCE_ACCEPTED=PENDING_ARCHITECT_REVIEW`，`STAGE_ADVANCED=NOT_YET`。

## 1. 身份、工作区及范围

- 实测 Root：`D:/CS/runproof`；Base/Parent：`1af24d94610c4e5dcf36d65c182add172e1401d2`。
- 分支：`codex/rpf-58-rev2-cross-domain-controlled-closeout`；origin：公开仓库 `MyKr-YSteinsK/runproof`，HTTPS fetch/push 身份一致。
- 原父分支：`codex/rpf-58-cross-domain-pge-core-portability`；main 快照：`bda0cd49e50e3181f604324e94877a24b9885334`。
- 开始时 tracked/index 干净，只有顶层 `?? docs/reviews/`；该目录未进入、枚举、读取、修改或暂存。旧运行根未读取或修改。
- 新 task root `.local/rpf-58-rev2/` 在创建前不存在、被 ignore，父路径无 reparse point。仅使用允许的固定 SDK 和 Java 来源；原安装与来源仓库未修改。
- 交付仅八个白名单源码/测试/Runner 文件及本目录六个文件。旧 rev-1 报告、摘要、诊断和历史证书保留原字节。无 Project State 改写、main push、PR、merge、发布或部署。

## 2. 修复、来源与技术决定

SDK 进程启动后先 fsync `sdk-process-started.json`；收到结构化结果后先写 `sdk-received.json`，然后才关闭 Host 和检查后置条件。清理使用冻结合同端口，另保存 `sdk-cleanup.json`。畸形报告保留状态/错误类别/hash，不持久化自由模型文本、stderr 原文或任意被拒绝路径。cold 在语义检查前保存完整 `capture.json`，失败保留事实且不退还额度。

新增 hash-chain TaskGuard，metadata/cold/Session 均先预约再执行，拒绝覆盖和额度重置；第二次 cold 必须已有 FAIL、实际修复和新的 Source 冻结。正式业务继续使用唯一 `SharedSession.execute_trial` 与单一 Ledger。新增实际入口及 Port 函数 bytecode 指纹、调用进入/返回事件。删除绕过 cold Gate 的单独订单业务入口。

新身份为 owner `rpf-58-rev2`、`rpf58r2-*` Run、v2 schema、Verifier `rpf58-shared-verifier-v2`。Verifier SHA：

`98b773f9af738e4e91ad7d9da233432b0f935eaa43d171ecefeb48225fe092dc`

23 个执行依赖的 Source Map 见 `verification-diagnostic.json`，其 canonical digest：

`b42aa85c0d7aaed20f2bce1bda3c1629a8f1fa9513615afa356b073697c4141f`

preflight、offline、cold、正式两个 Trial 和签发的执行 Source 完全一致。cold PASS 后、正式 Session 前，只加强了测试 helper 的内部摘要重算与 no-op mutation 检查；该测试模块不在执行 Source Map 中，单独冻结 SHA 为 `8495b056c0e29ce15da7a32c4200538a2b9e9e201ce482a9fa25d8392533ac58`。最终完整回归快照的八个交付文件均与工作树一致。正式运行后没有修改执行源码、Verifier、Oracle 或测试。

TaskGuard 中 `offline_gate_sha256` 是 Source Map 的绑定摘要标记，并非 offline 结果文件原始字节 SHA。它不作为外部可信锚。

固定来源实测：CPython 3.12.13，exe SHA `e9f7e4baa0da1c21ffc3c2c2a644459b1a38dced56dfc7846e16f801645d520f`；launcher SHA `74e020321eb8f828f0c2cfe865082fcf94aa6e7cf488e8a744d89b9282eaeb83`。Pydantic AI 2.57.0 / OpenAI SDK 3.35.1，RECORD mismatch=0，metadata 实际一次。Java17/H2 固定来源 commit `0258b9cef02ea74a40989d035c79256c776409c0`，manifest SHA `33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`；task-owned JAR 66,981,576 bytes，SHA `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。

## 3. 冷启动与真实双域记录

### 3.1 Cold

尝试 1：**ACTUAL PASS**；Popen/ready/report PID 均为 `20604`。四次 Fixture completion、三个唯一 Tool Call，顺序 inspect→create→update，回注请求为 `[2,3,4]`。`COMPLETED`、退出码0、stderr 0 bytes、guard denial 为空。实际 `FAULT_INHIBITED` 一次；Host线程停止、Host端口关闭、SDK退出均为 true。capture SHA：

`139825190fea2b1b5167ac683cedc56d0bf8175bff76d682cbe09e40312c2d1d`

尝试 2：**NOT_RUN**，第一次通过后未使用。冷 Fixture 未启动 JVM，Provider=0。公开结构化回执见 `cold-fixture-diagnostic.json`；原始 started/received/cleanup/capture 与任务预约仅留新 ignored root。rev-1 不可得回执仍不可得，没有回填旧失败。

### 3.2 唯一 Session、订单与配置

Session：`rpf58r2-session-5693ca727b444f4a`；共享执行进程 PID `33728`，运行约27.6秒，小于1200秒。先独占 started/预约再执行；TaskGuard 六帧依次是 metadata 预约/PASS、cold 预约/PASS、Session 预约/PASS。

| 项目 | 订单 | 配置 |
|---|---|---|
| Run | `rpf58r2-order-0940c29b6c0d4e08` | `rpf58r2-config-71244413b4d34ca7` |
| 实际环境 | fresh SQLite、确定性 Target | fresh Java17/H2、SDK scripted Fixture |
| 初态→终态 | PAID2500/refunded0/revision0 → REFUNDED2500/revision1 | ABSENT → rpf53-v2/version2/history[2,1] |
| 写操作 | 一次退款，唯一 COMMITTED receipt | POST create一次、update一次 |
| Authority | SQLITE_READ_ONLY_RECEIPT_READER | SAME_SERVICE_READ_ONLY_HTTP |
| Oracle | 独立只读 Reader/HMAC/Receipt 与 effect Oracle | HTTP current/history/list 与独立纯函数 Oracle |
| planned/triggered/observed | false/false/false | true/false/false，实际 FAULT_INHIBITED |
| 清理 | 连接关闭、exclusive lock probe、DB保留 | Java/SDK退出、Java/Host端口关闭、Host线程停止、临时local key释放 |

订单 receipt：`receipt-6a45f224dcc742c3139bb0ef`；operation：`refund-rpf58r2-order-0940c29b6c0d4e08`；DB raw SHA `f0869286fa968432f196b8d999d303f5f3e4f64a576e4748b5a6d1ffc83ed118`。没有复用 rev-1 数据或重开事务。

配置 Java PID `17944`；SDK Popen/ready/report PID `13536`。实际 argv/JAR、loopback listener所有权、无外联核对通过。四次 scripted completion /三工具，8次业务HTTP、2POST。health实际仅1次UP；预留3槽，另两槽均 `UNUSED_RESERVED_NO_IO`。未执行故障注入或未知写重试。

### 3.3 共同路径、反馈与预算

两个 Trial 均由实际 `SharedSession.execute_trial` 分派。入口 bytecode SHA `794c075c60b38eb9152d506cdfc5f066b4ee3237975ed18507b06c96c158b643`；实际 Port 分别为 `pge_order_port.execute` 与 `pge_config_port.execute`，独立 Verifier 重算其身份。

事件序列：订单 INPUT1/dispatch3/enter4/return12/verified14/feedback15/settled16；配置 INPUT17/dispatch19/enter20/return74/verified76/feedback77/settled78。前轮已验证反馈确实早于后轮冻结输入，所有正式资源同一 WAL 先预约后结算，无拆账/返还。

订单反馈 SHA `11b04ae43be2b071da2599a437676768119f6a10a9f1b31e67ead10a63c29f24`；配置反馈 SHA `6ddfcad2b1c28b0eb39e1206d32944048a6530f12900bb05b8136cb26cc7d68c`。

| 额度 | 实际 | 上限/处理 |
|---|---:|---|
| Provider/tokens/人民币 | 0/0/0 | 全禁；未读取或使用Provider key |
| metadata进程 | 1 | ≤4 |
| cold尝试 | 1 | ≤2；第二次NOT_RUN |
| 正式Session/Domain Trial | 1/2 | 1/2 |
| SQLite Trial/退款mutation | 1/1 | 1/1 |
| 正式JVM/SDK Fixture | 1/1 | 1/1 |
| 业务HTTP/POST | 8/2 | 12/2 |
| health | 1 | 预留3；另2槽未用且不返还 |

## 4. Witness、独立验证与回归

完整新证书：`cross-domain-portability-evidence.json`，77,522 bytes，schema `rpf58-cross-domain-portability-evidence-v2`，`source_kind=BOTH_REAL_CONTROLLED`，claim `CROSS_DOMAIN_SHARED_CORE_LOCAL_CONTROLLED_EXECUTION_PROVEN`。原始字节外部 SHA-256：

**`03aa9ac84f725de982b537a8882b27b764aaf6da9868b9a65a2cdcfd6e4d208d`**

真实证书及合成测试 CLI 正确/缺失/错误锚均为 **0/2/3**。20类 rehashed 负控均退出3：authority_swap、budget_split、cleanup、cold_cross_source、cross_domain_fact_splice、cross_revision_order、domain_swap、duplicate_write、empty_authority、false_effect、fault_overclaim、future_feedback、mixed_source、old_failed_cold、provider、runtime_callable_splice、schema_downgrade、source、time_reverse、unused_health_forgery。测试确认 mutation 非 no-op，重算内部任务/账本/冷回执等关联摘要及外部锚后仍拒绝。

离线生命周期模拟覆盖 Host关闭、先保存回执再失败、SDK异常/畸形报告、端口检查失败、capture写失败、冷失败不可重用/标PASS、损坏/锁竞争/超时/source mismatch/重复写。最初离线迭代曾发现语法、变量遮蔽、Mock拦截范围及真实样本mutation no-op问题，均在业务冻结前修复；失败日志保留，不计作冷或正式业务重试。

最终定向 **18项通过**；完整 Runtime **365项发现，363项成功，2项Docker跳过，0失败/0错误**，112.619秒。使用隔离快照和新任务缓存，无新增Provider/Java业务。11件历史锚经当前工作树原始CLI全部退出0，原字节与各自Verifier未改：RPF43、44、48、49、50、51r4、52r3、53r6、55r2、56r4、57v1。完整SHA及退出码见 `verification-diagnostic.json`。

Reviewed Artifacts/Public Docs 检查通过。Web/Maven/UI、Docker正式边界、Hosted CI：**NOT_RUN**；本轮无相应边界改动。

## 5. Acceptance

| Gate | 状态 | 实证 |
|---|---|---|
| A-01 | PASS | 精确Parent/remote、新分支/任务根、白名单与用户目录保护 |
| A-02 | PASS | v2 Source/Run/Verifier，旧事实隔离与混源拒绝 |
| A-03 | PASS | 同源真实cold01回执/PID/工具/回注/gate/cleanup |
| A-04 | PASS | 单一正式WAL、预算与异常离线负控 |
| A-05 | PASS | fresh SQLite唯一退款/receipt与只读Authority |
| A-06 | PASS | 新Java/H2与SDK三工具、8HTTP/2POST/1health及清理 |
| A-07 | PASS | 实际共同入口指纹、两Port、严格反馈事件顺序 |
| A-08 | PASS | 新完整Witness、0/2/3及20类语义负控 |
| A-09 | PASS | 365项/2skip、11旧锚、Reviewed/Public、0Provider和额度 |
| A-10 | PASS | focused commit/push，ls-remote确认实现SHA；tracked/index干净，仅原用户目录未跟踪 |

## 6. 残留、结论边界与交付

新 ignored root 保存必要原始结构回执、单一WAL/任务预约、SQLite证据、JAR副本、隔离测试快照及重要失败日志；不进入Git。所有task-owned进程/端口清理成功。普通一次性版本生成器在交付前清理。旧运行数据/安装/来源仓库不清理。

本次只建立两种真实受控Port共用内核的机制证据。配置是SDK scripted Fixture，订单是确定性Target；real Explorer未执行，跨域自主LLM/PGE、H1/H3、WorkSwarm均未证明。配置同服务GET不提供数据库外部独立Authority；issuer真实性未建立、独立复现未测试、归因仅相关、跨域信息增益不可比。`FAULT_INHIBITED`不算故障激活成功。历史RPF57结论独立保留。

Git交付：实现与证据提交 `cf6df740383848a7e9d90a90648b3090b5d499ce` 已普通push至本轮新分支，`git ls-remote` 观察同一SHA；本地tracked/index干净，仅保留开始时的顶层 `?? docs/reviews/`。远端父分支仍为 `1af24d94610c4e5dcf36d65c182add172e1401d2`，main仍为 `bda0cd49e50e3181f604324e94877a24b9885334`。本次文档收口另作commit/push；其最终SHA在聊天回执报告，不循环amend报告自身。未创建PR或更改main，Hosted CI未运行。后续范围由Architect审查决定，本轮不自动创建RPF59。
