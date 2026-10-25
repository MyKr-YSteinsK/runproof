# TASK_RESULT｜RPF-72 / rev-3

Plan ID: RPF-72

Revision: rev-3

Status: Complete

## CURRENT STATE

新版 LaunchSpec 已将实际启动时的净化环境冻结到当前私有 WAL/Manifest。离线验证使用历史原映射；同一新 N/F 原始 bytes 与 raw anchor 在 A/B 独立进程均 exit0。Source、聚焦测试、完整 Runtime、SDK 矩阵、负控和历史回归的真实结果见下表。A10 在文件生成时待最终回执提交，最后聊天补充准确 SHA 与 Git/API 双读；EVIDENCE_ACCEPTED、STAGE_ADVANCED 均由 Architect 决定，当前 PENDING。

## TARGET INTENT

Owner=`rpf-72-rev-3`，ABI=`rpf72r3-owner-source-v3`，ParentChild=`rpf72r3-parent-child-budget-v3`，LaunchSpec=`rpf72r3-launch-spec-v1`。Config250000、Order160000；11 slots / reachable474000 / global600000 / max_slot160000。实际 Driver 仍使用原 native CAPS，父级新版 Policy 在 CreateProcess 前严格授权实际 cfg 值。仅新双域本地 scripted 执行范围内 BUDGET_PARENT_CHILD_CONTRACT_EXECUTED=YES。

## PLANNING CONTEXT / Git / Source

Base `65617de848101afa8f632604f6491659778ad357`；分支 `codex/rpf-72-rev3-stable-launch-environment-replay`；源码提交 `6a014c4f3acb7a2b720f83710ca2f797c6580706`；source identity `cf9f468068d89d3ee02fa2d15b6d0388918e8739eb2054f24eec6166ad3ceaec`。84 源 raw/LF 闭包。13 个 execution/test/probe 属于冻结 Source，其余14项为事后证据报告。新 runner 的局部 PATH 排除了未展开的 `%JAVA_HOME%\bin`，没有读取 JAVA_HOME 或修改全局环境；原始 G0 诊断与纠正保留。Python3.12.13 / PydanticAI2.57.0 / OpenAI3.35.1、SDK RECORD/JAR pin 均保持。全部旧 tracked 源、旧证书、Driver/child/Guard、AGENTS/project/history 原字节保护。

旧 rev-2 的离线 verify 用当前 helper 重建环境，造成历史环境时间耦合；不知道旧值，也不反算。旧私有原件 UNAVAILABLE_NOT_READ；旧 A06/A09 FAIL 不改。纯内存 P0 对照只标 LEGACY_ENV_PROVENANCE_LIMITED_DIAGNOSTIC_ONLY，不代表旧证书复验。

## Gate

| Gate | Status | 证据 |
|---|---|---|
| G0 | PASS | Exact Base/branch/remote; 27 paths absent via local/index/Base/API; ignored owned non-reparse root; feature push has no deploy |
| R3-A01 | PASS | Independent v3 Owner/Source/Policy; source84 raw/LF closure, pinned SDK/JAR, old tracked bytes unchanged |
| R3-A02 | PASS | Actual native Popen strict capture, canonical private environment, cfg/SDK/PID/WAL binding, reject before CreateProcess |
| R3-A03 | PASS | Same original smoke and N/F bytes/anchors exit0 in independent A/B processes; no ambient environment reconstruction |
| R3-A04 | PASS | Eight original fixed-SDK thresholds; actual UsageLimits and single native WAL projection; orphan/UNKNOWN preserved |
| R3-A05 | PASS | New HTTP/H2 and SQLite N/F effects, independent Reader, four fault states, readonly reconcile and cleanup |
| R3-A06 | PASS | Actual raw-anchored semantic CLI attacks, deduplicated env cases, cfg controls, coupled reanchors and CLI0/2/3 |
| R3-A07 | PASS | 35 focused; standard complete unittest; exact discovery/outcome reconciliation, only two Docker class skips; snapshot bytes unchanged |
| R3-A08 | PASS | 24 original public/native verifiers plus R69 CLI0/2/3; old private evidence unavailable/not read |
| R3-A09 | PASS | WAL/process/authority cleanup and semantic replay; trusted Controller scope, no Issuer or child independent attestation |
| R3-A10 | NOT_RUN | At artifact generation: Source pushed and dual-read; final receipt commit/push and two Git/API HEAD/blob/diff readbacks supplied in final chat |

