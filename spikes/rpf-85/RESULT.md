# TASK_RESULT — RPF-85 / rev-1

**Status: PARTIAL（封存时：实现、正式聚焦与 A 路径检查完成；Git/新 hosted 结果尚未发生）**

- Base：`c341c28d1afc7d23b3e09934bf51788ffae62700`；现有 `main` 单树。
- Decision：**A_DIAGNOSTIC_HANDOFF_FAIL_CLOSED**。
- 精确范围：**1M+8A**。Router、matrix、Runtime 测试、RPF-12 核心、Project State 和历史证据未修改。
- 本报告在 commit 前封存，不预填未来 SHA、Push 或 CI；最终聊天提供独立 Git/Actions 回执，不 amend 回填。

## 实际改变

新增 stdlib-only `ci/verify-runtime-coverage-handoff.py`。`assess` 只读本次受控输入，固定本地 Git 的 Router/matrix blob，验证当前 tracked test tree、历史 57 模块/1232 ID、源摘要、路由与 required 标志；并逐一读取原 inventory/selection/result/progress、真实进程结算收据和输出 hash。原生 class/module SKIP 必须有实际事件、方法前缀和 fixture_skips 对账；不以 row 自称的 SKIP 或 stdout 文本推断通过。独立事件状态机和原 pinned Router 的 reconcile 构成两条核对路径。

只有完整 portable PASS/SKIP、无任一 source/身份/进程/数据/覆盖异常时，`runner_exit=1 + overall=REQUIRED_COVERAGE_UNAVAILABLE` 才允许 `CONTINUE_DIAGNOSTIC_ONLY`。状态 JSON 以 exclusive-create/flush/fsync 生成，绑定 run/attempt/commit、ledger hash、证据 manifest、counts/routes 和当前来源。状态明确保持 `release_eligible=false`、`release_executed=false`、`deployment_authorized=false`。

`enforce` 重新读取状态及原 ledger/收据/来源，不仅检查某个状态字段。539 required UNAVAILABLE 时返回 **1**；缺失/无效输入返回 **2**；只有全部 required 真正满足才可能返回 0，且 coverage-only 仍不是 Release Authority。其摘要只追加独立 RPF-85 blocker，原 RPF-12 summary 不改写。

Workflow 恰一处 `set +e` 只包围 Router，立即保存 `$?` 后恢复 `set -euo pipefail`；Handoff 与原下游 checks 不吞错。RPF-83 聚焦、Java17/Python3.12/Node22/Docker、reviewed artifacts/RPF16/17/18/Golden Demo/Maven/npm、fresh RPF-12 和原 Summary 断言都保留。原 Artifact 只增加 coverage JSON；其后 always Final Required Coverage Barrier 保证上游失败或证据缺失也最终失败。on/permissions/concurrency/35 分钟均不改。

## 实际验证

G0 的本地 Git HTTPS 返回固定 Base，工作树/index 干净，ACL/owner、空占、ignore/reparse、固定来源及 hooks 检查通过。先输出二进制 UTF-8 原始检查表，再 exclusive-create 收据、文件 flush/fsync，最后创建新 owner。Windows 目录 fsync 单独记 UNAVAILABLE，未伪造。未打开旧私有 WAL/marker 或 reviews。

冻结前首轮 **9/9 PASS**，约 **101.396 秒**；随后补齐新/漏/重动态 ID、required/inventory 标志、Summary 追加边界与 aggregate 类型检查。格式/AST/compile、strict JSON、PyYAML safe_load、工作流精确变换、**8 项 workflow 篡改负控**及 **4 个 Bash step 的 Git Bash `-n`** 通过。默认及 CRLF-aware whitespace 退出码见原诊断；未关闭其它 whitespace 检查。

冻结后只进行一次正式 unittest：**11/11 PASS**，约 **111.098 秒**，上限 240 秒/2 MiB 合计输出；实际输出 **2113 bytes**，无超时或截断，进程已退出、输出排空、三份冻结来源不变。不存在冻结后改源重跑。

完整 57/1232 identity 的本地 fixture 是本轮新 owner 下的 **SYNTHETIC_OFFLINE_TEST**，不是重跑 Runtime。它以公开 required ID/当前 matrix/source 构造自洽的模拟 inventory/result/进度和收据。实际 CLI 正控：

