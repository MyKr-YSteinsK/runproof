# CURRENT_STATE

> 2026-10-30 可核验快照。稳定产品合同见 PROJECT_BRIEF，长期决定见 DECISIONS，执行规则见 AGENTS，历史事实见 docs/history 与各固定 SHA 的 RESULT。本文不授予旧实验恢复权限。

## 当前阶段与工作模式

- RunProof 持续研发；本轮 RPF-82 是 repository integration / governance maintenance，不是项目结束或生产发布。
- 用户已接受 main-first、现有单工作树的常规协作方式（D-028）。G0、用户文件保护、必要验证及 CI 仍然有效；高风险/真实费用/并发/污染实验须另行提出隔离。
- 仓库为 public `MyKr-YSteinsK/runproof`，默认分支 main。旧 main 基线为 `bda0cd49e50e3181f604324e94877a24b9885334`；本地先快进研发链 `8c22556f56b088ecae641c96cb9ab8bba6af1c05`，再显式合并 RPF-79 `f123ae13f67b3825c094e3bb7764c348a393b19d`。治理提交的最终 main push/API/CI 回执在 RPF82 最终聊天提供；本文封存时不预填未来 SHA。
- 原有分支和 worktree 保留，未清理旧本地根。RPF-81/rev-2 BLOCKED 工作树及 G0 失败现场没有并入或恢复；仅其 Base 历史可达。
- 无 product tag/release；Production Cloud 仍 Deferred，AWS candidate topology 未变为部署或真实资源授权。

## 能力与证据层级

| 层级 | 当前事实 | 证据及限制 |
|---|---|---|
| RPF-00～39 正式受控产品切片 | 历史已完成；Desktop Web 双语 API-backed read-only 调查、Java/PostgreSQL canonical metadata、Python durable Worker、质量门和 Golden Demo | 沿用 docs/history；本轮不重造 reviewed artifacts，不把历史通过记为本轮实跑 |
| RPF-28/30/32/34/35 边界 | 多服务受控环境、optional OTel、显式 additive S3-compatible ArtifactStore、bounded read models | 原风险扩展/manual 边界仍有效；非 Production HA/云/发布证明 |
| RPF-40～73 研发链 | EffectWitness、订单/退款与运维配置、受限 Gateway、Witness/Verifier、PGE 与版本化接缝的源码及公开报告已纳入授权历史 | 各 RESULT 持有具体环境/版本/失败与接受限制；历史真实 Provider/SDK/HTTP 记载未在本轮重跑，不能概称全部能力已接受或默认启用 |
| RPF-75～77 离线策略研究 | 先前 Architect 的限定离线接受，RPF-79 迁移快照明确记录 | OFFLINE_POLICY_SIMULATION_ONLY；不证明真实策略优越性、真实校准或新业务安全 |
| RPF-78/rev-1 | PARTIAL；A08 FAIL 永久保留 | 原报告不回填。rev-2 负控门禁修订的公开证据已交付，封存报告仍 PENDING_FINAL_DELIVERY，不在本轮补授新的阶段接受 |
| RPF-79 迁移资料 | 独立历史的21份文档/manifest/index已与研发链合并 | docs/effectwitness-migration/2026-10-29-rpf79 为带日期的非 canonical 快照，不替代三份 Project State |
| RPF-80 | 限定合成投影/独立离线 Oracle 证据已被 Architect 接受（RPF82 Plan 带入） | 只证明投影规则，物理发送/真实 Provider 未证；原封存报告的 pending 状态不改写 |
| RPF-81/rev-1 | PARTIAL；localhost 正常字节、阻断、固定交错与负控有局部实证 | A05 恢复因果不足：无 UNKNOWN 的重启也被无条件拒绝；历史累计7次sendall/320接收字节，不是本轮运行 |

## 暂停与未修安全事实

