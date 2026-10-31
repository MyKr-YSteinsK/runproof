# TASK_RESULT — RPF-82/rev-3

**Status: Partial**。G0、修复前来源保全和 helper 分类修正已有实际证据；冻结后的 RPF-60 九项正式验证在原有 300 秒模块上限处超时。按 Plan §4–5 停止，保持失败来源身份，不提高预算、不重跑、不修改冻结代码。未进入完整分类遍历、commit、push 或 hosted CI。RPF-82 整体仍 PARTIAL。

## 基线与 G0

- 现有 main 单工作树，Base/当前 HEAD：`531338ad88e9ba8e6d4d4b271b10fbe7d161d46e`。本地 `origin/main` 和 authenticated Git Schannel `sslVerify=true ls-remote` 均真实返回固定 Base。
- G0 确认继承现场正好为 2 个 tracked 修改、9 个新增 rev-2 文件，index 无暂存内容；未枚举其它未跟踪文件或 docs/reviews。workflow 只保留 rev-2 原入口替换，权限、trigger、job、其它 checks、Gate 和 artifact 不变。
- 逐项 ACL 子进程显式传播异常与 exit，根与 `.local` 均 exit 0。读取中文文本第一次遇到 locale GBK 解码错误，发生在任何写入前；改为明确 UTF-8 并完整重跑只读 G0，未将错误追认为 PASS。
- 新 `.local/rpf-82-rev-3-g0-receipt.json` 先 stdout、exclusive-create、flush/fsync，再创建唯一新 owner `.local/rpf-82-rev-3-classifier-closure/`。文件 fsync 完成，Windows 标准库目录 fsync UNAVAILABLE。旧 Attempt-01/02 收据与根未修改或复用；仅读取获准的 Attempt-02 已知 receipt 作来源核验。

## 原失败来源保全

修复前立即将三份 CI 输入按原始字节 exclusive-create 复制至本目录 `pre-repair-sources/`。raw SHA-256：

| 快照 | raw SHA-256 |
|---|---|
| run-runtime-contract-tests.py | `5a6cb4f8e02104a3342e9f1ece5b45a94fe463a6e93e378bccefe409302f9d21` |
| runtime-contract-test-matrix.json | `1aae16bb743baf3a9eaeda674b15a9a93e0f0601b87d1b1373ae90cd2673cc1f` |
| test_run_runtime_contract_tests.py | `8751fdb1443d65d07a8ddc86243398e9ffb1a266f6770446dd7156090ddde3c8` |

rev-2 RESULT raw SHA 为 `31f8c6d76a0ec6108c1842d0b4d64c9a7bfc2f8d81eae38433510c40754bf644`，原完整 classification-ledger raw SHA 为 `21609e8fbadbfce0363d04bb3144c1f9cc61559cb961b32ab9bff3c3ec2dc0a0`。六份 rev-2 报告和两个继承 tracked 文件均未更改。矩阵和单测快照含 CRLF，raw 与 LF hash 不混用；未通过 Git 换行转换声称 raw 一致。快照只作审查，没有导入或执行，也没有公开任何宿主绝对路径或凭据。

## 精确修正

原 rev-2 账本两个 ERROR 是：

1. `test_effectwitness_pge_r81.ConformanceTests.test_injected_fsync_failure_stop`
2. `test_effectwitness_pge_r81.ConformanceTests.test_injected_write_failure_stop`

并非 Plan 中作为调查线索提出的 torn/missing-tail 方法；后两项原本已列为不可运行。

静态源码链为 test → `persist`（test 源码 66–70）→ `Host(..., True)`（barrier 9–10）→ `Journal(..., create=True)`（journal 8–10）→ `c.case_dir`（contracts 57–58）→ 历史 `WORK/sessions/unit-...` 路径 → `self.root.mkdir(...)`。此前 classifier 只识别直接构造入口，遗漏 `self.persist` 的依赖。旧 ERROR 的 ID、原 route、诊断来自原公开 ledger；本轮未重新打开旧私有日志取得动态 PID/path 值，更没有重放旧失败。

仅两项 exact selector 新增 `LEGACY_OWNER_ROOT`，reason 为 `HISTORICAL_OWNER_ROOT_NOT_AUTHORIZED`。这是会创建未授权历史 owner 的条件，不是虚构缺失 SDK/receipt 的替代说明。matrix v2 增加受审查的 helper registry，绑定 contracts/journal/barrier 来源，静态遍历本类 helper，拒绝未知调用、递归/重复 helper、未登记方法、owner 前提被伪装为 approved portable 和依赖漂移；九个实际 portable RPF-81 方法仍保留，其他既有 route 不变。

冻结的 RPF-60 harness 只允许旧 rev-2/CI root，因此新 Router 在自身源码内提供临时 test-only owner 适配，并把完全匹配的原竞争子进程命令转为当前 Python 的固定 `--r60-race` CLI。保留两个进程、原 plan/path/owner、原 Ledger/reservation 操作和全部断言；不执行输入脚本文本，不修改原测试文件或业务 Runtime，不复用旧根。

## 验证、冻结与停止点

