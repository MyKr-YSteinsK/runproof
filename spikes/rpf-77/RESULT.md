# TASK_RESULT｜RPF-77 / rev-1

Status: Partial — REPORT_SNAPSHOT。实现、正式离线验收与 source push/readback 已完成；最终 evidence commit/push/readback 尚待执行，A10=NOT_RUN（最终 evidence/聊天部分）。依 Plan §7～8，最终 SHA、远端状态及 A10 由封存后的 CHAT_FINAL_RECEIPT 补齐，不 amend 本报告。

Base：`92a740504700b3ca1609f273039248ccecaffb84`；branch：`codex/rpf-77-offline-utility-policy-evaluation`；Owner：`rpf-77-rev-1`；ABI：`rpf77-offline-utility-v1`；source kind：`SYNTHETIC/OFFLINE`；Evidence Ceiling：`OFFLINE_UTILITY_POLICY_EVALUATION_ONLY`。main 只读身份为 `bda0cd49e50e3181f604324e94877a24b9885334`，未合并。

## 1. Gates

| Gate | 状态 | 实际依据及限制 |
|---|---|---|
| G0 | PASS | origin/Base/main、原工作树、目标branch/path不存在、25个 CREATE_ONLY、owner/ignore/非重解析、AGENTS/产品合同及 feature push 不触发 workflow 均已查；不读 reviews/旧私有根 |
| R77-A01 | PASS | 新11源码+2输入先 freeze；raw/LF/Git blob，5只读参考；18个 Git blob 和 GitHub API contracts 原字节匹配 |
| R77-A02 | PASS | 显式决策前预测特征、强类型/来源/snapshot；评分不放宽硬准入；不把未来 outcome/标签送入 Policy |
| R77-A03 | PASS | 零新键验证价值、成本主导的无益新键、冲突/未知字段、UNKNOWN/预算/时间及 v3 正反错误场景均有实际决策/Oracle |
| R77-A04 | PASS | 30 development+18 challenge 新案例；参数/输入/source 先冻结，challenge 作者曝光如实标记；同信息集三策略；旧3例诊断另列 |
| R77-A05 | PASS | 独立规范 Oracle；漏选、多选、成本、事实、安全、重复/冗余、成本分母和逐例 Pareto 全量重算；不要求胜出 |
| R77-A06 | PASS | 独立 verifier 无生成器导入；CLI0/2/3；两次顺序不同 replay raw SHA 一致；公开原件再验 exit0 |
| R77-A07 | PASS | 78项独立 CLI exit3，12项联动重锚，0无效、0假PASS；原件/变体SHA/PID/reason/日志完整 |
| R77-A08 | PASS | freeze后121个方法连续两次 exit0、0 errors/failures/skips；未借用旧测试结果 |
| R77-A09 | PASS | 五项工程判断及负结果齐全；RPF74暂停，旧源码和canonical state均未改 |
| R77-A10 | NOT_RUN（报告封存快照） | 已 source commit/push/Git+API双读；待最终 evidence commit/push/双读及完整聊天交接，不提前称完成 |

## 2. Source、输入和运行回执

Source commit：`234ab77a378e8817382276f3ae4f4800f767a8a0`。Source identity：`9c6ea8d9b520587274ca092ce544f49834651db64e839d31b36868ef225b4fa3`。Source Freeze 实际完成于 `2026-10-28T13:28:21.138538Z`；首次正式 challenge replay 于 `13:28:34.884630Z` 开始。之后未改源码、输入、测试或负控生成器。

Contracts raw/LF SHA 都为 `622468faf23f21ed1d3d11e0016b6cbf51751c0c225e5c3dd938d74b3f6165a0`，Git blob 为 `222588f67d8624b3d9a8d68b4fceb591c981c698`，由 Git 和独立 GitHub API 读回匹配。所有13项 source/input 与5项 reference 的 raw/LF/blob 在 source-identity-map.json，不包含报告自身。旧 RPF-76 仅公开源码/输入只读参考，没有重新签字旧证书。

Development raw SHA：`f04aca883d128da50c82300c8253c044179cc63b2e6c2e4101d90a638960b8d5`；challenge raw SHA：`32ad40a14ebfea2a31b6eb5809444115dd16419881d5fd6c4302e127255ec930`。两份输入自创建起未改；seed=7701/7702，仅作固定身份。Challenge 为作者生成并曝光数据，标记 `CHALLENGE_AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND`，不是外部盲测。

三次冻结前测试分别116、118、121项，均 exit0，无开发失败；迭代增加了 rank permutation/row hash order 控制及前提/空池/非法 locator 测试，没有据 challenge 效果调权。三次早期开发 PID 未捕获，明确 UNAVAILABLE，日志保留。

最终命令为 `python -X utf8 -B -m unittest discover -s runtime/tests -p test_effectwitness_pge_r77.py -v`。两次121项、0失败/错误/跳过，exit0；PID30484/19284，unittest时间2.358s/2.332s，进程墙钟2.542s/2.512s。stderr SHA为 `1adfd7fddef64d2f663b568bed53132d154285e3d724f0f2d75fbed8b29c90f6` / `0516c787664b2b5d1a61c1e7df9f876b26684a9f2616b2dcc50391479820d3c0`。

