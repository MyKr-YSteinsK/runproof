# TASK_RESULT — RPF-86 / rev-1

**Status: PARTIAL / B_UNACTIVATED**（封存时：调查、安全负控与负结果复核完成，五方法准入失败；Git 交付尚未发生）。

- Base / main：`5a7edc048f915102c0f2c4f6dfb4e041641d9f10`。
- 范围：**9 CREATE_ONLY**；唯一可修改 workflow 因选择 B 而完全不改。
- 本报告在 commit 前 seal，不预填未来 SHA/Push/CI，不 amend 回填。最终聊天补证 Git 收据。

## 原生结果与首次阻断

冻结前仅进行一次五方法试运行，原测试源码/方法体/断言不改，唯一 Runtime patch 为隔离子进程内 `pge_dual_contracts.WORK`。原六方法中的第六项 PORTABLE 方法不在本次 cohort 内，也未计入通过数。

| 原方法（`runtime.tests.test_effectwitness_pge_dual.DualTests`） | 实际结果 |
|---|---|
| `test_four_paths` | ERROR（四个 subtest error events） |
| `test_twenty_one_reanchored_attacks` | ERROR |
| `test_unknown_usage_and_restart` | PASS |
| `test_scope_lock_budget_and_invalid_selection` | PASS |
| `test_unknown_mutation_stops_writes_but_allows_readback` | PASS |

合计 **testsRun=5，3 个方法 PASS /2 个方法 ERROR，5 个 error events**。原生 child exit1、无 timeout/truncation，约 2.423 秒 outer wall；完整 cohort admission 记 0，不能说 5/5 通过。

首次实质阻断链由本次保留 traceback 直接观察：

`synthetic_payload → pge_dual_contracts.contract → capability → pinned_sdk_fields → historical public certificate read_bytes → READ_SCOPE_DENIED`。

被请求的 helper 为 `runtime/runproof_runtime/effectwitness/config_experiment_verify.py:pinned_sdk_fields`，证书为 `spikes/rpf-53/rev-6/config-live-evidence.json`。本轮只从实际 traceback 确认引用；**未继续静态打开未列 helper 源码，未读取证书内容**。该输入不在本 Plan 的精确读取白名单内，不能因为它位于 public tracked tree 就自行放开。其它 READ_SCOPE_DENIED 事件未逐项归因，保留原计数，不都归作证书读取。

本轮不允许 patch SDK identity、替换证书、读取旧私有目录或增加原业务/source 常量补丁。因此源冻结前确认 B；正式五方法执行 **NOT_RUN**，避免在前提未满足时重复同一真实失败。该缺口不是 os WORK 注入本身的证明失败，但足以否定“仅 WORK 注入即可完成本轮全部准入”的假设。

## 417/30 责任账与范围

按固定公开 RPF-84 分类、当前 matrix 和精确列出的 30 个 test 文件，构建 **417 个 DEDICATED_RUNNER ID /30 模块**的完整逐方法静态责任账。记录源 blob/raw/LF hash、同文件 helper/call 边、物理 I/O 引用、root 符号、原 required/reason/disposition；未列 helper 不额外读取，跨模块边保持 UNKNOWN/NOT_INSPECTED，不把名称含 request/sdk 的静态引用说成真实网络调用。

当前 required 缺口仍为 **539**：DEDICATED_RUNNER417、FROZEN_PRIVATE_ARTIFACT69、WINDOWS_NATIVE35、LEGACY_SDK_PRECONDITION16、LEGACY_OWNER_ROOT2。417 行全部仍 `required=true / disposition=UNAVAILABLE`；三个局部 PASS 不从 417 或 539 扣除。源码四个 pge_dual helper 及原六方法类均保持固定 Git/原字节与 AST 身份。

## Guard、所有权与独立复核

G0 真正通过本地 HTTPS Base、main/index/tracked-clean、ACL/owner、空占/ignore/reparse、固定 source blobs、hooks 与既有 CI 边界；先原始二进制 stdout，再 exclusive-create 收据并文件 flush/fsync，最后建本轮 owner。Windows 目录 fsync 单列 UNAVAILABLE。

Guard 在 import 原测试前安装；既有合成 WAL/lock 只写新物理 owner，逻辑 owner 仍是 `rpf-63`，patch 最后恢复。没有静态读取旧 `.local/rpf-63` inode；新 mkdir/no-reparse 与 lexical scope 支持物理分离，旧 inode 比较因禁止历史 stat 记 UNAVAILABLE。

