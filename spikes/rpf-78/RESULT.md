# TASK_RESULT｜RPF-78 / rev-1

Status: Partial（协议状态 PARTIAL）。R78-A08 FAIL：两次冻结后106方法测试均 exit1、0 failures、1 error、0 skips；`test_negative_39` 中 `oracle-stop` 把已为 MUST_STOP 的值改成 MUST_STOP，触发 TEST_INVALID_NO_OP。不得把105个成功方法说成全套通过；没有修改冻结源码或替换失败原件。负结果不来自模型输给基线，而来自测试门禁未通过。

Base `240dbae75cc70f142c7c37a2a3994085063d7ccc`；branch `codex/rpf-78-offline-forecast-calibration-abstention`；Source commit `5a96a11c70976d6617a9a6ad05ff823dac7e309d`（已普通 push、ls-remote/fetch20 blobs/GitHub API读回）。Source SHA256 `366617fdb3c1a33a53cd3909ecd65bc7f85747e1ba7c47d6fbada4db6b56fe74`。模型原始 SHA256 `7e7afe079c57ed7a0c281b929fbc98f3d8ee188d8a9c324c01d80d2aca67af47`。封存于 2026-10-29T08:09:10.401821+00:00；G0起点 2026-10-29T07:14:34Z，已用 3276.4 秒，截止 2026-10-29T19:14:34Z。

## Gate 及执行事实

{"G0": "PASS", "R78-A01": "PASS", "R78-A02": "PASS", "R78-A03": "PASS", "R78-A04": "PASS", "R78-A05": "PASS", "R78-A06": "PASS", "R78-A07": "PASS", "R78-A08": "FAIL", "R78-A09": "PASS", "R78-A10": "NOT_RUN"}

A01：14源码/输入全部显式加入 index 后格式检查、编译12 Python、严格解析2 JSON，通过后冻结；Source Map另含6只读公共引用，20个LF/Git blob经fetch逐个一致。A02：强类型当前合同、冻结roster、内容/合同hash、visible time与反馈；预测输入不含未来标签。A03：24 fit案例48标签拟合、独立模型冻结先于首次评价。A04：12 validation/18作者已见challenge、三个抽象域、四策略同合同/预算/结果时序。A05：独立Oracle和全部分母/误差/净效用复算。A06：7类压力独立派生并逐个绑定父原始hash。A07：两次主重放原字节一致，独立Verifier及锚CLI实际0/2/3。A08：有效58项CLI全部exit3，含8组合；另1无效不算成功，完整测试两次均FAIL。A09：五项工程判断与PAUSED边界写明。A10：本报告在Evidence commit前封存，NOT_RUN不得回填未来SHA；最终聊天收据补充实际交付观察。整体状态保持PARTIAL。

`python -X utf8 -B -m unittest discover -s runtime/tests -p test_effectwitness_pge_r78.py -v` 两次真实执行，分别 2026-10-29T07:53:14.317135+00:00 和 2026-10-29T07:53:14.314280+00:00，PID 18940 / 7460，均106方法、105通过、1 error、exit1。冻结前纯组件35/39/39方法三次通过，不替代最终门禁。全部原始stderr/收据保存在本任务ignored根，hash和命令见runtime/verification JSON。

原始 `probe.py negative` 实际exit3，留下38个prefix文件。任务私有操作枚举器随后调用**未修改的 frozen mutant函数**，逐字节核对38个已存文件、补建20个有效文件、保留无效index38（old/new MUST_STOP）；另一独立操作进程对58个有效变体逐一调用真实 `probe.py verify --file ... --sha ...`。所有58真实PID、exit、reason、raw/日志SHA见negative-controls.json。没有以PREPARED充数，也没有把这个续取流程称为原始negative入口成功。

## 冻结与统计边界

Source freeze完成 2026-10-29T07:52:07.269942+00:00；唯一持久化fit模型完成 2026-10-29T07:52:07.634856+00:00；首次正式评价开始 2026-10-29T07:52:40.286663+00:00。模型文件与fit原字节完全一致；测试/Verifier可独立重算fit，但无第二次持久化导出/调参。

