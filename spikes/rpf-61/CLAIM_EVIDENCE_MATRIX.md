# Claim → Source → Boundary

核查日期2026-10-21。所有实现/证书URL固定在 `1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8`；当前材料不把feature能力计入main。下表“通过”是限定证书内容复核，不是独立重做业务。

## 核心主张逐条追溯

| ID / 可使用表述 | 原始来源 | 可证明内容 | 必须同列的边界 |
|---|---|---|---|
| C01 原RunProof平台的竞赛增强 | [产品合同](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/docs/project/PROJECT_BRIEF.md)、[原App路由](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/web/src/App.tsx) | Agent Reliability & Release Engineering与既有Desktop Web | 没有新建独立产品仓库，没有生产部署 |
| C02 浏览器真正发起一次跨域会话 | [UI诊断](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/ui-diagnostic.json)、[Gateway诊断](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/gateway-diagnostic.json) | request_id `9cd8a718-05d3-494a-a463-5a0e440aaa7c` 的前端POST202，Session `rpf60-session-ff259b8d1bef494b` | 历史已完成；本包截图展示属于RECORDED，不能重置配额 |
| C03 Explorer受限自主选择 | [RPF60 Witness](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/cross-domain-live-evidence.json)、[固定合同](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/runtime/runproof_runtime/effectwitness/lab_cross_domain_contracts.py) | 实际真实DeepSeek两轮选择order→config；select_experiment只有固定候选 | 未记录自由理由；变化不证明反馈因果作用；不是两个真实LLM Target |
| C04 订单Effect可核验 | 同上Witness；[静态Port/领域Oracle](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/runtime/runproof_runtime/effectwitness/lab_cross_domain.py) | Run `rpf60-order-da9b1127b5424628`，2500分完整退款、revision1、唯一收据；SQLite只读Reader分离 | fictional业务、确定性Target；Reader在本机同信任环境，不是生产支付或第三方认证 |
| C05 配置Effect与故障事实分栏 | 同上Witness、[会话摘要](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/session-summary.json) | Run `rpf60-config-2e979367c8d54805`，真实SDK scripted Fixture+Java17/H2，8 HTTP/2 POST，v2/history[2,1] | SAME_SERVICE_READ_ONLY_HTTP，非数据库外部Authority；planned=true/triggered=false/observed=false，NOT_TRIGGERED |
| C06 三合同与一个有界账本 | [合同](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/runtime/runproof_runtime/effectwitness/lab_cross_domain_contracts.py)、[Ledger/TaskGuard](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/runtime/runproof_runtime/effectwitness/lab_cross_domain.py)、Witness | Execution/Effect/Experiment版本身份，Provider与领域资源先预约后执行；83帧/82事件 | 合同只覆盖固定受控候选，不是任意任务/MCP执行；取消不回滚已提交业务 |
| C07 新Witness可独立离线检查 | [确定性Verifier](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/runtime/runproof_runtime/effectwitness/lab_cross_domain_verify.py)、[原验收记录](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/verification-diagnostic.json) | 原件1,069,226 bytes，源/Verifier身份、外部锚、领域事实与账本检查 | 独立指验证程序；hash非Issuer签名，重验同份文件非独立复现 |
| C08 反馈先于下一轮输入 | RPF60 Witness的rows/input/feedback与ledger_chain；[RPF59独立会话](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-59/cross-domain-selection-evidence.json) | 各自Session中首轮核验后反馈、随后次轮输入冻结 | RPF59与60是两场；无公平对照/统计或因果优势，跨域事实数不可相加为信息增益 |
| C09 配置域真实双角色及观察性L2 | [RPF57 Witness](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-57/config-pge-coverage-evidence.json)、[原报告](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-57/RESULT.md) | Session `rpf57-session-3ee4ca3412394b0a`；真实Explorer+真实Target，inhibited→local-delivery-suppressed，新增ack_unknown_reconciled/delivery_suppression_observed | `L2_OBSERVED_INFORMATION_GAIN_IN_THIS_RUN`；本地工具结果抑制非TCP丢包；业务违规未证明；不是RPF60镜头 |
| C10 共享内核双域受控验证 | [RPF58 Witness](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-58/rev-2/cross-domain-portability-evidence.json) | 同一共享Session/Ledger执行订单/配置，0Provider，静态领域Port | 订单确定性/配置SDK Fixture；不是自主Explorer选择 |
| C11 低费用的一次具体样本 | RPF60 Witness与摘要 | Provider2，prompt1254/completion86/total1340，保守估算CNY0.007191；6000tokens/CNY0.108不可退款预约 | 非账单、价格承诺、吞吐基准或一般费用保证；RPF59是1332tokens，不混用 |
| C12 未知结果停写与只读对账 | [RPF57真实抑制/对账](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-57/RESULT.md)、[RPF60离线测试](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/runtime/tests/test_effectwitness_lab_cross_domain.py) | RPF57实际update提交后抑制Tool回注并GET-only reconcile；RPF60未知预算/写路径有测试 | RPF60本次真实会话没有UNKNOWN，测试情形不能冒充真实故障发生 |
| C13 双语、深链及失败关闭 | RPF60 ui-diagnostic、App与新CrossDomainPage源码 | 原验收记录zh/en、Timeline/State Diff、事件e20、Gateway不可用不伪成功 | 本任务不重跑Web/Runtime；canonical后端当时未运行，API unavailable不等于后端在线PASS |
| C14 竞赛生态兼容的后续方向 | [既往技术调查](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-40/RESULT.md)、当前固定源码 | 可继续研究受限框架接入 | 当前没有JiuwenSwarm/WorkSwarm主执行框架集成；不填写“已集成” |