| 控制 | 实际 exit | 结论 |
|---|---:|---|
| assess，模拟 688 PASS /5 SKIP /539 UNAVAILABLE | 0 | CONTINUE_DIAGNOSTIC_ONLY |
| enforce，同一状态及 ledger 重新验证 | 1 | RELEASE_BLOCKED_BY_REQUIRED_COVERAGE |
| 同一输出路径再次 assess | 2 | 拒绝覆盖已有结果 |

负控包括 duplicate/nonfinite/超长/截断/缺失 JSON、路径逃逸及实际 reparse、退出码错配、漏/重/新 module/ID、required 虚减/降级、未执行假 PASS、timeout/truncate/exit1/未退出/未排空/缺 final、伪造 SKIP/partial/重复进度、source/matrix/log/status 漂移、CI 身份和 Summary 越界。均真实拒绝。GitHub Actions 明确禁止 `--synthetic`。同 owner 的 source/hash/进程收据不冒充第三方签名或独立 Issuer。

## Gate（封存时）

| Gate | 状态 | 边界 |
|---|---|---|
| G0 | PASS | 实际 HTTPS/HEAD/ACL/空占/来源和 durable receipt |
| A01 | PASS | 精确 1M+8A；旧 Router/matrix/tests/RPF-12/证据无改动 |
| A02 | PASS（验证器及模拟） | 固定 57/1232 与当前来源核对；真实新 hosted 全覆盖尚未执行 |
| A03 | PASS | 自洽 coverage blocker 仅允许 diagnostic continuation；异常拒绝 |
| A04 | PASS（本地控制） | 539 UNAVAILABLE 使 enforce 实际 exit1，不能以 ELIGIBLE 覆盖 |
| A05 | PASS | 原检查及 Router 全局结算保留；仅 Router 范围捕获真实 exit |
| A06 | PASS | 路径、原生事件、进程/来源/假绿负控；secret/Provider/旧私有根 IO 0 |
| A07 | PASS | 一次正式 11 tests，真实双状态与占用判定 0/1/2 |
| A08 | NOT_RUN | 待普通 commit/Push 和远端字节读回，最终聊天补证 |
| A09 | NOT_RUN | 新 repository checks、RPF12、Barrier、artifact 尚待实际 hosted 运行 |
| A10 | PASS | Task/Evidence/Stage 和内部 ELIGIBLE/上层 required blocker 分离 |

## 历史与剩余结算

旧 Run `41408665295` 已通过 GitHub step metadata 独立确认 completed/failure，repository checks 失败，Fresh Canonical Gate skipped。其 Router 的 **688 PASS/5 SKIP/539 UNAVAILABLE** 来自 Plan 带入的固定 hosted 取证；不是本轮本地执行。旧 RPF-84 coverage 仅引用原 path/SHA，未复制其 500k 方法账本。

本地完整 portable lane、RPF-60 九项、真实 Provider/SDK、业务 HTTP、Java/Docker/数据库实验均 **NOT_RUN/0**；没有读取或探测 Key。原 35 分钟内新增下游 hosted 时间/费用未知，不保证所有下游成功；不加 timeout、不额外 dispatch/rerun，不删失败检查。RPF-12 清理代码只删除自己的 tempfile tree，已检查其不会主动删除 Router/coverage 的 sibling 输出。

唯一外部未结算项是本次普通 Push 的 hosted 运行：应分别观察 Handoff、原下游检查、RPF-12 自身结论、coverage JSON Artifact 和最终 Barrier。上层 required 539 缺口不因任何 RPF-12 内部 `ELIGIBLE` 消失；最终 GitHub job 仍必须 failure。若前置原检查失败，下游 RPF-12 记 NOT_RUN，不追加业务修复来制造 PASS。

RPF-82 整体 PARTIAL、RPF-74/rev-4 PAUSED、RPF-81/rev-2 BLOCKED、RPF-78 A08 FAIL 不改。本切片完成不代表 EVIDENCE_ACCEPTED、STAGE_ADVANCED 或部署/发布授权。后续工作应逐类承担 539 项前提义务，不能直接豁免。

证据：[preflight](preflight-diagnostic.json)、[verification/source identity](verification-diagnostic.json)、[counterexamples](counterexamples.json)、[decision](decision.json)。