fit24/48 outcome、development_validation12/24、challenge18/63；分区case与outcome IDs互斥，三个域为lab-amber/bronze/cobalt。challenge为AUTHOR_EXPOSED_NOT_EXTERNAL_BLIND。旧77高估dev09/challenge09、低估dev10/challenge10及三个UNKNOWN诊断仅公共只读索引，未套用新模型、未算本轮challenge；语义索引导出发生在评价后，公共引用字节在源码冻结时已锚定，未参与拟合。

目标为合成useful_effect二值事件；HIGH n24/k18/p=0.730769230769，LOW n22/k4/p=0.208333333333，RARE n2/k0为INSUFFICIENT_SUPPORT；最小n6。平滑点预测(k+1)/(n+2)，Wilson z1.96仅描述性敏感性区间，非真实95%覆盖。表中n/正例/上下界/宽度见原字节forecast-calibration-report.json。

预测误差分母为**初始硬准入候选预测**，不是全部outcome：validation支持10/15（未知5），Brier 2.265809911244/10=0.226580991124，ECE 0.225961538462，均值预测0.574038/观测0.8；challenge支持27/44（未知17），Brier 7.099677432614/27=0.262951016023，ECE 0.219491927826，均值预测0.595323/观测0.814815。ECE固定四桶=sum|桶预测和-桶正例和|/支持N；每桶样本/和公开。未知/低支持不视为0收益或计100%准确。两组为不同手工样本，Brier变化不能解释为统计显著退化。

## 决策与反例

Validation：

|策略|成本 / 事实|合成净效用|漏选 / 过探|拒绝|局部机会成本|覆盖率|正确 STOP|
|---|---:|---:|---:|---:|---:|---:|---:|
|R78-BOUNDED_ABSTAIN|9 / 3|13|5 / 1|6|31|9/15|6/6|
|R78-POINT_ESTIMATE|22 / 5|22|4 / 1|4|26|13/17|7/8|
|PGE-v3-utility|25 / 8|37|2 / 1|2|13|18/20|9/10|
|B0-fixed|43 / 13|55|0 / 2|1|0|24/25|11/11|

作者曝光Challenge：

|策略|成本 / 事实|合成净效用|漏选 / 过探|拒绝|局部机会成本|覆盖率|正确 STOP|
|---|---:|---:|---:|---:|---:|---:|---:|
|R78-BOUNDED_ABSTAIN|27 / 6|25|8 / 3|10|63|15/25|8/8|
|R78-POINT_ESTIMATE|57 / 10|47|6 / 3|6|51|23/29|10/12|
|PGE-v3-utility|51 / 15|65|3 / 3|3|21|31/34|13/15|
|B0-fixed|76 / 22|94|0 / 4|2|0|39/41|16/16|

四策略所有unsafe_select/risk_guard_violation/repeated均0。bounded challenge适当拒绝2/10，点估计2/6；v3 2/3，B0 2/2。bounded正确STOP8/8不能掩盖覆盖15/25、漏选8与局部机会成本63。合成净收益为benefit_units*useful_effect-cost-risk；UNKNOWN交付的隐藏真值可由合成Oracle计分，不能称独立业务效用。事实条数不代表因果信息量；机会成本只是当前窗口最佳可行规范净收益，非顺序最优regret。

高估：challenge-00与challenge-14，HIGH点预测0.730769但标签0，bounded/point仍SELECT并浪费成本。低估：challenge-01与challenge-15，LOW标签1，净收益为正而bounded拒绝/point停止；均计漏选。低支持：challenge-03/17的RARE n2，challenge-04未见桶；challenge-07来源UNKNOWN也不可判定。新策略更差：challenge-02/16下界跨零而点估计仍正，bounded INCONCLUSIVE损失机会；完整首行、Oracle、状态和每策略指标在counterexamples.json，未伪造或删负例。

主重放120 runs /206 decisions，两种候选和反馈遍历顺序raw SHA相同 `60aab66b6b9a9bd54eb2d446c824a70f74be76c7d668244f2e8a211dfb02f219`。压力7类×18=126新case、504 runs /742 decisions，raw SHA `fd226deba425070f64274b87e4febb9b169da2068cb92e3382427425c5dc5e1b`。COST_UP、LABEL_FLIP、UNSEEN_BUCKET、EXPIRED_SOURCE、DELAY_FEEDBACK、REVERSE_CANDIDATES、MISSING_DOMAIN均预注册，派生ID与parent_raw_sha256分开，不改原始challenge。压力聚合bounded净28/拒绝96/漏选39/过探7，point净24/拒绝82/漏选35/过探14，v3净187，B0净265；四者unsafe=0。逐类公平对照见evaluation-report.json.stress_by_shift。区间在部分压力比点估计少亏损，但没有现实鲁棒性证据。missing-domain保留相同域UNKNOWN；无跨域全局解锁或全局封锁推断。

