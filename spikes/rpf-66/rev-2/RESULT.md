# TASK_RESULT｜RPF-66/rev-2

- **Status: Blocked / BLOCKED**；`TASK_COMPLETE=NO`，`STAGE_ADVANCED=NO`。工程候选与免费验证证据已交付，完整真实双角色任务未完成。
- **阻断点：P1 完整 Runtime Gate 未通过。** 未进入 Source Freeze、P2 metadata/cold、Paid Admission 或 live。未读取 Provider Key，未创建真实 Context、物理预算 WAL、Session receipt 或成功 Witness；所有正式资源计数为0。
- `PROVIDER_CHOICE_DIAGNOSIS=NOT_OBSERVED`，`diagnosis_scope=FREE_SYNTHETIC`。本轮不能确证真实 Provider 的具体 choice 条件，不能反推 rev1 的未知响应。

## 1. 身份、范围与版本

| 项目 | 实际结果 |
|---|---|
| 仓库 / root | Public `MyKr-YSteinsK/runproof` / `D:/CS/runproof` |
| 精确 Base / 父分支 | `7ccc34e6f6c188cb927211f144dd174287927356` / `codex/rpf-66-real-explorer-target-feedback-session` |
| 本轮唯一分支 | `codex/rpf-66-rev2-provider-choice-shape-diagnostic` |
| main 只读快照 | `bda0cd49e50e3181f604324e94877a24b9885334` |
| source commit | `a995f82d7807856d20d698cbecdf0fd08714b198`，已普通 Push，fresh ls-remote 与 GitHub API 均读回相同 SHA |
| 唯一 ignored 根 | `.local/rpf-66-rev-2/`；G0前不存在，未复用旧任务现场 |
| 候选 Source Map | 36项，digest=`ab63f721505701e8432a26dfb22ed815dce06353c9e4a9a85a74648dab2eb53a` |
| 候选 Verifier | `rpf66-dual-agent-verifier-v2` / `85440c8c2dc8c4aa1db50486dc8303ab5f6e012ca8710844a45be2cd4bc67227`；未进行正式freeze |
| Source Freeze | `NOT_RUN`；候选哈希仅证明已测试版本，不能冒充冻结成功 |
| 最终 receipt commit | 由聊天最终回执提供 SHA 和最终远端双读，避免将文件自身 SHA 回填进自身 |

G0已核对 Base、branch、remote、八个create-only路径、新根、父路径link、ignore、hooks及feature push的workflow副作用；新分支在本地与远端均不存在后才创建。最终刷新前，main与父分支均保持上述SHA。用户原有状态只有顶层 `?? docs/reviews/` 标记；该目录内容未进入、列举、搜索、读取、hash、复制、修改或暂存。旧 `.local/rpf-*` 私有现场未读取；固定SDK原始配置/解释器pin的只读访问属于Plan指定例外。

## 2. 六个源文件的实际改动

1. `pge_r66_context.py`：rev2 Base/branch/ABI、独立根与Session/Run身份、WAL owner/revision/root binding，以及新probe Source依赖。预算仍为14 Provider / 35000永久预约tokens / ¥0.75守卫。
2. `pge_r66_target_config.py`：在原transport返回后、原strict parser前，exclusive写入安全shape回执与WAL；限定schema、字段、计数、枚举、ID hash和usage hint。加入细化条件、ID/参数/usage前置核对；拒绝响应标UNKNOWN并停后续paid/write。
3. `pge_r66_explorer.py`：合法selection、原ToolCall ID、response ID、候选、usage、请求hash在Target前持久化；持久化body使用可由固定源码重建的hash/feedback回执。
4. `pge_r66_session.py`：选择freeze先于trial/JVM/Target；失败保留selection与`NOT_COMPLETE` receipt；Agent未完成不能进入DomainVerified/FeedbackFrozen成功row。
5. `pge_r66_verify.py`：rev2证书/Verifier身份、独立shape schema、scope/usage/ID/hash/先后关系、原selection绑定、不可重写checkpoint shape hash及partial拒绝。
6. `test_effectwitness_pge_r66.py`：生产同一transport/parser/factory/Session的正负矩阵、隐私canary、失败只读对账与清理、四组合、47类重锚攻击。

创建七个新公共路径：probe、README、本RESULT、preflight-diagnostic、verification-diagnostic、session-summary、capability-assessment。第八个 `dual-agent-witness.json` **不存在**。未修改其他tracked文件、旧RPF66顶层证据、基础parser/SDK、RPF63/64/65、Project State、Web、CI或控制平面。