A10 的文件内状态是生成时事实；本文件不回填自己的 SHA、不 amend。最终 Git/API 交付结论见最后聊天。

## LaunchSpec 实测与稳定回放

`pge_r72r3_launch_spec.LaunchSpec.observe` 在实际 native Popen audit 时同步比较真实 tuple 与当时 helper 的 expected env；Windows None executable、完整 list2cmdline 字符串、flag 顺序、绝对 binary/child/cwd、固定 SHA、shell=False、OS/arch 全部严格核对。完整十字段原始字符串映射、canonical raw、聚合/逐键摘要和 Owner/Source/Policy/capsule/Run/domain/round 绑定只存当前私有 WAL/Manifest。PATH 只接受 G0 冻结目录身份，系统根、任务临时目录、telemetry/pyc 字段均有独立语义限制。

`LaunchSpec.check` 离线不调用 old._sdk_env 或当前 os.environ。它验证冻结的原始 canonical 映射、类型、字段、摘要、目录权限语义和 WAL 重复绑定。原 native canonical(cfg) 实际出站 bytes 与 CONFIG_VALIDATED→PROCESS_START→SERIALIZED_INPUT→READY/REPORT→RESULT_BOUND 按同 PID/Source/domain/WAL 关联。scoped ContextVar/profile 只作用于当前父线程与精确 native code/self 帧，成功和异常均恢复；没有 patch 原 Popen/Driver/child。

smoke A/B 各实际 SDK1、Java/DB/业务0；第三个拒绝 smoke 在 CreateProcess 前阻断，child PID 无，未结票保留。两份成功 smoke 各在 A/B 新进程验原 anchor。N/F 各在原环境与局部安全变量变化后的独立进程验证同一 bytes/raw SHA，均 exit0；变化仅 SYSTEMROOT/WINDIR 大小写和 trusted PATH 顺序，不改系统环境。真正新启动的恶意 env/key/argv/cwd/pin 仍被拒绝。

## SDK / 预算 / native WAL

| Domain | Case | PID | synthetic total hint | SDK result |
|---|---|---:|---:|---|
| config-java-http | limit-equal | 11784 | 250000 | COMPLETED |
| config-java-http | legal-high | 19836 | 84600 | COMPLETED |
| config-java-http | limit-minus-one | 5820 | 249999 | COMPLETED |
| config-java-http | limit-plus-one | 16744 | 250001 | UsageLimitExceeded |
| order-sqlite | limit-equal | 25608 | 160000 | COMPLETED |
| order-sqlite | legal-high | 18880 | 54580 | COMPLETED |
| order-sqlite | limit-minus-one | 12476 | 159999 | COMPLETED |
| order-sqlite | limit-plus-one | 23620 | 160001 | UsageLimitExceeded |

legal-high 累计超过35000且输入上界加保守512输出仍在 slot 内。minus/equal/plus 末次 hint 刻意超单槽/输入上界，仅检验 SDK 累计阈值，不是合法付费预约；limit+1 实际 UsageLimitExceeded，失败 hint 不当作最终可信 RunUsage。成功为 SYNTHETIC_VALIDATED_USAGE；真实 Provider 请求/token/费用均0。

BudgetLedger 代理同一份 native fsynced WAL：CHECK/GRANTED→RESERVE/RESULT→CONFIRMED/SETTLED，逐票 native replay 一致，没有 shadow 账户、回收票、补账或重造额度。纯 Provider component 的474000/600000/11槽为合成演算；历史价格仅 HISTORICAL_PRICE_REFERENCE / NOT_INVOICE。

## 新 N/F 本地业务证据

N `rpf72r3-8497e32744cf4bd2`：manifest raw `a3dd105db3d2a522d25d98bf1f18c2251d3b8104c62d2923093f82dc42950ff9`；WAL raw `059b4535c758276be6cb62bbd9f9f1e202e00ab1dcf6e587def3a0a86bf3d8eb`；476.15s。

F `rpf72r3-b157f0018026bef8`：manifest raw `f72ab22b1d768f8e747c96557371bdf66768a4b44c0f7c28bacb6bafc3308f9d`；WAL raw `2b0e069331d9ed979f65ee580c13ff3bff4c65832442900ef44b3ea894a1db08`；495.19s。

