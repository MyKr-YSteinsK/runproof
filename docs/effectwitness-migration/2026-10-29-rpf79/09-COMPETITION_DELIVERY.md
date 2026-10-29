# COMPETITION DELIVERY｜完整迁移版

> 版本 **MIGRATION-2026-10-29-RPF79-rev1**；2026-10-29分支迁移资料，非canonical Project State、非main合并。CURRENT STATE按固定SHA和报告核验；TARGET INTENT保留批准需求；PLANNING CONTEXT不构成执行许可。
>
> 最高明确已接受离线阶段：**RPF-77**（75～77的接受来源为RPF-79正式Plan带入的上一Architect结论，不是本轮重新裁定）。**RPF-78：PARTIAL / PENDING_ARCHITECT_REVIEW**；**RPF-74/rev-4：PAUSED**。先审78再决定修订或下一方向。main=`bda0cd49e50e3181f604324e94877a24b9885334`，迁移Base=`240dbae75cc70f142c7c37a2a3994085063d7ccc`；最新未审查78=`d86528e9927ea2cd7a401da4865829c5a14bfcd2`。证据与验收分开，细节见10/14及SOURCE_EVIDENCE_INDEX.json。

## 当前适用规则

竞赛与研发双轨。11/10、ZIP≤500MB只作为RPF61 OFFICIAL_PORTAL_CHECK的2026-10-21历史现场记录，不是2026-10-29新独立门户核验；本任务不访问外网门户。用户登录后的精确时刻/字段/条款/提交回执UNVERIFIED。本迁移ZIP用于Project交接，不是比赛提交包。PPTX/MP4/最终赛事ZIP/门户上传没有新完成证据。


## 原合同与历史参考全文（HISTORY_2026_10_22）

> 下列旧快照中的“当前/下一轮/RPF65未实施”只描述2026-10-22，不与上方当前事实并列生效。稳定产品/安全/实验/UX约束继续有效；旧示例不构成重跑或越权许可。

