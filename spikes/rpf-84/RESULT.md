# TASK_RESULT — RPF-84 / rev-1

**Status: PARTIAL（封存时：本地 A 激活前提通过，Git 交付与 hosted Runtime 尚未发生）**

- Base / main：`e477be107dd186c45cdef750cd00ebf82ea55402`。
- Decision：**A_ACTIVATED_FAIL_CLOSED**；本次精确 5M+8A，不修改其它 tracked 源码。
- 本报告在 Git 提交前 seal；不预填未来 SHA/Push/CI，不 amend 回填。最终聊天补证交付状态。

## 实施与实际验证

Router 复用原流程，主进程不 import Runtime 测试；每模块 inventory 与 execution 分别用独立当前 Python 子进程。owner 迁至本任务，CI output 绑定 GitHub run/attempt，拒绝旧根、`..`、casefold 混淆及实际 symlink/junction。子进程环境只继承明确列举的非秘密变量；守卫在旧根 mkdir/open 事件的 syscall 前拒绝。

RPF-75 原 Probe 与测试均未修改。真实子进程加载 Probe 后，实际 Python subprocess 和 socket 构造仍被原 Audit Hook 拒绝；兄弟子进程能完成 `127.0.0.1` 的 5 字节回环和 Python 子进程启动。源码 pin 负控检测移除/弱化 Hook，未靠直接调用 guard 冒充实际 Hook 安装。

本地动态发现 **57 模块 / 1232 唯一 ID / 1232 唯一 disposition**，与公开 RPF-82 历史 ID 集合完全相同，没有借用历史执行 PASS。inventory-only 实际 exit **1**，结论 **REQUIRED_COVERAGE_UNAVAILABLE**。分类为 **693 PORTABLE（NOT_RUN）/539 UNAVAILABLE**：DEDICATED_RUNNER 417、FROZEN_PRIVATE_ARTIFACT 69、LEGACY_OWNER_ROOT 2、LEGACY_SDK_PRECONDITION 16、WINDOWS_NATIVE 35。两项 RPF-81 隐式 helper 仍按 owner 前提不可执行；没有补旧文件或把不可用算 SKIP。

Router 原有 **32** 个 unittest ID 全保留，新增 **9** 项后正式 **41/41 PASS**，约 4.066 秒（含进程启动；unittest 自报约 3.863 秒）。保留两次冻结前真实运行日志（38/38、41/41）；没有抹除早期结果。冻结前自写 AST 检查曾误把嵌套 Benign.test_entry 计入 RouterTests，随后改为该类直接方法计数；这不是 Runtime 测试失败。strict JSON、AST/compile、严格 PyYAML 和五项 workflow 篡改负控通过。CRLF 的默认 whitespace 诊断保留；命令级 `cr-at-eol` 检查通过，其余 whitespace 检查未关闭。

RPF-60 正式聚焦只执行原 `test_competing_processes_share_provider_reservation`，实际 **1 PASS**；两个真实 child 中恰一项预约成功，均 exit 0、waited=true，无额外业务请求。聚焦 outer process 约 1.467 秒、原 unittest 自报 0.809 秒。原九方法、断言和业务算法不改；完整九项、300 秒热点复现和本地完整 Runtime **NOT_RUN**。测试 harness 的 source-bound adapter 仅准入本次精确 folder，并将原两条 Python 命令导向受控 CLI；不会准入其它 owner。

总 Runtime lane ceiling **1500 秒**，每 child **≤300 秒 /2 MiB 输出**。deadline 传入 child 并钳制后续启动与竞争子进程 communicate；耗尽不得额外启动。超时/截断/缺 final result 保留实际 exit、进度和未运行项；未开始方法不得从进度伪造 PASS，SKIP 需实际 unittest 事件。只证明精确已启动 Popen 的 kill/wait/输出排空；OS process-group 全后代回收为 **UNAVAILABLE**，不夸大。

## RPF-66 历史来源与 Guard

