# RunProof EffectWitness｜项目迁移入口

> 版本 **MIGRATION-2026-10-29-RPF79-rev1**；2026-10-29分支迁移资料，非canonical Project State、非main合并。CURRENT STATE按固定SHA和报告核验；TARGET INTENT保留批准需求；PLANNING CONTEXT不构成执行许可。
>
> 最高明确已接受离线阶段：**RPF-77**（75～77的接受来源为RPF-79正式Plan带入的上一Architect结论，不是本轮重新裁定）。**RPF-78：PARTIAL / PENDING_ARCHITECT_REVIEW**；**RPF-74/rev-4：PAUSED**。先审78再决定修订或下一方向。main=`bda0cd49e50e3181f604324e94877a24b9885334`，迁移Base=`240dbae75cc70f142c7c37a2a3994085063d7ccc`；最新未审查78=`d86528e9927ea2cd7a401da4865829c5a14bfcd2`。证据与验收分开，细节见10/14及SOURCE_EVIDENCE_INDEX.json。

## 使用顺序

上传17份新版Markdown并替换旧同名版本（05有两个文件），不要把ZIP视为自动上传。用户另行将06全文复制到Project Instructions；15是新聊天首条可复制Prompt。先读00/01/02/03/06/07/08/10/12/13/14，按需04/两个05/09/11。

## 产品与不变量（TARGET INTENT）

RunProof EffectWitness是Agent Reliability & Release Engineering研发方向，核心Proof-Guided Exploration：真实受限Explorer依据Execution / Effect / Experiment三份冻结合同选择合法故障实验，真实Target在受控沙箱产生副作用，独立Authority/Oracle读取可信事实，Verified Feedback进入后续选择，输出有界、可离线验证的Witness Certificate。订单/退款与运维/配置变更首发，Desktop Web为主要人类体验；追求可重用基础设施。

01/02/03完整保留R-01～R-10、MUST/SHOULD/NON-GOAL与D-COMP原义。未实现目标不能删除或降级。LLM不持有业务真值、Verifier或Release Authority。UNKNOWN_OUTCOME后禁止盲重试写，依合同确定性只读对账；74的新更强“零新provider预约”不变量尚未修复。故障planned/triggered/observed/agent_exposed、结果满足/违规/未知分栏；Hash和自签Source Identity不等于第三方签名、独立Issuer、因果统计证明。离线复核同一证书不等于独立新环境复现。
## CURRENT STATE与下一审查入口

本轮只执行文档整理。远端RPF-40～78共39个报告按其各分支完整SHA定向读取，未运行它们的业务/Provider/Verifier。75～77的正式接受由RPF79 Plan带入；这些报告在Evidence commit之前封存为Partial/A10待交付，现有远端最终commit与其内容可读，不能改旧报告。65～73等历史报告的COMPLETE属于原Codex交付声明，本轮不凭报告代替Architect接受或新复跑。

[RPF-78 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/d86528e9927ea2cd7a401da4865829c5a14bfcd2/spikes/rpf-78/RESULT.md)：冻结后106方法×2，各exit1/1 error；oracle-stop对MUST_STOP重复赋值引发TEST_INVALID_NO_OP。58有效CLI负控拒绝、含8组合，另1无效项不计通过。A08=FAIL；A10报告封存NOT_RUN但源/证据提交已在远端，交付完成不能抵消A08。

78仅24 fit/48标签拟合，12 validation、18作者已见challenge；validation/challenge Brier0.226581/0.262951，支持10/15与27/44；bounded challenge净25、漏选8、过探3、拒绝10、成本27/事实6、局部机会成本63；point/v3/B0净47/65/94。低支持/未见桶/过期降级，不能声称真实校准、95%覆盖、外部盲测或全面优势。详见其evaluation-report.json与counterexamples.json（同SHA路径，先核对）。

[RPF-74 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/d5605c08af33c932f97529ae5b33228b56d8a113/spikes/rpf-74/rev-2/RESULT.md)目录虽为rev-2，正文Plan revision=rev-3；Config UNKNOWN seq199后仍provider RESERVE205/233，Order UNKNOWN427后仍RESERVE433/461。Explorer独立response ID和物理launch-receipt字节绑定仍有缺口；rev4草稿PAUSED，无授权重启、删除marker、重写WAL或补签。rev1报告为Partial，A03/A06为FAIL；不能把Gate失败误写成任务状态FAILED，也不能冒充已修复。

[RPF-77 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/240dbae75cc70f142c7c37a2a3994085063d7ccc/spikes/rpf-77/RESULT.md)：30 development＋18作者已见challenge＋3旧诊断；121方法两次、78/78 CLI（历史报告值，本轮NOT_RUN）。v3新challenge漏选1、过探1、合成事实4，相比v2事实12；启发式效用不等于未来真值。75～78均为合成离线，不代表真实双Agent/Web/Issuer。

下一动作：新Architect先独立读78源码、RESULT/诊断与远端Git交付，审查测试fixture失败、拟合/评价分离、拒绝机会成本；再决定rev2或其他有信息价值方向。本包不自动创建修复Plan、不恢复74，也不指定“下一步RPF65”。

阶段导航见10，精确SHA/URL见14和SOURCE_EVIDENCE_INDEX；RPF79迁移完成与Architect接受仍分别核对。