每场景 JVM1、SDK/Host各2、配置真实 HTTP POST2、SQLite 虚拟2500 minor全额退款1、scripted Explorer2；Authority N=4、F=5。配置 Reader GET/history 验证 ABSENT→v1→v2，SQLite mode=ro Reader 验证唯一收据。N 两域四态全 false；F 提交后实际抑制返回，planned/triggered/observed/agent_exposed 两域全 true，仅只读 inspect/reconcile，不重复写。独立验证、cleanup、反馈冻结后才进入另一域。正式 N1/F1、纠错0、SDK矩阵1、smoke3；Runtime unit fixture 配额另列，物理路径全部在当前 snapshot。

## 测试 / CLI / 历史

focused 实际35项通过，wall 378.50s。辅助 receipt 原 CRLF 正则误记 summary=false，原始日志和 receipt 未改；独立 focused-summary-review 核对实际 Ran35/OK。parser 在 Source freeze 前已修正。

完整 Runtime 仅1次，标准 unittest discover、单一 source-identical snapshot，未过滤、拆分、改测试、动态 monkeypatch 或复用缓存 PASS。原始日志最终总结为：

```text
Ran 635 tests in 3562.118s
OK (skipped=2)
```

exit=0，errors=0、failures=0，receipt wall 3566.05s。discovery=640，实际运行=635；两个原 Docker class-level unavailable skip 覆盖5个方法，标准 unittest 不将它们计入 testsRun。实际完成 ID 加这5个方法精确 multiset 还原640项；没有用进度行数造汇总。实际 snapshot 的895个公开复制文件在结束后逐字节比对一致，冻结 Source 未漂移。首次成功后未再跑第二次。parent3.12 full/HostedCI 均 NOT_RUN。

本轮实际 Manifest CLI 负控200，budget/env 165，env专项去重40；纯 cfg60、LaunchSpec-env42另计。4项深层攻击修复 env 聚合/逐键/raw/specSHA、prelaunch/sdk/result/domain 副本和 WAL 全链/raw anchor 后，仍因 relative PATH、foreign HOME、Config/Order SDK usage 语义拒绝。无 TEST_INVALID/平台错误冒充拒绝。CLI 无 anchor→2、错 anchor→3；正确原件 A/B→0。24个历史公开原生入口与 R69 CLI0/2/3 全部保持原 anchor/Verifier；R70/71/rev1/rev2 私有原件 UNAVAILABLE_NOT_READ。

所有命令 argv/cwd/PID/start/elapsed/exit/log SHA/source前后见 verification-diagnostic；完整清单、实际 ID 和 skip 映射见 runtime-diagnostic。报告辅助脚本一次无效换行参数写入导致私有未执行文件被截断，已在生成前重建；冻结执行 Source/test/probe 与证据日志不受影响，没有为此重跑实验。

## Key / 资源 / 清理边界

HOST_PROVIDER_KEY_READ=0、HOST_BUSINESS_KEY_READ=0、CHILD_KEY_PRESENT=false、EXTERNAL_DISCLOSURE=0。原固定 child 的两处缺失 getter 保留为 SANITIZED_CHILD_ABSENCE_PROBE；直接取证 pipeline completed child12次，两触点各至少12次，非总执行次数。library/legacy/full/focused fixture getter 总数 NOT_INSTRUMENTED；ALL_KEY_LOOKUPS_ZERO=FALSE/NOT_PROVEN。Java 内部新建模拟 loopback 鉴权票据不继承到 SDK child。公开数据只有摘要和断言，不含完整 PATH/HOME/原始环境或真实 Key。

晚次主路径16个 PID/port检查 PASS；创建时间/SID 未捕获则 UNAVAILABLE，不伪造、不杀陌生/复用 PID。physical symlink=UNAVAILABLE，WinError=1314；真实 junction 已创建并拒绝。未改 ACL/power policy，未清旧根/Run/WAL，docs/reviews 只允许顶层 status 自然提示。无 PR/force/mainmerge/tag/release/deploy/CI dispatch/contest。

## VERIFIED_FINDINGS

历史环境时间耦合由版本化冻结映射替代。源码定位：launch_spec.observe/check、sdk_contract._audit/_profile/verify_proof、budget_ledger._perform。支持证据是实际 native Popen、原 cfg 出站字节、独立进程 A/B 同原件、单 WAL 与联动反例；Source raw/LF、SDK/JAR pins见 source-identity-map。旧 rev-2 的 FAIL 保持原状。

