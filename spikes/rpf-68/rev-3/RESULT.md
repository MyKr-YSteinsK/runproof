# TASK_RESULT — RPF-68 rev-3

Status: Complete

Base: `461a0caf12ccd083ae4af2d49b57d8d48816a3d4`；分支：`codex/rpf-68-rev3-capacity-budget-live-cross-domain`；remote：`https://github.com/MyKr-YSteinsK/runproof.git`。
冻结源码 LF digest：`68bbfe44ccde9e5c20f8acaa6ea6660285e2e7ecdc145a556fc6e856887a3a17`；Verifier：`rpf68-cross-domain-verifier-v3`。源码提交及Git/API双读见 verification-diagnostic.json 的git_delivery；本报告回执提交SHA由最终聊天补报，不自引用回填。

## 本轮实现与授权

完成版本化逐槽预算、600k永久预约池、15元价格守卫、正式准入、source-aware usage、原样联合协议容量与独立反馈/Witness核验。用户明确批准额外修改 pge_r68_sdk_child.py 的 token 预算配置接口；父级传入 Config250000/Order160000。213行 guard 前缀、固定 SDK 安装、工具和业务实现保持原字节。

## Gate 结果

| Gate | 状态 | 依据 |
|---|---|---|
| G0 | PASS | 10 create-only paths absent in Base, index, filesystem and GitHub API; user approved one SDK-child extension |
| R3-A01 | PASS | Versioned context/source/registry and role-domain binding |
| R3-A02 | PASS | 474000 reachable permanent tokens, global 600000, max slot 160000, cost guard 15000000 micro-CNY |
| R3-A03 | PASS | Six actual fixed-SDK legal joint-envelope cases, finite coverage |
| R3-A04 | PASS | Final-source focused/full, 161 synthetic reanchored negatives, 21 historical/public entries and RPF67 anchor; Docker skips UNAVAILABLE |
| R3-A05 | PASS | Source/helper freeze, metadata1/cold2, OS cleanup and official price admission |
| R3-A06 | PASS | One admitted paid session; exact counts and unknown tickets in session summary |
| R3-A07 | PASS | Two independent business authorities and first-domain verified feedback consumed by Explorer2 |
| R3-A08 | PASS | Original real witness CLI 0/2/3 and at least 30 semantic reanchored negatives |
| R3-A09 | PASS | Task-only PID/port OS readback; historical failure retained; no protected-directory access |
| R3-A10 | PASS | Source commit delivered with Git/API SHA equality and unchanged main/parent; this report receipt commit identity is supplied in final chat without self-reference |

Docker 原2项 skip 为 UNAVAILABLE；Windows 原生3.12全量Runtime未运行；实际固定 SDK 子进程为3.12.13。Hosted CI 未执行，本分支 push 不触发 main-only Release Gate。

## 容量与费用账本

最终 CAPS：`{'EXPLORER': (32000,), 'config-java-http': (10000, 30000, 50000, 70000, 90000), 'order-sqlite': (10000, 30000, 50000, 70000)}`；全路径预约 474000，全局600000，每槽<=160000。输出128/256/512、framing512不变。Explorer由建议8000增至32000，以保留完整 VerifiedFeedback。所有 Provider 票永久占用，未知结果不回收。
protocol-budget-diagnostic.json 保存全部新旧容量矩阵：首轮5过1失败，固定 SDK 在累计66092合成token触发硬编码35000；经明确扩权修复后重跑。合成 usage 只用于合法协议容量检验，不是 Provider 测量。
正式会话：`PASS`；实际账本见 session-summary.json。官方核价绑定 Admission，所有金额仅 guard estimate，实际账单 NOT_QUERIED。

本轮真实会话耗时52.728秒，Provider9次；严格usage为输入5826、输出580，共6406 token。永久预约314000 token，预约费用上界估计¥0.107379；按已知usage计算的费用守卫估计¥0.036657，均不是实际账单。Config实际POST2次、HTTP8次、health1次；Order仅一次受控2500 minor退款；Authority读4次、JVM1、SDK/Host各2。所有票已结算，无Unknown/blocked；未追加正式会话。

| 角色/域 | 序号 | 输入上界 | 输出上限 | 永久预约槽 | 实际input/output |
|---|---:|---:|---:|---:|---:|
| EXPLORER/config-java-http | 1 | 791 | 128 | 32000 | 349/36 |
| TARGET/config-java-http | 1 | 1516 | 256 | 10000 | 550/31 |
| TARGET/config-java-http | 2 | 1386 | 256 | 30000 | 599/58 |
| TARGET/config-java-http | 3 | 1488 | 256 | 50000 | 687/80 |
| TARGET/config-java-http | 4 | 1634 | 512 | 70000 | 797/91 |
| EXPLORER/order-sqlite | 1 | 1578 | 128 | 32000 | 608/39 |
| TARGET/order-sqlite | 1 | 1806 | 256 | 10000 | 604/66 |
| TARGET/order-sqlite | 2 | 1552 | 256 | 30000 | 715/133 |
| TARGET/order-sqlite | 3 | 1871 | 512 | 50000 | 917/46 |