- RPF-74/rev-4：PAUSED/DEFERRED。公开 rev-2 路径中的 rev-3 报告仍 PARTIAL：Config UNKNOWN seq199 后有 provider RESERVE205/233；Order UNKNOWN427 后有433/461。原私有 WAL/marker/receipt 未读取，未修复、未重放。
- RPF-81/rev-2：BLOCKED。G0 原始收据持久化缺口；Source 修改/实验/commit/push 为0（本 Plan 带入的上轮事实）。恢复和反复补证路线按当前用户决定延后，不能以 main-first 绕过。
- UNKNOWN_OUTCOME 后禁止业务盲重试写，只允许按合同确定性只读对账。main 包含历史不安全研究候选，不能当作批准执行；已有安全缺口没有被本轮集成清零。

## 验证与交付事实

- RPF82 G0 在现有 tracked-clean 主工作树完成；prewrite stdout 原始收据先落盘，再 fetch。main 不被其他 worktree 占用，工作流锚与三来源一致。
- main→RPF81 为126个提交的快进；RPF79相对RPF81为 ahead2/behind8，显式 merge 后迁移21文件和 AGENTS 追加保留。完整本地 Git diff 审查覆盖831个研发变更路径，未以 API 前300项代替；72个 RPF40～81远端分支 HEAD 都在两条固定历史中可达，细项见 integration ledger。
- 本地检查的实际 exit、日志hash、NOT_RUN/UNAVAILABLE 见 spikes/rpf-82/verification-diagnostic.json；未执行项不记 PASS。RPF81测试/旧完整Runtime若触碰旧私有根则不运行。
- canonical `.github/workflows/release-gate.yml` 在旧main/两来源 blob 均为 `99aee95819cf1e2ea41b0bcfe68b3444730c6ba9`，无工作流变更、无新增权限。main push 自动触发依赖安装、Docker/PostgreSQL/Runtime/Maven/Web CI，已获本次授权；不执行 deploy/release，实际计算费用 UNAVAILABLE。
- 推送前完整历史diff检查发现3处继承的whitespace问题（两个EOF空行、一个trailing whitespace），历史blob原样，用户已明确仅豁免这3处继承空白，原exit2诊断保留；新增差异检查通过。封存时本次治理提交尚待最终 push 和 hosted CI；A06/A07 为 PENDING_FINAL_RECEIPT。CI 实际状态由最终聊天独立补证，不 amend 旧报告。本次外部模型 API/Provider/token/费用/SDK/业务写/实验TCP均0（Git/GitHub只作交付/读回）。

## 产品目标与剩余限制

- 长期仍需真实 constrained Explorer→受控真实 Target effect→独立 Authority/Oracle→Verified Feedback→有界离线 Witness Certificate；订单/退款与运维配置为两个首发 Domain，Desktop Web 为主要人类界面。本次不修改稳定产品合同，不将资料迁移或离线 L0 升格为 live。
- 未实现或未授权边界仍包括独立 Issuer/真实业务 Authority、完整反馈因果优势、通用并发/硬件断电保证、Production HA、多主机监督、OAuth/OIDC/SSO、tenant/RBAC、broker/scheduler/autoscaling、真实 destructive remediation 及发布端点。ELIGIBLE 仍是 decision-only。
- reviewed bytes、canonical identity 与 Release Authority 不由 OTel、Hash、Agent 文本、Mock 或同证书重审替代；LocalFileArtifactStore 默认和 S3 单节点兼容性限制不变。
- 旧 README 的 feature-branch 描述与迁移资料持有当时快照；当前已集成路径以本文/RPF82 ledger 为准。旧正文按本轮保护规则保留，后续可在独立文档范围内更新导航。
- 本轮无真实设备/UI验收、无新的性能或生产概率结论。Web 仍可能有已知共享 chunk 警告；未据此升级依赖。

## 下一工作边界

常规研发继续在 main 的单工作树按有界授权推进；以未完成产品目标与当前证据差距选取小任务。旧 UNKNOWN 恢复路线延后为单独研究，不自动创建新 RPF/分支/worktree或恢复暂停现场。生产、真实费用、部署及高风险隔离始终需要相应明确授权。
