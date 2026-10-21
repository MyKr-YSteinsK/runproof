# TASK_RESULT · RPF-61

Plan ID：`RPF-61`；Revision：`rev-1`；日期：2026-10-21。
Status: Complete

## 完成范围与身份

已形成初赛创意文本包、英文等价稿、逐项Claim索引、官方入口核查、180秒分镜、零重跑复核手册、用户提交清单和带哈希Manifest。完成的是材料准备与限定证据审查，**没有提交比赛、制作MP4或重新执行业务**。

Root现场经 `git rev-parse --show-toplevel` 确认为既有runproof仓库；origin为 `https://github.com/MyKr-YSteinsK/runproof.git`。精确Base/原父HEAD `1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8`；父分支 `codex/rpf-60-cross-domain-live-lab-gateway-ui`；新分支 `codex/rpf-61-proposal-submission-evidence-package` 创建前未被占用。原main `bda0cd49e50e3181f604324e94877a24b9885334`。

初始tracked/index clean，唯一原有顶层条目 `?? docs/reviews/`；未进入、枚举、读取、移动、修改或暂存该目录。仅新增 `spikes/rpf-61` 白名单文件和最多4张图；旧Web/Runtime/Java/CI、全部历史证书、AGENTS、Project State、history、README/DEMO原字节保持。原运行根仅按本Plan精确截图例外读取四张PNG，没有查看其他旧local文件、凭据或账本。

## 交付导航与取舍

| 文件 | 内容 |
|---|---|
| [README.md](README.md) | 导航、功能快照、来源与权限 |
| [SUBMISSION.zh-CN.md](SUBMISSION.zh-CN.md) | 90/451/1573字符三档正文、场景、架构、创新与局限 |
| [SUBMISSION.en-US.md](SUBMISSION.en-US.md) | 同等承诺的短/标准/详细英文稿 |
| [CLAIM_EVIDENCE_MATRIX.md](CLAIM_EVIDENCE_MATRIX.md) | 14条Claim、四份原件、Authority等级和阶段缺口 |
| [OFFICIAL_PORTAL_CHECK.md](OFFICIAL_PORTAL_CHECK.md) | 公开公告、实际表单可见范围、截止/格式未知项 |
| [DEMO_180S.md](DEMO_180S.md) | 20+35+35+30+35+25=180秒逐镜头口播、截图及证书来源 |
| [REPRODUCIBILITY.md](REPRODUCIBILITY.md) | 固定checkout、原Verifier、纯REVIEWED投影、页面不可用退路 |
| [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) | 用户PC端确认、协议/身份、粘贴/上传/回执步骤 |
| [PACKAGE_MANIFEST.json](PACKAGE_MANIFEST.json) | 文件bytes/SHA、来源/截图身份、实际验证与缺口；不循环绑定自身 |
| assets/四张PNG | 原始UI记录按解码像素无损转PNG，1266×713，未改画面内容 |

文案采用“智能体行动副作用验证”工作名，将Trace之外的业务状态与合同核验作为评委叙事。完整技术图对应Browser→Vite→Gateway→同一Ledger→真实Explorer→静态两领域Port→各自Authority/Oracle→已验证反馈→Witness/离线Verifier。架构图是解释材料，不作额外运行证据。

中英文均保留只有RPF60 Explorer是真实模型、订单确定性Target、配置SDK scripted Fixture、同服务GET、NOT_TRIGGERED、单次观察无因果优势等限制。未宣称JiuwenSwarm/WorkSwarm集成、真实双LLM Target、发现业务违规、生产就绪、Issuer签名或独立复现。

## 官网与实际提交状态

本次先从搜索工具读取华为云官方活动助手2026-09-17旧公告，直接打开该旧页超时。其10月30日日程只保留为历史版本与内部提前准备目标；当前官方日期以下段新公告与实际门户为准。精确时刻/时区仍未知。

