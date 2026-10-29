# TASK_RESULT｜RPF-80 / rev-1

Status: PARTIAL — PENDING_FINAL_DELIVERY（离线验收已完成；Evidence commit/push/最终双读由聊天补证，不回填未来SHA）。

Base `069108635a77b0a4a9a1f16fa23c205074c0f7f2`；branch `codex/rpf-80-unknown-provider-reservation-oracle`；Source commit `a5310b5f04efb96ae30fc584b212747d9d1639b9`，5源已普通push/fetch并API读回Oracle，才开始freeze。最终Evidence SHA由聊天回执补，不amend。Gate：{"G0": "PASS", "R80-A01": "PASS", "R80-A02": "PASS", "R80-A03": "PASS", "R80-A04": "PASS", "R80-A05": "PASS", "R80-A06": "PASS", "R80-A07": "PASS", "R80-A08": "PASS", "R80-A09": "PASS", "R80-A10": "NOT_RUN/PENDING_FINAL_DELIVERY"}。

## G0与实际时间顺序

事前观测UTC 2026-10-29T13:39:26.538674+00:00 / mono 97773.5757164，first_create UTC 2026-10-29T13:39:26.667029+00:00 / mono 97773.7040693；原始JSON先stdout flush，再git worktree add，最后持久化于 2026-10-29T13:39:27.673268+00:00。freeze UTC 2026-10-29T13:50:28.791169+00:00 / mono 98435.828212，第一次正式suite 2026-10-29T13:50:28.791809+00:00 / mono 98435.828843。严格 prewrite < first_create < freeze < tests。OS/Python/Git/free bytes/owner、13路径Base/index/大小写FS、ignore/reparse、main-only push风险均在首次写入前检查。原PAUSED工作树仅tracked status只读，未checkout/clean/stage。完整原始收据task-private，公开版去除宿主路径/所有权用户名但保留原收据hash与命令输出hash。

第一次只读G0调用系统PowerShell5失败（Get-Acl模块不可加载），无任何文件/分支创建；确认已有runtime pwsh7可读后整套重新只读核验，才打印PASS收据并创建新worktree。没有事后补记充当前置，也不逆改RPF78/rev2 G0 PARTIAL。

## 源码事实及判断

contract-analysis以固定Base/path/blob/行号定位：mark_unknown设置域停写；TOOL_RETURN含UNKNOWN，后续completion才可能FAULT agent_exposed；claim_slot随后可reserve(provider)，原生replay只锁存资源RESULT UNKNOWN，原Verifier检查业务WRITE_AFTER_UNKNOWN但漏新模型票。旧报告config199→205/233、order427→433/461只作SOURCE_REPORT_COUNTEREXAMPLE_REFERENCE，未读旧F WAL、更未重放实际旧帧。

新Admission是纯内存PROPOSED_STRICT_BARRIER；业务UNKNOWN后全会话任意域/角色的新provider票都DENY，同域业务写单独禁止。Oracle独立只import hashlib/json/re，从原始字节独立复算schema/seq/time/hash/票据/业务UNKNOWN/预约顺序，无Admission或生成器判定函数依赖。共享事件枚举/数据语义，不共享核心判定代码。

14个预注册合成case，独立原始输入SHA在Source fixtures固定。正常1、两域只读2、旧票结算1、旧票后发风险1，共5 NO_VIOLATION（仅预约范围）；双域×双角色4、跨域1、预算假设/停写后仍预约1、FAULT时序1、联动重锚违规1，共8 VIOLATION；不完整投影1 INCONCLUSIVE。全会话规则拒绝跨域，但同域列NO_VIOLATION，不能偷换；FAULT observed/exposed不能替代TOOL_RETURN停点。旧票RESULT结算不等于新预约；UNKNOWN后旧票MODEL_REQUEST单列OLD_TICKET_POST_UNKNOWN_SEND_UNPROVEN。AUTHORITY_READ只是抽象宿主只读动作，不声称真实HTTP或完整原生WAL执行。

## 实际验证与反例

冻结前32方法初次1失败1错误：重排变换未修clock导致EVENT_TIME_SCOPE而非预期来源拒绝，invalid index对normal先查UNKNOWN抛StopIteration。修正mutation index前置校验、重排clock合法化；未放宽Oracle。后续32方法通过，再补2个互异/FAULT边界方法，冻结前34方法通过。原始初次输出在工具console，私有摘要明确初次raw文件/PID捕获UNAVAILABLE，不伪造。冻结后源码/fixtures零改。

正式原命令两次34方法exit0、0 failure/error/skip；--help实际执行，generate创建新streams，再每个case单独新CLI：5 exit0、8语义违规exit3、1不完整exit4。8结构变体各新CLI exit3，互异、非no-op。seq/previous/session/domain/role为结构拒绝；删除UNKNOWN、重排且重算chain/time、删除尾帧为REGISTERED_CASE_ROOT来源拒绝，不混称语义拒绝。预注册联动重锚违规case以有效Source根被Oracle真正判UNKNOWN_PROVIDER_RESERVE，属语义拒绝。原始/缺失/错误锚实际0/2/3。全部28个子进程（两tests、help、generate、14case、8结构、2锚）PID/UTC/monotonic/exit/日志SHA与reason在诊断，未以PREPARED计成功。

## 源与信任边界

5源raw/LF/blob、fixtures SHA及19只读依赖blob见SourceMap；病例原字节和8变体全记录在counterexamples，可对固定roster复验。Source-root若与流一起被共谋替换，仅自签hash不能检测，输出始终标UNPROVEN_SOURCE_AUTHENTICITY；不宣称第三方Issuer/原生WAL真实性。NO_VIOLATION非SAFE总判定，不证明物理不发包/费用为0/业务真实幂等。预算充足为fixture假设，不是本轮原生额度验算。

## 方案比较与下一决定

方案1：claim_slot入口锁存，早于reserve，简单但进程内状态丢失/原子性未证。方案2：单原生WAL持久可重放UNKNOWN Gate，需新ABI/恢复/并发写前检查测试；禁止本轮修改旧WAL。方案3：宿主无模型只读对账后终止，不另申请Explorer/Target票，代价是跨域后续机会被放弃、可能INCONCLUSIVE。并发读改写、崩溃窗口、实体launch/receipt、物理发送/真实Authority均UNPROVEN，不推生产安全。

RPF74/rev4持续PAUSED，原实现未修；恢复需新授权Plan，不因本轮抽象合同通过解锁旧账本。RPF78/rev1 A08仍FAIL，rev2时序PARTIAL不被新G0覆盖。真实R-01～R-10/双Agent/Web/因果/签发者/比赛/部署均未升格；TASK_COMPLETE/EVIDENCE_ACCEPTED/STAGE_ADVANCED保留Architect裁定。

Provider/token/费用/SDK/JVM/HTTP业务/数据库/Docker/browser/Web均0，无Key读取或存在性探测，无旧.local访问、marker清理或reviews访问。只标准库/Git，180秒子进程上限、串行峰值2；CPU/I/O/连续OS采样UNAVAILABLE，wall不充CPU。13 CREATE_ONLY、0M/0D、无PR/main merge/force/amend/tag/release/deploy/workflow_dispatch。最终Git/API双读和清洁工作树由聊天补收据。
