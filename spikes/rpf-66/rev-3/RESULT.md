# TASK_RESULT｜RPF-66/rev-3

- **Status: Partial / PARTIAL**。本地Runtime门禁修复与真实Provider诊断已取得证据；完整真实双角色闭环未完成。`TASK_COMPLETE=NO`，`STAGE_ADVANCED=NO`，`EVIDENCE_ACCEPTED`留给Architect审核。
- **Windows Python3.14完整Gate PASS：450项、0 error、0 failure、2 Docker unavailable skip，一次完整进程exit0。** 不代表Windows3.12父Runtime或Ubuntu3.12 hosted CI全绿。
- 唯一真实Session在`provider-6`停止：安全shape于原strict parser之前记录`finish_reason=length`，原parser拒绝`PROVIDER_CHOICE`，usage保持UNKNOWN。没有二轮、DomainVerified、反馈或成功Witness；**不重跑live、不修冻结源、不补造stop/usage**。

## 1. 执行身份与交付

| 项目 | 实际值 |
|---|---|
| repo / root | Public `MyKr-YSteinsK/runproof` / `D:/CS/runproof` |
| 精确Base / 父分支 | `8c087a4c8e3a57e90f14c92aca4550e5da5ed861` / `codex/rpf-66-rev2-provider-choice-shape-diagnostic` |
| 唯一新分支 | `codex/rpf-66-rev3-runtime-gate-recovery` |
| main只读快照 | `bda0cd49e50e3181f604324e94877a24b9885334` |
| source commit | `0105c7c33cca5d5f4875438005b40f6376a0f3db`；已普通push，fresh ls-remote与GitHub API读回一致 |
| 唯一新root / ABI | `.local/rpf-66-rev-3/` / `rpf66-config-pge-session-v3` |
| 冻结Source LF digest | `eb6250b39f0e11c29089424a2fa7741216298949c31f176088a3ff1038b10156`，36项闭包 |
| 冻结Verifier | `rpf66-dual-agent-verifier-v3` / `79973f913d3714bfe3346da9a4aee39101b470050de68f8a988225eb04839f74` |
| 最终receipt commit | 最终SHA及fresh远端双读在聊天回执提供，本文件不回填自身SHA |

G0逐项验证新branch/root及九个create-only公共路径在磁盘/index/Base/远端均不存在，六个允许源存在且tracked，父路径无reparse escape，ignore/hooks/磁盘/loopback/push副作用安全。用户原始状态只有根级`?? docs/reviews/`；该目录没有进入、列举、搜索、读取、hash、修改或暂存。旧rev1/rev2私有运行根、WAL、quota、PID和临时证据均未读取/复制/清理；原始固定SDK配置/解释器与原JAR源的只读pin核对属于Plan明确例外。

实际只修改三个旧文件：`pge_r66_context.py`、`pge_r66_verify.py`、`test_effectwitness_pge_r66.py`。另外三个允许文件保持原字节。新增rev3的probe、README、本RESULT与五份JSON，共八个公共新文件；第九个`dual-agent-witness.json`不存在。总tracked差异11条路径。旧spike/证书/Verifier/历史测试、Project State、Web/Vite、CI、SDK/JAR/Java和全局环境均未修改。

## 2. 最小修复及技术决定

**问题与修复**：旧R66以严格`monotonic_ns <`代表因果顺序，Windows实际存在相等的连续值。新增`wal_position/wal_order`只在`replay`已验证seq/hash-chain/owner/run/round/票据与原clock非递减的物理WAL内工作，要求事件对象对应唯一物理帧，帧位置严格增加。相等clock不再误报；倒序、缺帧、重放、跨ticket和clock降低仍拒绝。没有机械将所有时间比较改为`<=`，没有修改旧历史predicate。

修复覆盖shape→parser disposition→settlement、selection→Target、DomainVerified→cleanup→FeedbackFrozen→下一Explorer。原Domain事件seq中的真实POST→SUCCESS_WITHHELD→UNKNOWN exposure要求保持。新增六个时钟测试和五类重锚攻击，合成控制从47增至52；相等clock既测成功Session，也经生产Host transport/parser真实入口测试拒绝与UNKNOWN。