后续切换PC视口并使用可读DOM后，成功取得[最新官方公告](https://openjiuwen.com/news/news-artical?id=248)正文（创建2026-09-09、更新2026-10-20）：创意截止改为11月10日，评审11月25日前，初赛先交名称/简介/场景/技术方案，创意通过后开发DEMO。PC端submission页同样明确2026-11-10，ZIP≤500MB、名称宜简洁避免中文状态符号、未登录看不到提交次数，并显示知识产权/获奖开源CLA条款。因此以新公告和实际门户日期更新材料，10月30日仅保留内部提前目标。临时1440×900视口已恢复；PC截图捕获失败，保留真实DOM文本，未伪称截图成功。没有点击报名、上传、登录或提交，没有隐藏API调用。

`PORTAL_PUBLIC_RULES=VERIFIED`，`LOGGED_IN_FORM=UNAVAILABLE`，`USER_SUBMISSION=NOT_RUN`。日期/ZIP≤500MB已核；精确时刻/时区、登录后字段/字数/URL替代附件规则与最终协议仍待用户。最新公告链接创意PPTX模板和FAQ，本次仅核链接未检内容。提案文本需按模板整理并打包；PPTX/ZIP不在本Plan输出白名单，本次未生成。用户须阅读最终知识产权/开源/CLA条款并决定，本任务没有代为接受。

官方链接与观察日期逐项保存在OFFICIAL_PORTAL_CHECK。该不确定性按Plan允许保留，不妨碍完整材料制作收口；PPTX模板整理及ZIP上传包仍需用户或后续授权完成。

## 证据审查与实际运行

在现有CPython **3.14.6**，对RPF57/58r2/59/60四份固定原件各运行一次原独立Verifier CLI，全部exit0；raw SHA与Plan固定值一致。4份GitHub `blob/<完整功能SHA>/原件` 页面均实读HTTP200。完整文件大小、rawSHA、Verifier模块/SHA、verdict和链接检查记录在Manifest。

另实际运行原 `lab_cross_domain_projection.reviewed()`，结果source=REVIEWED、Session=`rpf59-session-966ab13e1fdf471d`、COMPLETED、原Verifier通过。它只读取跟踪证据，不构造store或启动Gateway。

RPF60原件1,069,226 bytes / rawSHA `81422d26a6ea1406d66d73fecfe0a98a09310a81812faf84e95ed896679b8df9`，原Session `rpf60-session-ff259b8d1bef494b`，两轮order→config；历史Provider2/1340tokens/CNY0.007191估算。RPF57原件88,960 bytes，独立Session `rpf57-session-3ee4ca3412394b0a`，真实双角色inhibited→delivery-suppressed及新增两事实。RPF58是0Provider双域受控，RPF59是真实Explorer独立跨域研究；四场不拼接。

RPF60历史0/2/3、25类语义负控+4额外负控、Runtime394（2Docker skipped）、Web64/typecheck/build及12历史锚作为已提交历史事实引用，**本任务没有重跑这些测试或业务**。仅运行文档专用检查和4个选择性离线Verifier；截图不能代替证书。

截图先检查普通文件、非reparse、SHA与原公开ui-diagnostic记录一致，再人工审查，无可见Key/Cookie/用户名/私人路径。检查发现原四图虽命名.png，文件头实际为JPEG；本包用已有Pillow将其解码RGB无损编码为真正PNG，并逐像素比对一致。未裁剪、加字或改状态，原截图不修改；Manifest同时保留原文件SHA、新PNG SHA和像素SHA。使用权限来自本Plan窄例外；项目画面没有新加第三方媒体。没有替用户对赛事知识产权条款作授权。RPF59校验图明确仍标RPF59，不能冒充RPF60下载操作。实际创建瞬间与RPF60下载连续录像缺失，分镜如实依靠诊断/原件，不补造镜头。

## 验收矩阵

| Gate | 状态 | 证据与限制 |
|---|---|---|
| A-01 Root/Repo/Scope | PASS | 精确Base、fresh refs、无旧tracked改动、白名单范围 |
| A-02 Deadline/Portal | PASS 公共规则；UNAVAILABLE 登录后字段 | 新公告与PC入口共同支持11/10、ZIP≤500MB；登录后字段/精确时刻未确认 |
| A-03 文案 | PASS | 三档中文90/451/1573、等价英文、架构和业务场景；未虚构门户上限 |
| A-04 Traceability | PASS | 14项Claim绑定固定commit/证书/SHA/Oracle/来源，RPF57与60明确分场 |
| A-05 Demo | PASS 分镜 | 180秒，4图来源核验，无成片MP4，无伪LIVE/故障/违规 |
| A-06 Runbook/Offline | PASS | 4原Verifier exit0、纯reviewed投影、固定源码命令核对；本地UI新运行NOT_RUN |
| A-07 Safety/Privacy | PASS | Provider0/tokens0/费用0/业务POST0/JVM0/SDK0/退款0，未读取secret/账号 |
| A-08 Deliverable Audit | PASS | 白名单文件/图哈希、链接/来源/隐私/Claim一致性检查、public docs检查 |
| A-09 Git/Remote | PASS | focused新分支普通push，fresh ls-remote与GitHub readback；最终SHA见聊天回执 |
| A-10 Status/Next Decision | PASS | 此唯一TASK_RESULT与用户提交清单；没有赛事提交或自行阶段接受 |

## 缺口、清理与下一步

R-01～R-10完整原编号条文未在可读canonical仓库落地；仅R-08有当前Plan明确映射，已在矩阵保留其他编号NOT_REASSESSED，不擅自补名或宣称全部达成。该历史需求导航缺口不影响提交有证据支持的提案，若表单要求全量实现声明则先向Architect核对。

新task root只保留必要证书/文档校验日志、截图来源审计、公开门户观察与生成/检查脚本；没有新服务或运行中业务资源。未读用户Downloads/浏览器资料，没有安装、升级或安全策略更改。仅既有4图窄例外访问旧运行根，未读取其他旧私有材料。未新增巨大Witness副本或ZIP/MP4。

交付为新分支focused commit→普通push→远端SHA读回；没有修改父分支/main、PR、merge、tag/release、部署或公开网站。最终提交SHA在聊天报告，不循环修改本文件。所有文件SHA在Manifest，Manifest自身通过Git提交身份绑定，不包含自身hash。

建议用户立即用PC核实初赛表单、截止和协议，再选用三档文案及准确格式提交，保留提交时间/时区、回执、作品编号和最终附件SHA。无需为本次创意节点重跑旧Live或等待main合并；若必须视频/额外附件，先补齐才能提交。研究证据接受、项目阶段推进和后续产品开发交由Architect/用户决定，本任务不作接受声明。