### 技术决定

- **FROZEN 合同**：两候选/三合同/业务目标、单WAL、原SDK与parser、output cap256、原prompt、UNKNOWN停写、独立Oracle先于feedback、原资源上限保持。此处是合同分类；实际Source Freeze未发生。
- **RECOMMENDED 已采用**：`strict + safe diagnostics`；只进行原来的单次transport，先shape后校验，原Explorer选择提前留证。`evidence-backed benign compatibility`未启用；`bypass/forced stop`禁止。
- **DELEGATED_TO_CODEX 实际选择**：ABI `rpf66-config-pge-session-v2`；shape `rpf66-provider-safe-shape-v1`，shape≤8192 bytes、receipt≤12288 bytes、最多2个choice/每choice最多2个tool摘要；usage始终为`UNTRUSTED_OBSERVED_HINT`；transport/decode前无可用JSON则`NOT_OBSERVED`。

只保留允许字段名/未知键数、类型、有限枚举、合法ID不可逆hash、有界usage hint；不导出raw Provider JSON、content/reasoning、原arguments、prompt、key/header或私人绝对路径。choice type/unknown fields/required fields/index type/index zero/finish reason分别细分。未把length/null/filter转换为stop，未补造usage或成功响应。

## 3. 免费验证与阻断证据

### 已通过的当前候选验证

- 系统Python下focused：18项 PASS，测试370.643秒 / wall371.063秒；含27个响应负矩阵子案例、合法stop/单tool、transport/size/JSON/timeout/HTTP错误、隐私canary、ID重放、生产factory异常与四种两轮组合。
- 合成CLI正确/缺/错锚为 **0/2/3**；**47类**修改payload、重算envelope/外锚且必要时重链WAL的语义攻击全部exit3。该证据仅为`SYNTHETIC_TEST_ONLY`，其中模拟资源/费用不是真实消费。
- Reviewed Artifacts、Public Docs均exit0；18件历史证书原字节SHA及原Verifier逐件exit0，完整表见verification-diagnostic，未生成伪第19件。
- 每份完整快照逐项核对当前36项Source闭包与RPF60完整32项Source Map输入；当前两份完整快照均658个明确路径。staged/unstaged白名单格式检查分别exit0。

### 三次完整 Runtime attempt（不得合并为全绿）

| attempt | Source / 环境 | 实际结果 |
|---|---|---|
| `5cae06ec` | 较早候选`b2e3e814…`，系统Python | 221.713秒主动取消，为补充checkpoint shape不可改写校验；exit4294967295，无完整测试数，不算PASS |
| `6fbbd35a` | 当前候选`ab63f721…`，系统Python3.14 | **444项，0 failure / 1 error / 2 skip**，1360.189秒；未修改历史HTTP fixture出现WinError10053；exit1 |
| `aa48741c` | 当前候选`ab63f721…`，锁定Python3.12.13 | **444项，1 failure / 21 errors / 2 skip**，1490.139秒；exit1 |

`single_full_green=false`，`final_complete_full_green=false`。两次完整运行的2个skip均为Docker provider unavailable；不称Docker通过，不称整轮PASS。

系统3.14失败点为历史 `ConfigTargetDiagnosticBackendTests.test_fixture_http_4xx_preserves_first_enumerated_rejection_code`。同一快照的定向复查：系统3.14再次报WinError10053，锁定3.12.13单项通过。仓库Release Gate使用Python3.12，因此随后进行了完整固定环境对照；没有用单项PASS替代整轮Gate，也没有修改历史fixture或Windows安全策略。

固定3.12.13整轮仍失败，20个拒绝型错误分别为`FEEDBACK_CAUSAL_ORDER×4`、`SESSION_MONOTONIC_ORDER×1`、`COLD_EVENT_ORDER×11`、`ACTUAL_CALLABLE×1`、`SESSION_LINEAGE×3`，另有1个`KeyError: traceparent`。新增R66负矩阵的`tool_unallowed`子案例也失败：先后事件的`monotonic_ns`均为46423000000000，严格`<`断言不成立。**这是本轮新增测试的已知失败，不能全部归为历史代码问题。** Windows父Runtime的3.12兼容性未建立；固定SDK子解释器pin不等于父Runtime整套环境可替换。