- 冻结前 Router 单测先 31/31、补充伪造 owner 前提负控后 32/32；RPF-60 新 owner 的竞争/deadline 两项 2/2 PASS。
- AST/compile（2 个当前 Python CI 文件及继承 RPF-60 测试，无 pycache）、strict JSON/schema、duplicate/nonfinite 负控、真实 PyYAML、CLI help、helper closure 与 diff check 实际完成。来源在公开 verification diagnostic 中先记录，再开始正式测试。
- 冻结后 Router 正式单测 **32/32 PASS**，保留 rev-2 原有 22 个测试 ID。新增隐藏 WORK mutation、benign helper、未知/递归/重复 helper、新方法、owner mask/依赖漂移、pre-mkdir/open audit 拒绝和实际 child exit 1 反例。合成审计事件不调用旧路径的 mkdir/open；实际旧根 syscall 为 0。
- 其中正式 RPF-75 self-denial/sibling 控制通过：原 hook 拒绝 process/socket 事件，实际 subprocess 被拒；新兄弟进程完成 5 字节 127.0.0.1 回环和当前 Python 子进程。**原 RPF-75 的 87 项完整聚焦测试尚未运行**，不能由该控制或历史 rev-2 通过替代。
- 正式 RPF-60 模块在 **300.026728 秒**返回 exit 1、timeout=true、truncated=false，日志 SHA 为 `fe4ea87ed4d79da79b2ddb0e584fb8ab38410c24791534be5331dbabe7409981`。原 9 个发现 ID 中，前 7 项实际 addSuccess，`test_rehashed_semantic_controls_all_sequences` STARTED 后被限时终止，`test_unknown_write_lock_torn_restart_and_no_refund` 尚未到达。
- 因无最终 unittest 结算，记录 **7 PASS、1 ERROR（模块超时）、1 NOT_RUN**，没有伪造完整 testsRun。重锚方法没有返回断言 FAIL；当前不能确认本机耗时变化的根因，未将其称为已证明的 flaky/性能缺陷。rev-2 历史 9/9、244.694 秒也不能替代本轮正式验收。
- 冻结后未再修改三个 CI 文件、两个继承 tracked 文件或预算，没有再跑这组方法；新代码、旧失败快照和原报告身份均保留。由于正式聚焦未过，唯一完整 inventory/classification pass **NOT_RUN**。

## 覆盖与 Gate

rev-2 1232 IDs = 688 PASS + 5 原生 SKIP + 537 UNAVAILABLE + 2 ERROR 是历史本机结果，仍原样保存。1232 与旧 hosted testsRun 1118 的 114 差额解释不变：RPF67 27、RPF68 15、RPF78 frozen 67、Docker 2、RPF05 3 个方法被类级 setup/error/skip 挡住。

rev-3 的规则差异静态仅为原两个 ERROR 的 route 更正：PORTABLE -2、LEGACY_OWNER_ROOT +2、全部 required=true；不能把算术映射的 539 UNAVAILABLE 当作本轮新发现/新执行。当前仅 RPF-60 模块有 9 个实际 fresh discovered IDs，完整 57 模块本轮发现尚未运行。其他方法沿用原执行责任，不计为本轮 PASS。Windows basename 与 stdlib 两项源码、期望、PORTABLE route 均未改，本轮方法体 NOT_RUN，原 hosted Linux FAIL 仍待后续单独修复。

| Gate | 实际状态 | 证据或缺口 |
|---|---|---|
| G0 | PASS | 有效新收据；固定 Base 与继承现场精确核验 |
| A01 | PASS | 三份 raw 快照、六份旧报告及继承文件身份保全 |
| A02 | PASS | 实际两个 ERROR 的静态 helper 链及 unknown helper 负控通过 |
| A03 | NOT_RUN | 正式聚焦后停止，未进行本轮完整发现遍历 |
| A04 | PASS | 两项 exact owner-root 更正；static/source-backed 控制通过，无广泛降级 |
| A05 | FAIL | Router 32/32；RPF60 模块超时，九项未全结算；原 RPF75 聚焦 NOT_RUN |
| A06 | PASS | 已执行安全负控通过，无旧根 IO/SDK/Provider，冻结失败后停止 |
| A07 | NOT_RUN | 未新 push，未触发 hosted CI，不能记 canonical PASS |
| A08 | NOT_RUN | A05 未通过，不满足交付条件，未 commit/push |
| A09 | PASS | rev-2 PARTIAL/原 ERROR 保留，所有历史暂停与产品缺口不变 |

## 交付与建议

全部新源码和本目录证据仍在本地工作树；HEAD 未变，不声称 Architect 已读本地路径或 GitHub 已接受本次修改。原 hosted run 40920947296 FAILED；本轮 Actions/Canonical Gate NOT_RUN。Provider、真实 SDK、业务写、Docker/JVM、部署/发布均 0；CPU/RAM/IO/资金未测，UNAVAILABLE。

后续如授权新的冻结候选，建议先在冻结前定位该重锚矩阵的实际耗时，评估在既有总预算内按方法分派，保留失败身份并避免整个模块共享一个不够用的 deadline。这是后续工程建议，本轮没有提高上限、删减矩阵或启动新 RPF 编号。
