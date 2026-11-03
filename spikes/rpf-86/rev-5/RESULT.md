# TASK_RESULT — RPF-86/rev-5

Status: PARTIAL

Decision: STRICT_ADMISSION_ACTIVATED（本地 A；交付及 hosted 在封存时尚未执行）

Base/main: `d6304828fc223ce7aff743e3b786780d7fc3a925`。本地实施及严格准入已通过；A08/A09 为 NOT_RUN_AT_SEAL，未来普通 Push/完整 SHA/远端及 hosted 结论仅最终聊天补，不 amend。

## 因果与修复

一次真正执行目标的 import-only 探针出现两次 READ_SCOPE_DENIED，分别严格匹配 `cache_from_source` 对固定 RPF55/RPF53 `probe.py` 的候选。Python 3.14.6、tag=cpython-314、-B=true、baseline pycache_prefix=None。只做许可源码推导的内存词法比较；未读取/stat/list 旧 cache，未导出未授权路径。静态调用链是 `pge_dual_config_port.py:14–15`、`spikes/rpf-55/probe.py:28–30`。H_CACHE 对本次新运行成立，不追认成 rev2/rev4 旧私有事件重现。

修复仅在 harness：每个新 native child 把 `sys.pycache_prefix` 设到自身独占 fresh pycache 根并继续 -B，不开放旧 pyc，不增加 read roots，不改 Runtime/原方法/probe，也不 patch 全局 loader。真实控制证明两个源码 pin 不变、SourceFileLoader 不变、旧缓存 open 仍拒绝、新 pycache 无 pyc。错误 tag/目标/大小写/穿越、source pin、prefix escape/reparse、假 journal 与 artifact 泄密负控均通过。

最初一次子进程在 target import 前因缺少显式 `importlib.util` 而 AttributeError；只有 INIT，Guard 尚未安装、target import=0。原 stdout/hash/receipt/source 全部保留。补齐标准库显式 import 后，新目录执行唯一真正的归因 probe，未覆盖证据或重置预算。明确记账为1次初始化失败启动+1次真实 import-only；不是重复执行同一目标。其后完整诊断一次、聚焦零次、正式 cohort 一次。

## Gate 与证据

| Gate | 实际标签 |
| --- | --- |
| G0/A01 | PASS：325项现场检查，Git HTTPS/Base/ACL/casefold/空占与全部 pin；3份实际 Base raw/LF snapshot |
| A02 | PASS：两个 cache 候选精确对应，旧目标不读/stat/list；fresh owner 语义与负控通过 |
| A03 | PASS（本地）：冻结后原五方法5 PASS/0 ERROR/0 SKIP，Guard denied={}，12帧完整 journal、terminal PASS、exit0、无timeout/truncation |
| A04/A06 | PASS：正式27/27，原23 IDs及实质断言保留；AST/compile/strict JSON/source/diff及反例验证 |
| A05 | PASS：独立 Python 进程核对真实PID/source/log/journal/manifest，8份新WAL逻辑owner=rpf-63；没有重跑方法 |
| A07 | PASS：正式成功后才加独立pilot及白名单artifact；去掉两项加法后YAML模型与Base完全相同，Bash -n PASS；workflow另行freeze |
| A08/A09 | NOT_RUN_AT_SEAL：普通Push/远端/hosted后续回传，不预填Linux PASS |
| A10 | PASS：1232 required/539 UNAVAILABLE不减，独立Authority与Release边界不变 |

冻结前诊断 21.457s，正式 native+独立 verifier 23.987s，正式 unit 10.961s，实验总 wall=355.811s/cap520s。各native≤120s、verifier≤60s、stdout≤2MiB，import-only≤20s/256KiB。所有启动子进程实际退出并排空。harness冻结前后hash一致；workflow在formal成功之后独立冻结，没有冒充同时已formal验证。

原六方法AST/断言身份不变，仅执行原五cohort；第六portable不重复计入。独立核验是同一次run另一进程，不是新环境复现/第三方Issuer。合成 broad-assert 假绿控制保留；本次原生零拒绝不推导历史/真实Agent成功。

## 封存与边界

Plan §0 的 `pge_dual_verify.py` blob 有39位抄录错误；用户明确授权本轮改用固定Base实际40位 `ed4329a0064daae75792eddfdfdd5cebc1b4b695`。Plan/原源码/历史未改。Windows目录fsync UNAVAILABLE；文件fsync及durable反例实证。

只上传 `public-result.json`：固定method IDs、枚举状态、typed PID/exit/布尔/字节/hash；原日志、物理owner、target token、证书正文/SDK identity不导出，失败分支也测试脱敏。完整WAL不上传。原RPF12 Artifact/Job Summary/Required Barrier/权限/35min cap保留。即使pilot成功，539 required仍将使全局CI预期FAIL，不是Release PASS。

Provider0/Key探测0/真实SDK0/Java0/本地Docker0/业务HTTP0/生产写0/LLM API费0。旧私有owner/WAL无read/list/stat，docs/reviews禁入，RPF74/81不恢复。精确3M+11A、一次普通main Push；EVIDENCE_ACCEPTED/STAGE_ADVANCED由Architect独立裁定，无release/deploy。

证据：[import归因](import-probe-attribution.json)、[验证](verification-diagnostic.json)、[反例](counterexamples.json)、[性能](performance-diagnostic.json)。Windows/hosted Python3.12 cache tag各自运行时计算，Linux须真实CI结算。wall差异不是与rev4的纯性能因果对照；CPU profile NOT_RUN。