## 业务事实与证据边界

本轮真实Explorer分别选择`normal`和`normal-full-refund`，两域fault四态均为false；真实会话未激活故障，故障路径证据限于免费合成SDK/真实本地业务正控。本轮一次真实共享会话完成两个真实 Explorer 和两个真实 Target。Config 使用 task-owned Java/H2 HTTP服务；Order 为独立SQLite Authority。第一域独立读回、清理与 DomainVerified 之后冻结反馈，第二轮 Explorer 请求绑定该反馈。真实证书保留同一 Context/物理WAL/Source lineage；详见 session-summary.json 的 round/trace/fault/业务Oracle和全部Provider usage。
真实重锚负控共58类：冻结脚本44类，加独立CLI补验14类，覆盖Provider请求/票/价、第二域反馈时序、UNKNOWN、Port/Oracle等；原CLI0/无锚2/错锚3全部通过。证书原始SHA：`5b97d3e0a4c9c3d2492b5aa49af00ebe1e553b24b0f9725087180510e55dd9e9`。

本轮没有建立跨域可比 L2 信息增益、因果归因、external issuer、独立复现、第三域或 Web集成；历史RPF57不能充作本轮统计证明。故障四态按实际 fault.planned/triggered/observed/agent_exposed 记录，不能以候选名替代。

## 保护与清理

docs/reviews/ 未进入、未读取、未暂存；旧历史证书、Source maps、旧.local现场保持。所有本轮失败证据保留在.local/rpf-68-rev-3/；最初失败JVM晚观测UNAVAILABLE，后续cleanup-prior.json实际确认原PID不存在且端口关闭，原观测不覆盖。
最终OS清理：`PASS`。只检查本轮记录PID/端口；不终止陌生PID。Provider Key不进入child、Source或普通export，child短期权限令牌仅保留ignored运行现场；父级引用在finally清除。
无PR、merge、force、tag、release、部署、workflow dispatch或比赛提交。main与父分支最终身份需由交付回执核验。

## VERIFIED_FINDINGS

### F1 · CURRENT_STATE

`runtime/runproof_runtime/effectwitness/pge_r68_driver.py:49`：8192字节合法JSON空白会由原生SDK原样回注；制表符与NUL的转义使canonical suffix继续增大。
证据：protocol-budget-diagnostic.json cases arguments8192/recursive-upper。支持：联合容量必须同时覆盖序列化后缀和上一可信prompt。 限制：不能推断真实tokenizer分布。

### F2 · CURRENT_STATE

`runtime/runproof_runtime/effectwitness/pge_r68_sdk_child.py:292`：原生SDK隐藏的35000累计上限，在合成usage累计66092时拒绝了父级已准入的合法轨迹。
证据：Initial matrix FAIL retained, scope-extension approval, final rerun。支持：父级和子进程的累计预算必须来自同一冻结表。 限制：仅调整预算配置；SDK安装和guard前缀仍保持固定身份。

### F3 · CURRENT_STATE

`runtime/runproof_runtime/effectwitness/pge_r68_contracts.py:8`：冻结前将每个Explorer槽由8000增至32000，以保留完整verified-feedback形状。
证据：Final slots sum to 474000 within 600000; actual SDK matrix。支持：在输出上限不变时为两个角色提供足够输入容量。 限制：预约容量不代表实际usage或账单。

### F4 · CURRENT_STATE

`runtime/runproof_runtime/effectwitness/pge_r68_context.py:39`：真实业务准备和账本写入要求真实Admission，未准入的直接入口被拒绝。
证据：Focused test plus synthetic semantic controls。支持：cold/synthetic路径不能静默升级为真实业务trial。 限制：本任务Python边界不能证明操作系统安全沙箱。

### F5 · CURRENT_STATE

`runtime/runproof_runtime/effectwitness/pge_r68_session.py:10`：Session先核验并清理Config，再冻结反馈并调用Explorer2；Order使用独立Authority。
证据：session-summary.json and conditional cross-domain-witness.json。支持：真实门禁通过时，同一WAL关联两个域。 限制：独立复现、因果L2增益与外部issuer仍未建立。

### F6 · TARGET_INTENT

`runtime/runproof_runtime/effectwitness/pge_r68_context.py:9`：task-owned owner、Context和传递Source闭包仍使协议演进与历史身份耦合。
证据：source map raw/LF and immutable historical certificate regressions。支持：后续可在构造器与Source Map接缝验证版本化公共ABI。 限制：本轮未授权公共核心抽取或第三域实现。

## CODEX_ENGINEERING_JUDGMENT

### J1

- observation: rev1的2706与rev2的2811/3317/9623均超过原窄输入槽。
- root_cause_hypothesis: 协议回注容量与允许的原始响应字段长度没有联合预算。
- supporting_evidence: Six joint fixed-SDK tests; previous-prompt + canonical-suffix +512 proof.
- contrary_evidence_unknown: 真实Provider可能返回更短字符串；尚未枚举所有Unicode历史。
- risk_impact: 提交后的平台拒绝可能中断安全对账。
- confidence: HIGH for these counterexamples; bounded for generalization
- cheap_discriminating_test: 保持相同SDK与合法响应，在各阶段合法范围扫描上一可信prompt；不调用付费Provider。