HTTP拒绝路径未读body即关闭连接、Windows计时精度与可选observability依赖分别是调查线索；未逐一确证所有错误根因。历史源码与Verifier受保护，当前白名单不能修复整个失败面。停止付费的直接依据是完整Gate失败，而不是猜测Provider响应会怎样。

## 4. 实验、资源、费用和证据边界

| 实际阶段/资源 | 本轮实际值 |
|---|---|
| Source Freeze / combined metadata / cold | NOT_RUN / NOT_RUN / NOT_RUN |
| paid-gate / live / Provider key读取 | NOT_RUN / NOT_RUN / NO |
| session / trial / 正式JVM / 正式SDK | 0 / 0 / 0 / 0 |
| Explorer / Target / 全部Provider | 0 / 0 / 0 |
| 正式业务HTTP / POST / health | 0 / 0 / 0 |
| 永久预约tokens / 已知tokens / 本轮成本守卫预约 | 0 / 0 / ¥0 |
| 本轮Provider unknown / 未结算票据 | 无；真实WAL未创建 |
| 实际账号账单 / rev1未知usage | 未查询 / 保持未知，未读取旧私有账本、未退款或转移额度 |
| 两轮真实选择/读回/故障四态/Feedback/L2 | 全部NOT_RUN；normal与suppressed均未真实选择 |
| 真实Witness / CLI0/2/3 / 真实语义攻击 | 不创建 / NOT_RUN / NOT_RUN |

P0只读核对[官方定价](https://api-docs.deepseek.com/quick_start/pricing/)与[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)；当时Flash峰值USD0.30/1.20每百万在×15审慎守卫内。P2/P3未到达，不冒充再次价格准入或实际账单。公共pins中的Python3.12.13、SDK2.57.0/OpenAI3.35.1、Java17.0.12、JAR66981576 bytes / `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`是预期值；本轮combined metadata未运行。固定解释器文件hash由只读pin核对，见preflight；未额外执行cold/SDK/JVM来取证。

免费快照、原始脱敏日志、测试WAL、控制副本和复现脚本保留在本轮ignored根；重要取消/失败未删除。已结束的本轮完整测试进程PID经系统查询均不存在；没有正式实验PID/port可清理。未使用的报告草稿脚本已清理。原始私有目录标记保持原状。未来不能把这些合成或局部证据拼成真实双轮。

## 5. 逐 Gate

| Gate | Status | 来源与限制 |
|---|---|---|
| G0 | PASS | preflight.G0的实际仓库/路径/身份/副作用检查 |
| R2-A01 | PASS | 独立ABI/root/source/owner实现及四组合合成检查；真实Context未初始化 |
| R2-A02 | NOT_RUN | 生产Host seam的免费正负/隐私检查PASS；真实Provider shape未观察 |
| R2-A03 | NOT_RUN | 生产factory失败路径与原selection ID留证合成PASS；真实选择未运行 |
| R2-A04 | FAIL | 两次完整Runtime均不全绿；Freeze/metadata/cold均NOT_RUN |
| R2-A05 | NOT_RUN | 未预约真实Provider；无真实会话usage可验收 |
| R2-A06 | NOT_RUN | 未运行真实两轮、Oracle/Feedback |
| R2-A07 | NOT_RUN | 两候选均未真实选择；不填伪fault false/triggered |
| R2-A08 | NOT_RUN | 真实Witness不存在；真实CLI/攻击不运行 |
| R2-A09 | PASS | 免费attempt如实保留、边界/用户文件保护、无key/paid/native trial、进程已结束 |
| R2-A10 | PASS | source commit普通Push及双读完成；本回执最终commit/Push双读由聊天最终回执给出，不自引用 |

## 6. 交付与后续所需授权

仅修改六个旧白名单并新增七个rev-2文件，共13条tracked路径。source commit已从新进程经ls-remote与GitHub API双读一致；最终receipt commit单独提交并普通Push，最终SHA在聊天回传。main及父分支未推送；未创建PR、merge、tag、release、dispatch、deploy或比赛提交。功能分支push不触发已审workflow的发布副作用，未宣称CI全绿。

下一修订需明确完整父Runtime环境，并处理历史HTTP fixture、时间顺序/可调用身份/观测依赖失败与本轮新增等时间戳断言；若要修改受保护历史源码，必须扩大精确白名单并保存旧证书绑定。当前没有正式Source Freeze，也没有已消耗的rev2付费额度；这不授权越过P1或自行重开真实实验。最终`EVIDENCE_ACCEPTED`及阶段推进留给Architect审核。
