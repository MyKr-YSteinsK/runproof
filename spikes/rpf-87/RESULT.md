# TASK_RESULT — RPF-87/rev-1

Status: PARTIAL

Decision: A_ACTIVE（本地验收通过；hosted派生事实尚未建立）

Base/main: `26e9bddafd29c5fea4ea604871429b019e35d264`。A08/A09为NOT_RUN_AT_SEAL；最终完整SHA、Push、远端blob与hosted结果仅后续聊天回传，不amend报告。

## 实施与来源

新增只读跨lane verifier和17项测试，仅改workflow既有文件。原RPF84/85/86代码、矩阵、原方法、历史报告、WAL/证书均未改。验证器首先实际调用原RPF85 `enforce()`，确认57模块/1232唯一ID、688 PASS/5 SKIP/539 UNAVAILABLE、DEDICATED=417、原exit1，绝不把原Handoff改为成功。

Pilot需同时满足：同Run/attempt/commit及严格路径；固定源/AST/五ID、真实START→PASS、两个不同PID、退出/排空/时限、native与独立进程收据、日志/journal/manifest与每份WAL OWNER source链、零Guard denial、零真实资源和public_projection一致。仅five exact ID映射到原DEDICATED/UNAVAILABLE/not-executed/required=true；任一不符原子性零提升。第六portable不重算。

RPF86 `identity()`、`run()`、`native()`、`independent()`、`Guard.install()`本轮均未调用。历史证书只使用固定元数据，不读正文/SDK identity。读取原RPF85 source inventory所需当前57份公开测试及matrix依赖源，仅作原合同的源/hash/AST核对，未导入/执行Runtime测试。必要source事实取定向Git源码对象；不读旧私有目录。

原CI validator从已pin源bytes直接compile，RPF85内部Router加载采用**该module内**限定loader适配，不改全局importlib，不安装audit hook；避免意外读取旧repo pycache。本地合成RPF85的OWNER仅绑定本次fresh RPF87 root；hosted仍原始严格CI路径。模型状态明确LOCAL_SYNTHETIC_CONTROL_ONLY，不能混为hosted执行。

## Gate与实际本地验收

| Gate | 实际标签 |
| --- | --- |
| G0 | PASS：178项现场检查，main/Base/HTTPS/ACL/casefold/9路径空占/ignore/reparse/push副作用 |
| A01/A02 | PASS：源/策略/ID与原Handoff完整核验，exact五项原子准入，真实反例与脱敏 |
| A03 | PASS：合成CLI实际退出assess0/enforce1/invalid2；模型693/5/534，release仍阻断 |
| A04 | PASS：RPF84/85/86相关纯安全原断言实际回归；原RPF86 27 IDs/源码不变，其余证明按源身份复用 |
| A05 | PASS：新增reconciliation step+一个公开派生JSON path，最终always Barrier先原RPF85再新复核，原其余step/触发/权限/35min保留 |
| A06/A07 | PASS：冻结后17/17方法及独立ID差集进程检查，源hash不变，无新增Runtime cohort/真实费用 |
| A08/A09 | NOT_RUN_AT_SEAL；hosted目标尚未发生，不预填534 |
| A10 | PASS（封存事实）：来源/异常/职责完整；原539不可变，新账本独立且NO_RELEASE/NO_DEPLOY |

17项正式测试采用逐方法有界子进程（≤175s，stdout≤2MiB），总controller wall 415.427s，最长单child 78.580s。此耗时为metadata/收据验证，不是运行原Runtime。冻结后无修源/重签。独立stdlib进程确认1232 ID中exact5变化、1227不变。

## 两层账本和负证据

原始真实覆盖仍以原Router/Handoff为准（历史539不改）。本地**合成fixture**模型为693 PASS+5 SKIP+534 UNAVAILABLE，DEDICATED余412；[coverage-provenance.json](coverage-provenance.json)只保存可离线对比的ID全集/差集和明确的expected标记。新hosted结算是否真实得到534必须等新Run，不能由合成fixture、public PASS、step success或hash自签单独推出。独立复核是同run另一进程，不是新环境/Issuer。

反例包含：缺/伪造public/native/verifier、PID/clock/run/attempt/commit漂移、source旧版本、漏/重复/错/第六portable ID、Guard拒绝、重新hash的假START或WAL源、物理/日志/journal改写、reparse/路径逃逸/旧owner字符串无target I/O、JSON duplicate/nonfinite/size/unknown/bool-int、output overwrite与脱敏。所有17方法通过，详见counterexamples及raw log hashes。

首轮把整套测试放进单个180s driver导致超时，已保留真实异常；该首次raw unit stdout未落盘，UNAVAILABLE，不补造。之后分方法限175s并实时保全日志。一个正例断言误把两个来源的枚举顺序差异当ID差集，改为exact排序集合比较（原native执行ID顺序仍严格）；隐私断言误将公开方法名中的sdk_identity字样当成敏感字段，改为递归字段白名单。旧失败记录/新反例均保留，没有删除测试或弱化输入准入。

## 交付、安全与后续

精确1M+9A；workflow额外源/语义/YAML/Bash-n/raw旧行保留检查通过。报告在commit前封存，后续Git/CI不回填。原RPF12 Artifact/Job Summary/Canary及RPF86 redacted artifact保留；仅新增脱敏派生账本，绝不上传WAL、私有root、路径token、证书或SDK identity。

Provider0/SDK0/Key探测0/新增本地Java0/Docker0/业务HTTP0/真实API费用0。未读/list/stat旧私有owner，docs/reviews禁入；Project State/历史/原源码不改，RPF74/81暂停不恢复。真实534仍须最终Barrier exit1，不是Release、Stage Advance或整体RPF82完成。Architect独立裁定Evidence Accepted与阶段。

证据：[verification-diagnostic.json](verification-diagnostic.json)、[counterexamples.json](counterexamples.json)、[coverage-provenance.json](coverage-provenance.json)。下一步建议按剩余412个DEDICATED cohort的实际前提和信息价值另行选择，不能从本切片推导整批可执行。