### J2

- observation: 父级600k授权没有移除原生SDK的35k累计限制。
- root_cause_hypothesis: 同一预算策略在父级WAL和SDK进程配置中重复维护。
- supporting_evidence: 66092 cumulative synthetic usage raised UsageLimitExceeded; user authorized the exact child seam.
- contrary_evidence_unknown: 旧正常fixture低于隐藏上限，因此先前通过未覆盖此条件。
- risk_impact: 仅增大父级槽会留下第二个独立停止条件。
- confidence: HIGH
- cheap_discriminating_test: 使用recursive-upper fixture，将原生RunUsage累计与冻结分域槽总和比较。

### J3

- observation: SourceSynthetic负控与真实Provider轨迹支持不同层级的证据主张。
- root_cause_hypothesis: 将usage confidence字符串本身当证据会混淆信任边界。
- supporting_evidence: Fixture source gating, unique admission WAL event, actual Provider tickets and source-aware verifier.
- contrary_evidence_unknown: 尚无独立复现或外部issuer。
- risk_impact: 将测试误标为真实发现会夸大竞赛证据。
- confidence: HIGH for evidence classification
- cheap_discriminating_test: 对synthetic改为real的Context变异重新锚定，在零付费条件下确认拒绝。

### J4

- observation: 初次JVM晚观测为UNAVAILABLE；后续OS读回确认原PID不存在且任务端口关闭。
- root_cause_hypothesis: Windows进程生命周期的短暂观测可能滞后于子进程清理。
- supporting_evidence: cleanup-prior.json plus preserved initial late-envelope receipt.
- contrary_evidence_unknown: 初次不可用观测没有捕获完整进程创建遥测。
- risk_impact: 清理结论必须保留不确定性，直至后续真实观测将其消解。
- confidence: MEDIUM for cause; HIGH for later absence
- cheap_discriminating_test: 对记录的任务PID读取GetExitCodeProcess及创建时间；不终止无关复用PID。

## ALTERNATIVE_PATHS_AND_TRADEOFFS

### A · 继续维护task-owned SharedSession

修改接缝：`pge_r68_session.SharedSession, pge_r68_contracts.CAPS, pge_r68_sdk_child.main`。复杂度：当前低复杂度；重复策略随revision增加。历史成本：Keep old verifier and identity maps immutable; new source identity per revision。最坏失败：Another hidden parent/child policy divergence blocks after commit。时机：适合当前双域证据收口；本轮不开展广泛重构。

### B · 新建版本化公共Owner/Source/Budget/Verifier/SDK guard核心

修改接缝：`pge_r68_context.Context and sources, pge_r68_budget.Ledger/replay, pge_domain_port.py, pge_r68_driver.Driver, pge_r68_sdk_child._guard/main`。复杂度：中高复杂度；须明确构造器ABI、Source闭包和安全责任。历史成本：Dual verifier/source tracks; do not remap old certificates。最坏失败：Common abstraction broadens authority or makes old witness unverifiable。时机：建议Architect审查后单独开展零Provider兼容性Spike。

### C · Web/MCP/第三域能力验证

修改接缝：`lab_cross_domain_contracts.py, lab_cross_domain_verify.py, pge_r68_session.REGISTRY, domain-specific future Port`。复杂度：集成复杂度高；需要独立Authority和新的输入/工具合同。历史成本：New evidence family and explicit cross-version navigation。最坏失败：Surface demo hides missing independent effects, issuer or feedback lineage。时机：待B证明ABI保持权限边界且第三域决定明确后再做。

## NEXT_DECISION_RECOMMENDATION

建议先由Architect审查本轮证据与缺口，再单独授权无Provider的公共ABI兼容性Spike，证明owner/source/budget/guard责任不扩权、旧证书不漂移后，决定第三域与Web。反对在一次任务内同时大规模抽公共guard并接入第三域live；切换条件为独立白名单、版本化ABI、旧锚回归与新独立Authority明确。未创建或执行RPF-69。

## POTENTIAL_GENERALIZATION_DEBT

- PROVEN_DEFECT：已证子进程隐藏累计35000上限；仅在明确授权的参数接缝修复。
- GUARD_COPY：213行task-owned SDK guard保持原字节；公共guard需要独立授权及负控证明。
- OWNER_SOURCE_COUPLING：Context构造器绑定当前raw/LF Source闭包与owner；泛化需要版本化不可变capsule ABI。
- THIRD_DOMAIN_REGISTRY：TOOLS/args_for/REGISTRY及序号/域选择仍是具体双域合同。
- OBSERVABILITY_GAP：账单未查询；不导出private reasoning；无外部issuer、独立复现或广泛Unicode/tokenizer证明。
- HISTORICAL_SOURCE_DUAL_TRACK：历史Witness保留原Source/Verifier；新helper或Source身份不得覆盖它们。

能力被实现和一次运行通过不等于 EVIDENCE_ACCEPTED 或 STAGE_ADVANCED；这两项保留给Architect/用户决策。
