# RunProof 与个人作品组合评审

**2026-11-23 · 待用户评审。** 核对了 `MyKr-YSteinsK` 账号可访问的自有仓库清单和各仓库 README，对 RunProof 做仓库审查，对 `config-center` 下钻到固定提交的 API、DTO、部署与测试文档。以下公开文档以可公开项目为依据。功能描述来自仓库；本轮只有 RunProof 做了新的聚焦执行验证。[GitHub 主页](https://github.com/MyKr-YSteinsK)

## 建议的简历组合

1. **RunProof 做 Agent 主项目。** 面试先展示一条受控配置故障的端到端运行，再展开策略决策、typed tools、人审、只读对账、可验证证据和回归比较。RPF-114 可先作为所做机制的可信本地示例。[现有验收](../../spikes/rpf-114/RESULT.md) · [待评审升级](UPGRADE_REVIEW.md)
2. **config-center 做后端深度与实际目标。** 展示版本、回滚、并发保护、长轮询、MySQL/Flyway 和 Java 客户端降级。联动后，两个仓库各自可运行，共享一组故障案例与证据链接，面试可以深入谈服务契约和 Agent 工具行为。[config-center 状态与验证](https://github.com/MyKr-YSteinsK/config-center/blob/0258b9cef02ea74a40989d035c79256c776409c0/docs/project/CURRENT_STATE.md)
3. **CareerSim 做第二个 Agent 能力案例。** 已冻结的 `candidate-v6-auditable-control-loop` 是 Single Agent + 3 Skills，侧重任务策略、对照与证据取舍。用一个失败案例讲决策过程，即可与 RunProof 的副作用验证形成互补。[CareerSim 工程与报告](https://github.com/MyKr-YSteinsK/CareerSim-BDCI26)
4. **按岗位取一项补充。** 后端或开发者工具岗用 MyKr-ops 展示本地文件操作的预检、确定性和用户可控性。全栈岗用 Myriad Atlas 证明内容校验、静态编译和离线 PWA 交付，或用 Bangumi Side B 讲数据治理和可访问站点。数据/研究岗准备一份明确区分数据可用性、复现实验与外部验证的案例。[MyKr-ops](https://github.com/MyKr-YSteinsK/MyKr-ops) · [Myriad Atlas](https://github.com/MyKr-YSteinsK/myriad-atlas) · [Bangumi Side B](https://github.com/MyKr-YSteinsK/bangumi-side-b)

## 公开仓库速览

| 仓库 | README 和可查证的侧重点 | 作品中的位置 |
| --- | --- | --- |
| RunProof | 有状态评估、独立副作用验证、证据与 Release Decision | Agent 主项目，优先跑透单条闭环。[仓库](https://github.com/MyKr-YSteinsK/runproof) |
| config-center | Java/Spring 多模块；版本、Watch、ETag、Flag、回滚与客户端韧性 | 实际联动目标及后端项目，说明 H2 与 MySQL 的证据范围。[仓库](https://github.com/MyKr-YSteinsK/config-center) |
| CareerSim-BDCI26 | 可审计单 Agent + 3 Skills，冻结历史 v6 及方案评估 | 第二 Agent 项目，说明策略候选、失败和最终选择。[仓库](https://github.com/MyKr-YSteinsK/CareerSim-BDCI26) |
| MyKr-ops | Windows 本地确定性笔记整理与批量重命名 | 工具工程，提炼预检、幂等与明确反馈。[仓库](https://github.com/MyKr-YSteinsK/MyKr-ops) |
| Myriad Atlas | Markdown 校验、内容编译、静态站与离线阅读 | 全栈面补充，可直接查看使用体验。[仓库](https://github.com/MyKr-YSteinsK/myriad-atlas) |
| Bangumi Side B | 数据核验、SQLite 与生成静态/PWA 页面 | 数据工程到产品交付的一条链。[仓库](https://github.com/MyKr-YSteinsK/bangumi-side-b) |
| Red Repeat | 音乐资料、库校验和 PWA 静态交付 | 产品与视觉补充，减少和其他 PWA 重复展示。[仓库](https://github.com/MyKr-YSteinsK/red-repeat) |
| Veil Archive | 移动端优先的本地 PWA、离线和恢复 | 本地优先工程补充，面试中可选一个 PWA 深讲。[仓库](https://github.com/MyKr-YSteinsK/veil-archive) |
| ACGN History Analyzer | 个体记录、标签与 LLM 辅助分析 | 有稳定用户任务和数据时可做只读工具实验，暂不并入 RunProof。[仓库](https://github.com/MyKr-YSteinsK/ACGN-History-Analyzer) |
| ACGN Works Tracker | Servlet/JDBC、MySQL、CSV、统计视图 | Java Web 学习演进的支撑材料。[仓库](https://github.com/MyKr-YSteinsK/ACGN-Works-Tracker) |
| Cervical MRI Research Lab | 数据准入、许可、完整性和受限研究协议 | 适合说明科研数据工程，按仓库状态限定结论。[仓库](https://github.com/MyKr-YSteinsK/cervical-mri-research-lab) |
| City Population Competition | 数据合同、预测候选、泄漏控制、阶段复现 | 岗位涉及数据可讲实验纪律，仓库状态仍保留提交缺口。[仓库](https://github.com/MyKr-YSteinsK/city-population-competition) |
| AI Workflow Assets | 孵化器、任务交接、工程规则和可复用 Skills | 支撑方法库，把工具与个人决策责任对应起来。[仓库](https://github.com/MyKr-YSteinsK/ai-workflow-assets) |
| Coffee Order Course Demo | JFinal 的用户、商品、订单和本地 demo | 课程记录，优先展示比 CRUD 更成熟的项目。[仓库](https://github.com/MyKr-YSteinsK/coffee-order-course-demo) |
| Anger_bird | Unity/C# 的教程练习，涵盖物理与关卡循环 | 兴趣探索，适合游戏或客户端相关场合。[仓库](https://github.com/MyKr-YSteinsK/Anger_bird) |

## 可以准备的面试材料

**现有证据支持的表述。** “实现了带独立 Controller 与 SQLite 权威读回的受控 Agent 工具执行原型。订单响应丢失后先验证业务收据，再基于核验反馈执行配置变更，导出可离线核对的结构化 Witness；同时验证错锚、篡改和无反馈时的拒绝路径。” 这一表述对应 RPF-114 的确定性本地运行，现场一键复现可选择其已验证版本。[RPF-114](../../spikes/rpf-114/RESULT.md)

**联动验证后的表述模板。** “为 Spring Boot 配置中心构建受控变更 Agent，提供版本前置校验、人工审批、UNKNOWN 对账与证据回放。固定的 N 个场景中，报告有效样本的任务完成率、重复副作用、未知结案率和失败恢复时延，并比较确定性与 LLM 策略。” 只在实际完成后填入 N、指标、环境、调用费用及相关证据链接。

**面试演示顺序。** 限时讲用户问题 → 跑一项配置变更并触发响应丢失 → 看证据及决策 → 用独立 CLI 复核 → 展示失败对照、下一项权衡和个人做过的设计。配一张架构图和一页回归结果。准备回答为何需要读回、业务幂等与乐观锁有何差异、哪些失败应归因给 Agent、何时需要后端持久化或复杂编排。

### 优先投入

1. 打通 [升级评审](UPGRADE_REVIEW.md) 的 M1/M2，使每条简历主张可连接到可复跑案例与某次经验证提交。
2. 录制短实测，保留干净启动和失败恢复流程；README 首屏给出当前能力、一步开始与一次可复现结果。
3. 为 RunProof 和 config-center 各保留两三项能讨论的设计取舍，准备真实边界数据和对应测试。把 CareerSim 的证据评估和单 Agent/Skills 设计留作第二项目。
4. 核对岗位方向再选择一项辅助项目。其他项目作为背景素材，待有真实需求时考虑联动。优先独立维护 `MyKr-ops`、PWA 和研究仓库。