> # COMPETITION DELIVERY｜首届 openJiuwen 智能体创新大赛（迁移更新 2026-10-22）
>
> > **规则版本边界：** V5 孵化期旧公告曾显示 2026-10-30/10-31；RPF-61 在 **2026-10-21** 实际读取新版 openJiuwen 官方公告和华为云 PC 提交页面，记录提案截止 **2026-11-10**、**ZIP ≤500MB**。本次 2026-10-22 公网再查仍有旧英文缓存公告显示10-30、最新版中文正文无法直接从公共文本访问器取得。因此这里把 11-10/500MB 标为 **RPF-61 现场核查记录，需用户登录时复核精确时刻与最终要求**，绝不混称本次独立二次核验成功。
>
> ## 1. 竞赛身份、入口和日期
>
> - 名称：**首届 openJiuwen 智能体创新大赛**；作品名建议门户字段：**RunProof EffectWitness**，副标题“智能体行动副作用验证”。原 RunProof 公共仓库竞赛升级，不是新建独立产品仓库。
> - 官方赛事更新：[https://openjiuwen.com/news/news-artical?id=248](https://openjiuwen.com/news/news-artical?id=248)；PC 作品提交：[https://developer.huaweicloud.com/competition/information/1300000328/submission](https://developer.huaweicloud.com/competition/information/1300000328/submission)。
> - **RPF-61 记录的当前初赛创意提案截止：2026-11-10（日期级）；附件 ZIP≤500 MB；评审预计 2026-11-25 前；创意入围后 DEMO 开发。** 精确终止时刻/时区、登录后的必填字段、组队/实名认证、次数和最终知识产权/CLA 勾选内容以当前门户实际显示为准。
> - 历史旧英文公告仍可检索到10月30日/11月15日，不能无版本说明就与新版当前规则混用。内部仍希望在 10-30 前准备完毕，但它不代表当前官方截止。
> - 官方公告中的模板 URL 为 RPF-61 记录（尚未检验模板内容）：[中文创意 PPTX 模板](https://gitcode.com/user-attachments/files-group/9307451/92e19ad1e34948418fca9a0d5b712ada.pptx)、[English PPTX](https://gitcode.com/user-attachments/files-group/9307451/2b31df4f73774db8a515338e9b9b7eb2.pptx)、[FAQ PDF](https://gitcode.com/user-attachments/files-group/9307451/120c8629644844b888f6cea4aa7112e3.pdf)。需用户自行查证文件内容及许可证/条款。
>
> ## 2. 截至迁移的**实际已交付**与尚欠用户动作
>
> 已完成 RPF-61 材料分支 `codex/rpf-61-proposal-submission-evidence-package@c5ebfb887336ca67b61270df9965f6b1ebbf2b9a`，对应新源 `spikes/rpf-61/README.md`, `SUBMISSION.zh-CN.md`, `SUBMISSION.en-US.md`, `CLAIM_EVIDENCE_MATRIX.md`, `OFFICIAL_PORTAL_CHECK.md`, `DEMO_180S.md`, `REPRODUCIBILITY.md`, `SUBMISSION_CHECKLIST.md`, `PACKAGE_MANIFEST.json` 与四张来源核查 PNG。
>
> **未完成：** 官方 PPTX 模板填稿、最终可上传 ZIP、视频文件 MP4（是否当前初赛必需尚不确定）、用户实名/组队/协议阅读与接受、最终门户上传、成功回执、提交作品编号。`USER_SUBMISSION=NOT_RUN`；任何提交前必须保存**平台成功回执+时间+附件 SHA**，不能凭 Git push/登录成功推导已经交付。
>
> 此次迁移不替用户创建赛事 PPTX/ZIP，也不授权第三方登录/提交。新对话可按用户请求提供模板填稿/演示材料，但不能把其误写成研发证据。
>
> ## 3. 作品正确技术叙事（可复用申报事实）
>
> 产品定位：面向会调用工具并改变有状态业务的 Agent，测试其**实际行动效果**。`Execution / Effect / Experiment` 三份合同冻结权限、业务不变量、实验预算；真实 Explorer 从受控候选中选择，Target 在受控业务环境中执行，确定性 Oracle 读取收据/配置状态并将**验证过的反馈**回注，输出可按外部 SHA 离线校验的 Witness。订单/退款与运维/配置变更已在同一共享调度、账本与 Port ABI 中执行（RPF-64）。
>
> 必须用**不同证据源**描述：
>
> | 来源 | 能证明 | 不得宣称 |
> |---|---|---|
> | RPF-57 | 配置真实双角色两轮，观察性 L2=true | 因果优越、统计领先、生产服务 |
> | RPF-60 | 真实浏览器→Gateway→真实 Explorer→订单/配置两个受控 Target→Witness | 此会话两 Target 都是真实 LLM；被抑制故障激活 |
> | RPF-62 | 真实配置 Target HTTP200/Tool UNKNOWN 后实际只读恢复 | 本轮有 Explorer/跨域 Web |
> | RPF-63 | 同一配置域会话真实 Explorer×真实 Target 两轮，故障确实触发 | 本次 L2=true；或已接入 RPF-60 Web |
> | RPF-64 | 新 TaskContext/DomainPort 同时跑订单真实 SQLite 和配置 Java/H2 SDK Fixture；0 Provider | 新的双真实 Agent 或广泛动态第三领域 |
>
> 不得将多次 Session 剪辑成一次运行，不能把 `SYNTHETIC_TEST_ONLY` / `FIXTURE_SCRIPTED` / `REAL_LOCAL` 升级成 `REAL_PROVIDER_TARGET`。`UNKNOWN_OUTCOME` 不等于业务失败，故障激活不等于违规；Issuer 真实性/独立复现/因果优势仍未证明。原源功能分支**未合并 main**，应给可固定访问的 feature commit URL，不只给 main 链接。
>
> ## 4. 视频和评委体验
>
> - 当前可用的 180 秒**分镜/讲稿**位于 RPF-61 的 `DEMO_180S.md`，不是 MP4 录屏；四张图属于以往 LIVE RUN 的**录制证据**，此刻呈现时标 `RECORDED/REVIEWED`。
> - 三分钟演示的重点：行动是否真的影响业务、未知结果安全停写和读回、权限/预算、两域差异、Witness CLI，最后明确限度。真实发生的失败/未触发如实展现，不承诺必须出现业务漏洞。
> - Web 旧 `zh-CN/en-US`、State Diff、Timeline、deep links 保留；控制 API 不可用 fail closed。RPF-63/64 的新内容若未接入 Web，需以明确标记的已记录证据展示，不将其伪装为 RPF-60 的新 LIVE 状态。
> - 视频如在正式阶段要求，长度 ≤180 秒，以最终赛事规则为准；不能因为视频仅为后续要求就永久搁置产品 UX。
>
> ## 5. 提交前用户清单
>
> - [ ] PC 登录华为云实际 `submission` 页面，核验**2026-11-10 的具体截止时刻/时区**、最后可改稿与提交次数。
> - [ ] 确认个人/团队身份、实名认证、规则和知识产权/可能获奖开源/CLA 条款，用户自行决定同意。
> - [ ] 下载并检查官方 PPTX 模板与 FAQ，核对初赛字段、大小、是否需要代码链接/视频，按官方格式准备，不直接把 .md 改扩展名。
> - [ ] 使用 RPF-61 文案和证据矩阵准确填写；需要说明现有真实双角色/双域能力时分清 RPF-63、RPF-64 的不同等级。
> - [ ] 制作 ZIP，检查 ≤500MB、SHA-256、解压后文件/字体/图表完整，不上传密钥、本地 `.local` 私密账本/个人信息。
> - [ ] 用户亲自完成最终上传/确认，保存成功回执、提交编号和最终文件 SHA。只有这一步才能从 `NOT_RUN` 变为 `SUBMITTED`。
>
> ## 6. 与下一步研发的关系
>
> RPF-65～后续研究仍有空间：真实 Target 接入新共用 ABI、更多状态/故障、跨域双真实角色、更强测试、MCP/API 接入、Web 新体验。比赛提交与研发**两条并行工作线**。重大扩权或赛事实质承诺交由用户决定；不为了凑高分启动高成本无界 Benchmark。获奖不是工程 PASS Gate，未获奖不降低已验证代码与简历证据。