两次正式 replay PID25696/12708，每次153 runs/272 decisions，raw SHA均为 `d96874f815f7486ba392fac0868373211b0a13f38f06fdef2a6c4244e30db8a1`。新主评价144 runs/260 decisions；已曝光诊断9 runs/12 decisions，不能混称51个新case。第二次确实反转候选与反馈迭代顺序，不是拷贝第一次文件。

CLI正确/缺/错anchor实际 exit0/2/3（PID22368/30904/26748）；公开归档复验 PID19904、exit0。78个负控各有独立 CLI PID，全部 exit3，12组合、0 TEST_INVALID、0假PASS；negative准备阶段不计PASS。拒绝reason计数：TRACE_ID3、SOURCE_IDENTITY1、RUN_SCOPE3、EXPOSURE1、CLAIM_BOUNDARY1、FROZEN_SNAPSHOT22、ROW_SEQ1、STATE_CHAIN5、SNAPSHOT_ANCHOR1、FROZEN_ROSTER5、FROZEN_VISIBLE_RECORDS9、POLICY_UTILITY_SEMANTICS11、ORACLE_SEMANTICS4、FROZEN_EVALUATION_LABELS2、FROZEN_OUTCOME2、METRIC_DENOMINATOR_REPLAY6、ROW_HASH_ORDER1。

## 3. 决策与完整评价汇总

字段均为纯合成数据：预测verification/freshness/value不是现实效用保证；KNOWN仅表示来源与字段在决策前可见。V3评分 `2*novelty+4*verification+3*freshness+3*value-cost-2*risk`，已尝试ID不再贡献后三种义务项；未知特征不猜分，非正最大效用停止。V2沿用冻结数学语义 `10*gain+2*priority-cost-risk`，全零gain停止；B0固定order。旧 effects 映射到新 effect_keys；共同新增snapshot/来源/utility字段、initial_elapsed，不导入或运行旧driver。

Policy输入无 worthwhile IDs、future outcome、Oracle action；Oracle只收冻结case、当前记录及决策前状态。Normative no-benefit或已完成 worthwhile 的再次选择计over_exploration，其费用计wasted_simulated_cost；合法但无益的SELECT与unsafe SELECT分开。

| split / policy | SELECT | STOP | INC | cost | verified facts | repeated | redundant | safety rejections |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| dev / v3 | 10 | 22 | 8 | 20 | 7 | 0 | 3 | 10 |
| dev / v2 | 21 | 24 | 6 | 80 | 18 | 0 | 3 | 27 |
| dev / B0 | 40 | 24 | 6 | 118 | 23 | 14 | 17 | 27 |
| challenge / v3 | 6 | 13 | 5 | 12 | 4 | 0 | 2 | 6 |
| challenge / v2 | 15 | 14 | 4 | 58 | 12 | 1 | 3 | 22 |
| challenge / B0 | 24 | 14 | 4 | 74 | 14 | 8 | 10 | 22 |
| diag76 / v3 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 |
| diag76 / v2 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| diag76 / B0 | 3 | 0 | 3 | 6 | 6 | 0 | 0 | 0 |

| split / policy | correct_stop / total_stop | stop not determinable | missed | over | wasted cost | appropriate INC / INC | cost / facts |
|---|---:|---:|---:|---:|---:|---:|---:|
| dev / v3 | 20/22 | 0 | 2 | 2 | 4 | 8/8 | 20/7 |
| dev / v2 | 17/24 | 2 | 5 | 14 | 66 | 6/6 | 80/18 |
| dev / B0 | 24/24 | 0 | 0 | 24 | 86 | 6/6 | 118/23 |
| challenge / v3 | 12/13 | 0 | 1 | 1 | 2 | 5/5 | 12/4 |
| challenge / v2 | 11/14 | 0 | 3 | 9 | 44 | 4/4 | 58/12 |
| challenge / B0 | 14/14 | 0 | 0 | 15 | 56 | 4/4 | 74/14 |
| diag76 / v3 | 0/0 | 0 | 3 | 0 | 0 | 0/3 | ZERO_FACTS/null |
| diag76 / v2 | 0/3 | 0 | 3 | 0 | 0 | 0/0 | ZERO_FACTS/null |
| diag76 / B0 | 0/0 | 0 | 0 | 0 | 0 | 3/3 | 6/6 |

所有split/policy unsafe_select=0、risk_guard_violation=0；合法SELECT分子=SELECT总数。0/0不能称100%。Stop correctness分母排除not determinable，因此dev/v2为17/(24−2)=17/22，其余有STOP者同表原分母。Safety rejections是每步过滤次数，非攻击拒绝率；攻击拒绝率独立为78/78。

成本/事实paired Pareto（Favorable/Unfavorable/Tie/Tradeoff）：dev v3-v2=0/0/18/12、dev v3-B0=3/0/16/11；challenge v3-v2=0/0/11/7、challenge v3-B0=2/0/10/6；diag v3-v2=0/0/3/0、diag v3-B0=0/0/0/3。没有pure unfavorable不代表无策略负例；成本和事实变少通常属于取舍，不能隐藏规范机会损失。