## 独立验证与资源

Verifier只import copy/math/contracts，独立复算模型、预测/排序、Oracle、状态、row/hash链、统计分母与压力变换，不调用生成侧policy/calibration/forecast/replay/metrics/oracle。正确锚exit0、缺锚exit2、错锚exit3；公开decision-traces亦实际CLI exit0。仅共享schema/hash仍是共同故障局限。raw源码身份区分Windows原始字节与LF/Git blob，跨平台raw身份可移植性NOT_ESTABLISHED。

Provider HTTP0、token0、费用¥0、SDK0、JVM0、业务写入0；无服务/数据库/socket/browser/Docker、未读取或探测Key。网络仅本分支Git/GitHub推送读回。Python含recorder调度峰值4，每进程180秒上限；连续OS采样、CPU/I/O测量UNAVAILABLE，wall秒不充作CPU。完整旧Runtime NOT_RUN。运行收据与起止UTC/单调差、产物体积见runtime-diagnostic.json。未进入旧私有Run或docs/reviews；旧main/父分支/原RPF74现场保留，RPF-74 PAUSED。无reset/clean/marker删除/历史重写/merge/deploy/提交赛事。

## VERIFIED_FINDINGS

- fit24/validation12/challenge18，仅48个fit标签参与拟合；模型和轨迹独立复算，两种遍历顺序主轨迹原字节相同。
- challenge支持27/44，Brier0.262951/ECE0.219492；bounded净效用25、漏选8、成本27、事实6、拒绝10，不支持优越性主张。
- 58个有效CLI负控全部拒绝，含8个组合；106方法两次各1 error。失败是无效变换被no-op保护拒绝，并非Verifier接受了伪造Oracle。

## CODEX_ENGINEERING_JUDGMENT

- 必须区分来源KNOWN与预测可靠。Policy只接收当前view/state/evidence和冻结fit模型，评价标签在接口之外。
- 稀疏手工桶的Wilson区间不保证未来校准；bounded正确STOP8/8不能掩盖覆盖15/25与漏选8，不应据此推广策略。
- no-op保护正确暴露了测试fixture选点错误；A08保持FAIL、任务PARTIAL，不能事后修改冻结源码消除失败。

## ALTERNATIVE_PATHS_AND_TRADEOFFS

- 点估计有更多选择、净效用47高于25，但仍漏选6、过探3。
- B0/v3的challenge净效用94/65高于bounded；B0成本76高于27，少花成本的拒绝不能证明可靠性更好。
- 后续修订可选择保证不同于原值的Oracle变换，并在冻结前用fit衍生fixture验证变换有效性；本轮不实施这项修改。

## NEXT_DECISION_RECOMMENDATION

- 建议Architect审查PARTIAL证据后决定是否授权新修订；先修负控fixture，再新冻结并完成规定的完整聚焦测试，保留本轮原件。
- 考虑真实Explorer前，应取得独立作者评价并明确特征可见性/效用语义；不从本轮推导Provider、业务或Live授权。

## POTENTIAL_GENERALIZATION_DEBT

- 手工合成非iid、作者已见challenge，不代表真实校准、95%覆盖或显著性。
- 桶过粗、低支持、OOV、来源过期均会引起拒绝，拒绝机会成本必须可见。
- 即使交付UNKNOWN，规范净效用仍是模拟器隐藏真值；事实数不是因果信息，局部机会成本不是顺序regret。
- RPF77数学基线增加了共同特征生命周期检查，不宣称旧Runtime原字节复现；raw源身份依赖Windows checkout，Verifier与ABI共享schema/hash辅助函数。
- canonical negative入口在index38中断；有效58项依赖逐项枚举未修改的公开mutant索引并保留无效项，不能声称原入口完整成功。

TASK_COMPLETE / EVIDENCE_ACCEPTED / STAGE_ADVANCED 仅由Architect审查实际证据后决定。