## CODEX_ENGINEERING_JUDGMENT

机制是在准入时记录历史，回放时验证历史和独立语义。可信本地 Windows Controller 范围内置信度 HIGH。支持：原件/anchor不变的 A/B exit0、实际实时准入及重锚反例。限制：无外部 Issuer 签名、child 未回显 cfg/capsule，不能证明任意共同重签的本地自陈数据不可伪造。最便宜鉴别实验是后续获授权的 versioned Launch factory 对本次冻结样本做差异回归，不改旧 Guard 或重标旧证据。

## ALTERNATIVE_PATHS_AND_TRADEOFFS

| 路线 | 安全与历史 | 成本与回归 |
|---|---|---|
| task-owned hook（当前） | 原 Driver/child/Guard不变，严格实际准入 | 最小范围；仍有代码帧/profile耦合及重复wrapper |
| versioned Launch factory | 显式冻结 API，保留旧证据路由 | 新权限/ABI设计与共享回归预算 |
| 新 child capsule echo | 新路径和 Guard/pin 审查；echo本身非签名 | 最大 SDK/审核面，当前未授权 |

## NEXT_DECISION_RECOMMENDATION

首选 Architect 先核实本回执，再决定证据接受与阶段推进。若共享生命周期或调用帧耦合成为已证维护障碍，下一 Plan 优先显式 versioned LaunchSpec/factory 薄接口；切换需新白名单、兼容矩阵和有限回归预算。真实 Provider/Key/费用/故障因果实验须独立授权；不自动创建 RPF-73。

## POTENTIAL_GENERALIZATION_DEBT

已证：84源闭包和重复 task-owned wrapper；历史 env 成为显式 ABI；Controller 有进程/业务权限，非 OS sandbox；profile/audit 绑定 native 代码帧和 SDK pin。仅推测：源码扫描/profile开销可能影响效率，本轮未 profiling 或性能优化，不宣称性能提升。

LEGACY_R72R2_PRIVATE_MANIFEST_VERIFIED=UNAVAILABLE；CHILD_INDEPENDENT_ATTESTATION=NOT_ESTABLISHED；REAL_PROVIDER_THIS_TASK/REAL_EXPLORER_AUTONOMY_THIS_TASK=NOT_RUN；SDK_GUARD_MIGRATED/FULL_COMMON_CORE_MIGRATED=NO；ISSUER/L2=NOT_ESTABLISHED；MAIN_MERGED/DEPLOYED=NO。TASK_COMPLETE 为 Codex 自报，Architect 接受/推进仍 PENDING。

## 27项 CREATE_ONLY

- `runtime/runproof_runtime/effectwitness/pge_r72r3_contracts.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r3_owner_source.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r3_capability.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r3_budget_policy.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r3_budget_ledger.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r3_launch_spec.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r3_sdk_contract.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r3_ports.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r3_session.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r3_verify.py`
- `runtime/runproof_runtime/effectwitness/pge_r72r3_migration.py`
- `runtime/tests/test_effectwitness_pge_r72r3.py`
- `spikes/rpf-72/rev-3/probe.py`
- `spikes/rpf-72/rev-3/README.md`
- `spikes/rpf-72/rev-3/RESULT.md`
- `spikes/rpf-72/rev-3/preflight-diagnostic.json`
- `spikes/rpf-72/rev-3/verification-diagnostic.json`
- `spikes/rpf-72/rev-3/parent-child-contract-matrix.json`
- `spikes/rpf-72/rev-3/budget-negative-controls.json`
- `spikes/rpf-72/rev-3/history-regression.json`
- `spikes/rpf-72/rev-3/source-identity-map.json`
- `spikes/rpf-72/rev-3/architecture-decision.json`
- `spikes/rpf-72/rev-3/capability-assessment.json`
- `spikes/rpf-72/rev-3/launch-environment-diagnostic.json`
- `spikes/rpf-72/rev-3/runtime-diagnostic.json`
- `spikes/rpf-72/rev-3/key-boundary-diagnostic.json`
- `spikes/rpf-72/rev-3/positive-replay-diagnostic.json`

最终准确回执 SHA 和可访问 GitHub URL 由最后聊天双读补全；私有 D 盘路径不是 Architect 可访问的远端 URL。