真实控制调用验证：旧根 `open/mkdir/stat` 被拒绝，mkdir/stat 在委托 saved OS 函数前停止；实际 socket 构造、Python subprocess 被拒绝；当前新 task parent 的 canary 写入被拒绝，parent 复核该 canary 不存在。还覆盖方法漏/重、SKIP 假 PASS、source/assertion-count/owner 漂移、重复 result、casefold/实际 symlink或junction、CI身份、crash/exit1/missing/timeout/truncate、未退出/未排空和 JSON 负控。

**不夸大系统调用证明**：证明范围为 CPython audit 与显式 `os.stat/os.lstat/Path.resolve/os.mkdir` 拦截；任意 native syscall、kernel sandbox 和全 OS process tree 证明为 UNAVAILABLE。回收只证明精确 Popen 句柄 kill/wait、输出排空。禁止内部 test child 创建任何额外 subprocess；supervisor 启动当前 Python 属受控 harness。

冻结前 harness 8/8 PASS；第一次有 stdout ResourceWarning，随后在白名单源码中关闭已排空 Popen stdout，原日志保留，第二次 8/8 PASS。没有改 Runtime 或原方法来修测试。

冻结后一次正式 harness **8/8 PASS**（约1.971秒，1387 bytes）；一个独立临时 Python 进程 **PASS_NEGATIVE_EVIDENCE_ONLY**（约0.553秒），只读复核当前任务保留的 3/2 失败结果、旧 candidate source snapshot、原五源身份、原生事件、pid/exit/log、物理文件 manifest 和新 WAL 的原逻辑 owner。它没有 import/执行原五方法，也不是独立新环境或第三方 Issuer。snapshot 仅为本任务新候选脚本，不是复制历史 Run/WAL。

正式两项合计墙钟见 verification，远低于 420 秒；正式 unit≤180秒，复核 child≤60秒，输出≤2MiB。原生预试 child≤180秒；原始失败现场与资源输出保留。没有冻结后改源或原生重跑。

## Gate（封存时）

| Gate | 状态 | 证据 / 限制 |
|---|---|---|
| G0 | PASS | 有效事前收据、真实 Base/ACL/空占/身份 |
| A01 | PASS（静态责任账） | 417 IDs/30 模块、539 分布、未知依赖明确保留 |
| A02 | PASS（已观察所有权） | 实际写入新 owner、逻辑身份不改；不代表五项完整准入 |
| A03 | FAIL | 预试 3 PASS/2 ERROR；正式五方法 NOT_RUN（已知输入权限缺口） |
| A04 | PASS | 真实 API/进程/路径/假阳性拒绝；有限接口范围如上 |
| A05 | PASS | pinned 原源码/AST 不改，旧证书内容及私有 WAL 未读取 |
| A06 | PASS | 正式新 unit8、格式/strict JSON、B workflow Base byte equality、独立负证据复核 |
| A07 | PASS（B 决策） | workflow 原 blob `fe060ccb918acd318ff1b542cc6ece597a80d424` 完全保留，未加 step/artifact |
| A08 | NOT_RUN | seal 时 commit/普通 Push/readback 尚未发生；最终聊天补证 |
| A09 | NOT_APPLICABLE（pilot） | B 未激活，无 hosted 五方法证据；普通 push 的既有 CI 仍须如实观察 |
| A10 | PASS | 1232 required/539缺口、Task/Evidence/Stage、Release Authority 分离 |

## 交付与下一决策

选择 B 保留候选源码、417 责任账与失败证据；不触碰 workflow/Router/matrix/RPF85 verifier/Runtime/Project State。既有 RPF85 诊断闭环继续有效，当前任务没有改善正式覆盖。

Provider0、SDK0、Java0、Docker0、实际业务写0；只有本轮新 owner 的离线合成 WAL/lock。没有 Key 探测、旧 WAL 修复或历史预算复活。CPU/磁盘/未来 hosted CI 费用为 UNAVAILABLE。

下一决策只能是新 Plan 精确授权相关 helper/历史 public certificate 的只读审查并确认逻辑身份边界，或改选 cohort；本轮不预授读取、复制或数据替代权。RPF-82 PARTIAL、RPF-74/rev-4 PAUSED/DEFERRED、RPF-81/rev-2 BLOCKED、RPF-78 A08 FAIL 不变。

详细证据：[owner dependency ledger](owner-dependency-ledger.json)、[verification](verification-diagnostic.json)、[counterexamples](counterexamples.json)、[decision](decision.json)、[preflight](preflight-diagnostic.json)。EVIDENCE_ACCEPTED 与 STAGE_ADVANCED 由 Architect 独立裁定。