历史 parent blob `677d957302476bb89b52dedb5ab047f2850bd686` 绑定提交 `76088c6e268388fe414956d48cad0242641ae01a`。恰一处 `model_settings={"max_tokens": 256,` →512 的 raw byte 替换等于冻结 child blob `b10e9bbc7d59fcab7b0dea6db9c214a27b0dce01`。测试只读本地 Git 对象，不 fetch、不 checkout、不执行旧源码。Windows working child 的 CRLF 与 Git LF blob 明确分栏：先验证 raw Git 对象唯一差分，再验证明确的 checkout EOL 映射；没有静默重写 frozen child。

RPF-83 当前 sanitizer blob `d37f027631fe0eff26f33b29e407281971d9c40c` 原样保留；旧 Witness/Source Map/verifier 不重签。R66 其它全部方法/helper AST 不变，目标方法中从 `ctx,_=fresh()` 起的原 Guard 块也保持不变。错对象、0/2 次 token、非 token 字节差异、当前新源码冒充历史版均被实际负控拒绝。独立受控 root 对原 frozen Guard 的网络/DNS/越界读取/进程/bind 五项拒绝通过。

**这一独立 byte+Guard 控制 PASS 不等于 R66 原完整方法 PASS。** 原方法仍因历史 owner 的 `fresh()` 义务路由为 required UNAVAILABLE；本轮没有执行或改造它的历史业务 fixture。

## Gate（封存时）

| Gate | 状态 | 实际边界 |
|---|---|---|
| G0 | PASS | 本地 HTTPS Base、AGENTS、干净 HEAD/index、ACL、空占/reparse、hooks、固定 blobs 和持久收据 |
| A01 | PASS | 仅 5M+8A；protected source 无差异，历史私有根/Witness/Source Map 零写 |
| A02 | PASS | 实际 Hook 自拒绝，独立 sibling socket/subprocess 成功 |
| A03 | PASS（身份对账） | 57/1232 动态身份一致；完整执行覆盖未通过，539 required UNAVAILABLE |
| A04 | PASS（独立来源/Guard 控制） | 固定 Git 对象精确差分及五项 Guard；原方法仍 UNAVAILABLE |
| A05 | PASS（聚焦） | 两实际 child、恰一预约、全部 wait；完整九项 NOT_RUN |
| A06 | PASS | 原32+新增9项、真实 crash/exit1/missing/timeout/truncate、假绿/owner/source/matrix 负控及格式 |
| A07 | PASS（本地激活决定） | 选择 A；只替换全局 discover 一行，其它 workflow 语义一致；hosted 仍须独立裁定 |
| A08 | NOT_RUN | commit/普通 Push/remote readback 由最终聊天补证 |
| A09 | NOT_RUN | 新 hosted Run 尚未发生；Fresh Canonical Gate 未执行 |
| A10 | PASS | 无阶段推进或 release/deploy；旧失败/暂停状态保留 |

## 剩余义务与交付限制

Plan 带入的旧 Run `41400142627` 为 failure，1118 tests /116 errors /1 failure /2 skips、936.850 秒；原 RPF-83 聚焦通过，Fresh Gate skipped。本轮未将旧结果当作重跑。新完整 hosted lane 只有实际执行后才能判定 Linux 隔离有效性和剩余错误；即使 PORTABLE 全通过，539 required UNAVAILABLE 也必须使 CI 非零，后续 Canonical Gate 仍不应运行。

Provider/API/真实 SDK/业务 HTTP、Java/数据库业务实验、生产动作均为 **0**；实际 CPU/磁盘/CI 费用 **UNAVAILABLE**。RPF-75 守卫、RPF-66 frozen child、RPF-83 Runtime/测试、旧报告/证书未改。RPF-82 整体 PARTIAL、RPF-74/rev-4 PAUSED/DEFERRED、RPF-81/rev-2 BLOCKED、RPF-78 A08 FAIL 保持；EVIDENCE_ACCEPTED 和 STAGE_ADVANCED 不由本报告自行批准。

完整证据见 [coverage ledger](isolation-coverage-ledger.json)、[source identity](source-identity-ledger.json)、[counterexamples](counterexamples.json)、[verification](verification-diagnostic.json) 与 [decision](decision.json)。报告封存后不回填 Git/CI；唯一外部未结算项为本次普通 Push 后的 hosted 完整运行。
