# TASK_RESULT

Plan ID: RPF-67
Revision: rev-4
Status: PARTIAL

## 结果

真实订单 Target 已完成 Provider → inspect/refund → UNKNOWN → read-only reconcile/安全停止 → final stop → 固定 SDK → 独立 SQLite Authority → 同一 WAL → 离线 Witness。

| Gate | 状态 |
|---|---|
| G0 | PASS |
| R4-A01 | PASS |
| R4-A02 | PASS |
| R4-A03 | PASS |
| R4-A04 | PASS |
| R4-A05 | PASS |
| R4-A06 | PASS |
| R4-A07 | PASS |
| R4-A08 | PASS |
| R4-A09 | PASS |
| R4-A10 | NOT_RUN |

## 身份、预算与免费验收

- Repo: MyKr-YSteinsK/runproof；origin: https://github.com/MyKr-YSteinsK/runproof.git。
- Base: `2d57f0461e76911d3b4f6b3feae7935e1413113a`；branch: `codex/rpf-67-rev4-terminal-input-budget-recovery`。
- Source LF digest: `434d32a26a422ddc3ea6079ed43a492ae80b3728d6d38a887945d10ed1e7de75`；Source Map raw/LF、冻结时间及 helper SHA 见 preflight-diagnostic.json。
- CAPS: [3000, 2600, 2600, 4200, 1400, 1200]，总15000；协议最多4次。未使用4800备选；终止512 output与512 framing guard均保留。
- 免费最终 focused 59 项；full 486 项，errors/failures=0，Docker2 skip=UNAVAILABLE；Windows3.12父全量NOT_ESTABLISHED、Ubuntu hosted CI NOT_RUN。
- 合成77类重锚+CLI0/2/3、19件历史原证书/原Verifier/原SHA及Reviewed/Public均PASS。开发期一次26项聚焦出现1失败，修复为预发送永久停止先于普通资源限额；已保留该失败，不冒充最终源结果。第一轮full后审查发现Host覆盖预算错误分类、拒绝receipt回注未独立核对，修复后使用第二轮完整full验证最终源；两轮原日志及源身份均保留。
- 新 SQLite 完整收据+最大160字节ToolCall ID/512字节content，固定 SDK 四次免费响应成功；原 ToolReturn 串行化字节逐一相同。真实结构第4次suffix=1386，982+1386+512+512=3392<=4200。边界实际validate_request总额4199/4200接受，4201拒绝，无Provider预约/发送。
- receipt-before-WAL 与 WAL-without-receipt 两种 crash negative 均永久拒绝；≥11种拒绝receipt重锚攻击及原77类Witness负控均拒绝。

## 真实试验与边界

- 正式命令/PID/cwd/exit、metadata/cold/admission与SDK pin见 verification-diagnostic.json；未读取或续用旧 ignored root。
- 实际Provider已接受响应数: 4；known tokens=3783；known usage守卫估计¥0.0213705。预算永久预约与known usage分别列在session-summary.json；实际账单NOT_QUERIED。
- Provider第4响应实际到达: True；final Model stop: True；完整SDK报告: True。
- 一次已确认退款、2500 minor CNY、独立mode=ro Reader、原receipt及故障四态见session-summary.json；不以模型文本作Oracle。
- Agent Verdict / Platform Error / Oracle Verdict已分栏。没有完整真实Witness时条件公开文件不创建。
- 本轮正式根及RPF-67新增故障根的WAL/DB/失败/marker证据保留；全量旧测试在本任务新快照内按既有fixture生命周期运行，完整日志保留。无真实重试、无换根复活预算、无旧会话接触；OS PID/线程/socket/Key清理见os_cleanup。

## 交付与未证实能力

- 仅5个既有文件及本Plan合格新文件提交；Session owner装配替代修改受保护Port，业务SQL/工具方法、Child、旧HTTP fixture、历史锚保持原字节。
- Git交付实际观察: `{}`。最终receipt提交SHA由聊天回执补报，不为自引用改写提交。
- docs/reviews/保持用户原顶层未跟踪标记，未进入/列举/读取/hash/diff/stage；docs/project、docs/history、AGENTS及旧证据未改。
- main/parent未变；没有PR、merge、force、tag、release、dispatch、部署、赛事上传。普通分支push无自动Release Gate触发，Hosted CI须按实际GitHub观察。
- TASK_COMPLETE=False；EVIDENCE_ACCEPTED=ARCHITECT_REVIEW_REQUIRED；STAGE_ADVANCED=ARCHITECT_REVIEW_REQUIRED。
- 同一真实双域Session NOT_PROVEN；Explorer NOT_RUN；L2 NOT_TESTED；Web NOT_INTEGRATED；causality NOT_PROVEN；independent reproduction NOT_TESTED；issuer NOT_ESTABLISHED；production release NOT_AUTHORIZED。

## 建议（不扩展本轮授权）

后续可为新旧DomainPort构造器显式传入owner，减少Session装配重复；将预算证明字段作为版本化公共协议维护。下一阶段仍需独立验证同一真实双域Session，不能拼接两个订单/配置Witness宣称联合闭环。

开发记录限制：少量早期临时命令的 PID／当时 raw source digest 未记录，已显式标 NOT_RECORDED；正式 Controller/SDK、两次完整 full、最终 focused 的 PID／源／退出码完整保留。