## 四份证书的不可混淆身份

| 证书 | source_kind / Agent等级 | 本次离线结果 | raw SHA-256 |
|---|---|---|---|
| RPF-57 | REAL_EXPLORER_REAL_TARGET_CONFIG_JAVA_HTTP | exit0；公开链接HTTP200 | `76dd7077d75e6dd8ad319bb6e17a01209faadee9fe94d276f3b85e73e88abbe7` |
| RPF-58 | BOTH_REAL_CONTROLLED | exit0；公开链接HTTP200 | `03aa9ac84f725de982b537a8882b27b764aaf6da9868b9a65a2cdcfd6e4d208d` |
| RPF-59 | REAL_EXPLORER_CONTROLLED_TARGETS | exit0；公开链接HTTP200 | `0bb359ca78c7c0415afef30ff959d41112da3f5155e5ae18e68be28735f9996a` |
| RPF-60 | REAL_EXPLORER_CONTROLLED_TARGETS | exit0；公开链接HTTP200 | `81422d26a6ea1406d66d73fecfe0a98a09310a81812faf84e95ed896679b8df9` |

RPF57、58、59、60的当前原件均在固定功能快照中；没有复制原件到本材料包。源Verifer SHA与文件大小见Manifest。RPF60当时运行的source digest=`3402428d659a5140d8c90a108a59142b78b0beba2d6de7d2e4c9a3ce967e0ada`。

## 阶段收口：R-01～R-10

当前可读canonical PROJECT_BRIEF没有落地这十个编号的完整逐条定义；RPF40原报告也记录Bootstrap未落地。本Plan只明确点名R-08。为保护需求，不根据宣传稿自行替其他编号命名或宣布达成。下面的NOT_REASSESSED是编号对照缺口，不否定既有能力。

| 原编号 | 本包判定 | 截止前行动 |
|---|---|---|
| R-01 | NOT_REASSESSED：原条文不可得 | Architect补原编号→条文对照；勿填全部达成 |
| R-02 | NOT_REASSESSED：原条文不可得 | 同上 |
| R-03 | NOT_REASSESSED：原条文不可得 | 同上 |
| R-04 | NOT_REASSESSED：原条文不可得 | 同上 |
| R-05 | NOT_REASSESSED：原条文不可得 | 同上 |
| R-06 | NOT_REASSESSED：原条文不可得 | 同上 |
| R-07 | NOT_REASSESSED：原条文不可得 | 同上 |
| R-08 | LIMITED_IMPLEMENTED：真实受限Web Lab | 使用C02～C08及C13；非通用生产服务 |
| R-09 | NOT_REASSESSED：原条文不可得 | Architect补原编号→条文对照 |
| R-10 | NOT_REASSESSED：原条文不可得 | 同上 |

无需等待编号治理补齐才能提交当前有证据的创意提案，前提是表单不要求逐项已实现声明。现阶段没有发现必须改产品代码才能完成本包的阻塞。

**提交前阻塞**：用户确认11月10日精确时刻/时区与登录后字段、知识产权及身份；按官方PPTX模板整理并打ZIP≤500MB。本Plan只交文本/PNG，PPTX/ZIP由用户或后续授权补齐；若系统另需MP4亦须补齐。**可延期**：新付费实验、生产接入、真实Target扩展、公平对照、Issuer签名、框架集成、main合并、视频精修（仅在当期不要求时）。未知要求不得自动列为不需要。