- **FROZEN保持**：两候选、三合同业务目标、原prompt/三工具/SDK/parser、cap256/128、单WAL、未知停paid/停写、独立Oracle先于反馈、Provider14/token35000/¥0.75及历史保护。
- **RECOMMENDED采用**：Windows父Python3.14主Gate，固定3.12.13只作SDK子解释器；有限旧HTTP调查；strict+安全shape先留证再严格校验。
- **DELEGATED_TO_CODEX选择**：Context schema/ABI与Verifier升v3，rev3 owner/root/Base/branch及新probe Source identity独立；业务Execution/Effect/Experiment原v2语义保持。正式端口一次选40000–44999。增加新probe `admit`，只有冻结源、唯一metadata/cold、价格与未消费资源检查全部成立才exclusive-create paid gate。
- `evidence-backed benign compatibility`未启用；强制stop、usage修补、扩大cap或冻结后修源禁止。

## 3. 有限差异与免费验收

### 解释器/旧问题矩阵

| 环境 | 本轮实际观察 |
|---|---|
| Windows父3.14.6，exe SHA=`03168c01…` | QueryPerformanceCounter，报告resolution=1e-7；1000次紧邻采样169对相等、0倒序；OTel SDK available；最终450项完整PASS |
| Windows固定3.12.13，exe SHA=`e9f7e4ba…` | GetTickCount64，resolution=0.015625；999对相等、0倒序；OTel SDK unavailable；修复后R66 Clock+Shape 12项PASS，但未重跑父Runtime全量 |
| 未修改Base快照/3.12 | 旧cold与observability两个定向case均ERROR，分别COLD_EVENT_ORDER和traceparent；证明这些缺口在旧基线仍存在 |
| Ubuntu3.12 hosted | workflow只读核实为ubuntu-latest+setup-python3.12；本轮没有触发，NOT_RUN |

rev2的21 errors/1 failure作为公开历史事实保留，来源为其原verification-diagnostic。当前将COLD_EVENT_ORDER归为baseline复现，FEEDBACK_CAUSAL_ORDER/SESSION_MONOTONIC_ORDER/SESSION_LINEAGE归为已读严格clock谓词、未逐项重跑，traceparent归为baseline复现的缺可选SDK路径，ACTUAL_CALLABLE具体根因仍未确证。**不将所有旧错误归为一个原因，也不以新12项PASS宣称Windows3.12父Runtime已全面兼容。**

旧4xx testcase四次隔离、被动审计：Base/3.14 PASS、Base/3.12 ERROR、候选/3.14 PASS、Base/3.14 PASS；端口均于finally后关闭。源码raw hash逐份相同，没有R66改动导致的跨污染证据。诊断只记录PID、端口、send长度和clock，不存headers；被动观察仍可能影响竞态。分桶为**C：精确race根因未确证**。未改旧fixture、旧test、Windows安全策略或全局包；没有monkeypatch Full suite。新HTTP日志标签1/3/4/5源于报告计数修正，实际执行严格为4次。

### 当前冻结版本的正式免费结果

- focused：**24项PASS**，wall196.198秒；原18项加六个时钟测试，四种候选组合全部纯合成PASS。
- 合成正确/缺/错外锚CLI **0/2/3**；**52类**实际修改payload、重算envelope/外部SHA及必要WAL重链的语义攻击全部exit3。模拟资源计数不是实际消费。
- **18件历史原证书**各按原raw SHA/原Verifier逐件exit0；RPF43/44/48/49/50/51r4/52r3/53r6/55r2/56r4/57/58r2/59/60/62/63/64/65r2，逐件命令/hash保存在verification-diagnostic。旧RPF66没有可补入的真实成功证书。
- Reviewed/Public各exit0；限定staged/unstaged格式检查分别exit0。
- 单次完整主Gate：`python -X utf8 -B -m unittest discover -s runtime/tests -p test_*.py -v`，**450项、0 error、0 failure、2 skip、exit0，wall612.332秒**。PID29692，snapshot=`full-d5d5b195`。没有-k/filter/xfail/新增skip/拆分拼接；旧HTTP case在这一完整进程中也实际PASS。
- 两个skip均为Docker provider unavailable: RuntimeFailure（DockerIntegrationTests、Rpf05RuntimeTests）；不称Docker可用。Source闭包36项与RPF60 Web/Vite 32项逐一校验；最终`single_full_green=true`、`final_complete_full_green=true`仅指本rev3这一完整尝试。