反例：dev-00 / challenge-00 已有全部effect键但存在可见验证/更新预测，v3 SELECT，v2 ESTIMATED_ZERO_GAIN STOP；dev-01 / challenge-01 新键成本风险主导，v3 STOP，v2/B0有规范无益探索；dev-09 / challenge-09 预测高估，v3产生1次多余SELECT、浪费2；dev-10 / challenge-10 特征漏掉价值，v3早停，missed=1。故普遍策略优势 NOT_ESTABLISHED。

旧三例 `diag-dev-01`、`diag-dev-13`、`diag-hold-01` 仅由RPF-76公开输入做新ABI诊断投影，utility字段缺失保留UNKNOWN。V3三次INC、v2三次STOP，规范Oracle均有尚未完成的机会：双方missed=3，v3合理INC=0/3；B0选择后获得6个合成事实。旧问题未因新挑战集表现而宣布解决，也未运行旧Runtime/私有Run。

## 4. 真实性、资源与时间

完整roster在两份新输入中预冻结，不从待验证visible records自行签发；record SHA是规范化合成记录字节完整性。Verifier只导入contracts与fixture读取，独立重算其余逻辑。SHA不能抵御同时控制issuer与trust root的对手；normative label不是Authority，facts对数不是信息论/因果收益。Source绑定exact raw layout，Git LF另核对，跨平台任意clean checkout未证明。

Provider=0、实际token=0、¥0、真实SDK child/JVM/SQLite/HTTP/socket/外部Issuer/生产部署=0；宿主Key读取与存在性探针0。Daybreak、旧完整Runtime、真实Explorer/Target/Authority均NOT_RUN。旧`.local`账本未读写，reviews未进入/列举。

记录88个正式普通Python child；实测同时child=2，及其两个recorder parent构成4个Python峰值，PID30484/19284/14144/6124均有回执。正式命令墙钟总和27.7004s，最大5.8945s；负控逐个独立CLI串行，78次共16.4068s。CPU单独用量UNAVAILABLE，不把墙钟冒充CPU计量。所有记录命令无timeout，开发日志和78个变体保留，私有产物约86MB，未删除marker/失败证据或清理旧根。

G0 clock=2026-10-28T13:17:19Z；首单调观测10048.9593457对应13:17:24.765314Z，初始偏移5.765314s另列；唯一deadline=2026-10-29T01:17:19Z。最终交付实际结束时刻由聊天及交付回执给出，不在报告封存前猜测。仅两次focused提交，源码已推送，evidence尚待最后动作。

## 5. VERIFIED_FINDINGS

`projection.eligibility`在utility评分前执行硬准入，`utility.features`将novelty、验证、新鲜度、值更新、成本和风险分开。`policy.decide`能在零新键、有公开验证预测时继续，也能拒绝预计无益的新键。独立`verify.adjudicate/measurements/compare`实测拒绝78个篡改；新challenge中漏选3→1、多选9→1仅是限定作者合成集的描述性结果，且v3事实更少。

## 6. CODEX_ENGINEERING_JUDGMENT

997行Python包含策略、fixture、CLI、测试和独立复算；v3不是简单取消零gain门槛。最大风险已从“只数键”转为“可见预测是否可信、有多准”：KNOWN只表示来源可见，不表示实际价值为真，kind9/10已给出正负预测误差。旧三例缺特征时保持UNKNOWN是诚实的能力缺口，不能以规范标签补答案；本轮没有建立可直接用于真实控制器的普遍优势。

## 7. ALTERNATIVE_PATHS_AND_TRADEOFFS

选固定整数可解释式而未引入模型/贝叶斯价值学习，可逐项复验且费用为零；代价是未校准特征、权重和attempted-ID义务完成代理。V2只复制数学语义、三策略共用信息和硬准入，避免旧runtime启动；verifier独立计算仍共用schema/规范概念，保留共模风险。成本/事实Pareto仅作描述，另列规范漏选/多选，避免用单一胜率掩盖取舍。

## 8. NEXT_DECISION_RECOMMENDATION

建议Architect先审查kind9/10和旧诊断UNKNOWN：明确真实系统如何取得决策前验证需要、新鲜度和值更新预测，以及规范“值得继续”由谁定义。A路线是在独立作者数据上校准这些估计与双向错误；B路线是经另行批准做只读Policy Lab，展示各项解释和不确定性。真实Agent/业务接入仍需单独安全及来源证据，RPF74不自动恢复。

## 9. POTENTIAL_GENERALIZATION_DEBT

有限抽象域、固定时刻0 snapshot、attempted代替义务完成、预标normative utility及手工曝光challenge均限制外推。真实来源认证、动态时效、值更新误差、跨session身份、校准风险/成本与可移植source identity仍缺；这些限制不能由更多内部hash修复。CURRENT_STATE只是新分支的离线算法/评价切片；TARGET_INTENT的真实Target/独立Authority不变。TASK_COMPLETE/EVIDENCE_ACCEPTED/STAGE_ADVANCED归Architect；最后完整聊天回执才补齐A10。
