# 180秒真实证据演示稿

形式：分镜、口播与已记录素材索引；**没有生成视频文件**。总长180秒，建议中文口播，按下面时长录制后可删减停顿，不能加速后改写事实。画面上的历史LIVE徽标须始终配合镜头标题 `RECORDED FROM ACTUAL LIVE RUN · 2026-10-21`，不能当作今天重新启动。

## 固定片头小字

功能代码 `1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8`；主会话 `rpf60-session-ff259b8d1bef494b`。来源标记：RECORDED FROM ACTUAL LIVE RUN / REVIEWED EVIDENCE / EXPLANATORY DIAGRAM。最后一段切换RPF57独立会话，必须全屏切页明确标识。

| 时间/秒 | 可用画面与来源类别 | 旁白/字幕（可直接朗读） | 逐镜头事实来源 |
|---|---|---|---|
| 0–20 /20 | EXPLANATORY DIAGRAM：中文方案架构图，2500分退款与配置v2两个例子 | “智能体说已完成，业务真的完成了吗？RunProof EffectWitness面向Agent研发，用合同、实际状态与确定性核验审查行动副作用。” | [产品合同](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/docs/project/PROJECT_BRIEF.md)；本包中文架构；图是解释，不伪装运行截图 |
| 20–55 /35 | RECORDED FROM ACTUAL LIVE RUN：[英文RUNNING原图](assets/live-start-browser.png)，随后[中文COMPLETED原图](assets/live-completed-browser.png) | “这是10月21日实际运行的记录。用户从桌面浏览器确认后，经本机Gateway启动这个新Session。真实DeepSeek只负责在两个受控候选中选择，运行中可请求取消，取消会在安全边界生效。” | [前端POST202/同Session诊断](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/ui-diagnostic.json)；RUNNING图不能证明勾选或点击瞬间，HTTP202由诊断支持，不编造缺失点击录像 |
| 55–90 /35 | REVIEWED EVIDENCE：原Witness订单行与摘要的字段排版；可用完成图作背景，图上没有收据字段时不称截图可见 | “第一轮选择正常退款。虚构订单从未退款到完整退款2500分，revision变为1，只有一张收据。确定性Target负责执行业务，独立只读连接与Oracle核验收据和状态。这个结果说明本次满足合同。” | [Round1摘要](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/session-summary.json)；Run `rpf60-order-da9b1127b5424628`；raw SHA见下方 |
| 90–120 /30 | REVIEWED EVIDENCE：同Witness配置字段，版本/历史/故障三标记 | “第二轮选择配置实验。真实SDK运行脚本化Target，Java/H2从不存在到v2，历史为二、一。这里故障计划被禁用，planned为真，triggered和observed都为假，所以明确标成未触发。只有Explorer是真实模型。” | 同原Witness Round2；Run `rpf60-config-2e979367c8d54805`；target FIXTURE_SCRIPTED |
| 120–155 /35 | REVIEWED EVIDENCE：本次离线CLI输出、原件SHA；若用[旧RPF59校验图](assets/reviewed-browser.png)，标题必须标RPF59另一个会话；[Gateway不可用原图](assets/gateway-down-browser.png)可作为末尾失败关闭说明 | “当前RPF60原件可按外部SHA离线核验。浏览器核对下载字节，Verifier另查合同与账本。网关不可用时不会用历史结果伪装在线成功。哈希不等于签发者签名，重新校验证书也不等于独立复现实验。” | [RPF60原件](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/cross-domain-live-evidence.json)；[Verifier](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/runtime/runproof_runtime/effectwitness/lab_cross_domain_verify.py)；RPF59图只证明其自身UI，不能给它换RPF60 SHA |
| 155–180 /25 | REVIEWED EVIDENCE / EXPLANATORY DIAGRAM：全屏标题 `RPF-57 INDEPENDENT RESEARCH SESSION`，纯文字事实与固定链接，无虚构截图 | “另一个独立的RPF57配置研究会话使用真实Explorer和真实Target，观察到工具结果抑制后的只读对账与新增事实。这不是刚才的Session。我们提供有界证据，不把一次选择变化说成因果优势；现阶段重点是让Agent行动结果可审查。” | [RPF57报告](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-57/RESULT.md)、[原Witness](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-57/config-pge-coverage-evidence.json)；Session `rpf57-session-3ee4ca3412394b0a` |

## 素材标签和完整性

4张PNG均为原RPF60诊断点名的普通文件，先核原SHA再人工检查，原文件虽命名.png但实际JPEG，本包仅把解码RGB无损编码为真正PNG并验证逐像素一致；未裁剪、覆盖文字或生成新业务状态；尺寸1266×713。图旁的标题/字幕属于解释层。原始SHA、字节数、来源、权限和处理记录在Manifest；公开图没有账号、Key、Cookie或私人路径。画面由本项目UI构成，没有添加第三方影音素材。

- `live-start-browser.png`：真实RPF60运行中的英文画面；没有勾选/点击瞬间录像。
- `live-completed-browser.png`：同一RPF60完成后的中文画面。
- `reviewed-browser.png`：RPF59 REVIEWED证据的原SHA校验画面，**不是RPF60下载界面**。
- `gateway-down-browser.png`：RPF60入口显示Gateway不可用，不能剪成业务FAIL。

主会话raw SHA：`81422d26a6ea1406d66d73fecfe0a98a09310a81812faf84e95ed896679b8df9`。录像若需展示RPF60原件下载，现有证据只有诊断记录与离线文件检查；没有该操作的连续录屏，不补拍新付费实验。可展示命令和原件链接，并准确标REVIEWED EVIDENCE。

没有VIOLATION_CONFIRMED镜头，不宣称发现业务漏洞；RPF57局部Tool delivery suppression不叫TCP丢包；RPF60 NOT_TRIGGERED不叫成功注入。若当期表单必须MP4，本包尚不满足该附件，需另行授权视频输出与用户上传。