初版候选`ba2e4d52…`的24 focused/12个3.12定向/52控制已通过；随后仅补全新probe的冻结/准入防护，生成最终`eb6250b3…`，重新运行最终focused/合成/历史/Reviewed/Public以及最终12项3.12定向，均通过。所有本轮attempt收据保留，rev2失败没有被改写。本轮没有第二次完整全量或Windows3.12全量。

## 4. 冻结、metadata、cold与准入

全部免费Gate与格式检查后才生成唯一source-freeze。LF Source Map、七个可变/新源原字节和三个helper hash已锁；试验后再次逐项验证36个依赖的原字节与冻结前完整快照一致，Source/Verifier/helpers均无漂移。原始freeze未重写，未重跑旧任务入口。

metadata一次PASS（wall5.888秒）：实际SDK Python3.12.13、Pydantic AI2.57.0、OpenAI3.35.1、RECORD mismatch0，Java17.0.12；JAR从允许的固定原始只读源新复制，66981576 bytes / SHA=`906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。未从历史任务复制JAR副本。

cold一次PASS（wall5.022秒）：实际固定SDK scripted子进程、5 completions、4 callbacks、tool returns [2,3,4,5]、UNKNOWN后inspect、ready/report/cleanup一致；无Provider、无正式JVM/业务HTTP。原SDK子Python pin没有冒充父3.12兼容证明。

2026-10-23在准入前再次只读核对[官方定价](https://api-docs.deepseek.com/quick_start/pricing/)和[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)；峰值输入USD0.30/输出USD1.20每百万，×15守卫覆盖全池最贵档¥0.63，低于¥0.75。×15不是汇率或账单。新probe独占创建rev3 paid-gate后，live父进程才读取DEEPSEEK_API_KEY。SDK/JVM不持Provider Key，未打印或持久化其值。

## 5. 唯一真实会话：观察到的事实

live仅一次，wall29.942秒、exit3；没有自动/手工重试。Explorer合法选择`local-delivery-suppressed-after-http200`，原ToolCall ID、response ID、候选、usage/请求/合同hash在Target副作用之前已独占保存到selection receipt并绑定WAL。

真实Target经固定SDK/新Java/H2执行inspect→create v1→update v2，真实update HTTP200/business code0后Host才抑制ACK、向Agent返回UNKNOWN；故障planned/triggered/observed/agent_exposed均true。模型之后真实调用一次只读inspect，未再写；父端独立GET current/history/list分别验证v2、[2,1]与唯一项。共9业务HTTP、2 POST，UNKNOWN后POST=0。同服务只读HTTP Authority，非第三方数据库Authority。

随后Target第5次请求（会话`provider-6`）HTTP200/JSON已被transport接收。**在原strict parser之前**的shape记录：choice数1、object、index为整数0、无未知choice/message字段、assistant、无tool_calls，**finish_reason=length**。安全条件为`CHOICE_FINISH_REASON`与由此引出的`TOOL_FINISH_MISMATCH`；原parser拒绝码`PROVIDER_CHOICE`，上层场景停止码`HOST_FAILURE`。这是本轮确证条件，不能回填rev1实际原因。

未可信接收的usage只作`UNTRUSTED_OBSERVED_HINT`：prompt1084/completion256/total1340。**不纳入已知usage、不转RECEIVED、不作为账单**。合法拒绝response ID仅留下SHA256指纹，原文未保留；这是明确的取证限制，冻结后未追补或修源。已可信接收的实际model字段是`deepseek-flash`；未用官网公布的版本名代填实际raw model。

真实物理WAL共**147帧**，raw SHA=`f3b29a84ca1371f717704b5b0ee12efaaefba71982e471b3288d49f81bf6ac45`；canonical逐字节重建与Session receipt全帧一致。`provider-6`的shape/rejection/UNKNOWN RESULT物理seq为**127/129/131**；同票据/round/run先后检查PASS。UNKNOWN后没有新增Provider/POST/SDK/JVM/trial预约，没有DOMAIN_VERIFIED或FEEDBACK_FROZEN。

只读读回成功**不等于Agent完成**。本轮为Provider平台错误，Agent记NOT_COMPLETE而非AGENT_FAIL_GUARDED。正式DomainVerifier因HOST_FAILURE未成立，完成轮数0，第二轮/反馈/L2均NOT_RUN。normal未选择，NOT_RUN。Session failure receipt保留原选择和局部真实事实，没有创建成功Witness；真实原件CLI及52类真实证书攻击全部NOT_RUN。

## 6. 实际资源与费用

| ticket | role | 永久cap | 可信prompt/completion/total | 状态 |
|---|---|---:|---|---|
| provider-1 | Explorer1 | 2500 | 376 / 44 / 420 | RECEIVED |
| provider-2 | Target1 | 3000 | 702 / 30 / 732 | RECEIVED |
| provider-3 | Target1 | 2400 | 750 / 57 / 807 | RECEIVED |
| provider-4 | Target1 | 2400 | 837 / 80 / 917 | RECEIVED |
| provider-5 | Target1 | 2400 | 971 / 83 / 1054 | RECEIVED |
| provider-6 | Target1 | 2400 | **UNKNOWN**；hint不计入 | UNKNOWN |

- metadata1/cold1/session1/trial1/正式JVM1/正式SDK1/Provider6（Explorer1+Target5）/HTTP9/POST2/health1；均未超授权上限。
- 永久预约**15100 tokens**，可信已知**3930 tokens**；合计实际usage与费用仍**UNKNOWN**，未查询账号发票。
- reservation成本guard **¥0.0719235**；已知usage成本guard **¥0.021654**，二者均非账单。未知请求cap不退，不与rev1额度并表。
- provider-6有UNKNOWN RESULT但usage未决；**session-1、trial-1仍未结算**，没有清账或补造成功。
- 新JVM/SDK/Host线程/本地业务Key均按finally清理；独立OS查询确认cold/SDK/JVM PID23116/30200/21620及父live进程已结束，六个本任务端口均关闭。未清理其他用户进程或旧现场。实验WAL/失败收据/快照永久保留在本轮ignored根。

## 7. 逐 Gate 与剩余边界

| Gate | Status | 实测来源/范围 |
|---|---|---|
| G0 | PASS | fresh身份/路径/branch/root/ignore/link/用户marker/Push副作用检查 |
| R3-A01 | PASS | rev3 Context/ABI/Source/owner/两候选独立；合成与正式源冻结通过 |
| R3-A02 | PASS | 相等clock生产seam与全会话PASS；倒序/缺失/重放/跨票据等52控制拒绝；真实失败127→129→131留证 |
| R3-A03 | PASS | 四次有限HTTP对照及同源hash；Base3.12 clock/OTel复现；race/ACTUAL_CALLABLE未知明确保留 |
| R3-A04 | PASS | focused24、合成52、18历史、Reviewed/Public、Windows3.14单次完整450 exit0；Docker2跳过单列 |
| R3-A05 | PASS | 正确时机唯一freeze、原/LF/helpers不变、metadata1/cold1与固定pin/cleanup |
| R3-A06 | FAIL | 真实Target业务成功后provider-6因length被拒，usage UNKNOWN |
| R3-A07 | FAIL | 无完整首轮DomainVerified/反馈及第二轮；局部业务不能替代闭环 |
| R3-A08 | NOT_RUN | 无合法完整新Witness，真实CLI/证书攻击不运行 |
| R3-A09 | PASS | 单147帧WAL/不可返还预算、UNKNOWN停止、只读对账、清理与隐私/历史隔离通过 |
| R3-A10 | PASS | 指定新分支source commit已Push双读；最终receipt commit与最终双读由聊天回执给出 |

所有报告仅描述一例配置域受控Java/H2+真实Explorer/Target局部会话，不建立订单真实Target、跨域双真实、Web Live、Issuer、独立新执行复现、因果学习优势、L3或部署授权。只在指定新分支focused commit/普通push；main与父分支未推送，无PR/merge/tag/release/dispatch/deploy/赛事操作。Source Freeze后绑定源、测试、probe与helpers未改；Git原始用户marker保留。

建议进行Development Architect Checkpoint Review：Runtime主Gate已恢复，本轮已定位新的真实length拒绝条件；后续应围绕有界最终输出策略及合法拒绝response ID原文留证制定新授权，而非再次泛修Runtime或重开本次trial。禁止从本次shape推断rev1响应、合并旧会话为成功证书或自动推进阶段。
