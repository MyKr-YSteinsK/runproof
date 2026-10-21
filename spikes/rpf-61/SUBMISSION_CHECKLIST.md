# USER SUBMISSION CHECKLIST

本包未代用户登录、报名、接受协议、上传或提交。建议先准备并在规则确认后提交初赛提案，不以继续开发或主线合并拖延；最新官方及PC门户日期为2026-11-10，内部仍按2026-10-30提前准备，不等到最后时刻。

## 用户先确认（实际提交的前置条件）

- [ ] 用PC打开[实际submission入口](https://developer.huaweicloud.com/competition/information/1300000328/submission)，确认选的是“初赛作品提交”。
- [ ] 再次核实2026-11-10的准确截止时刻/时区、实名认证/报名/组队、能否修改；保存最终规则。
- [ ] 用户自行完成账号/团队；姓名、学校/单位、邮箱、电话、成员由用户填写，不从仓库猜测。
- [ ] 阅读最终知识产权共享、原创性、展示使用和依赖许可条款；明确愿意接受再操作。公开仓库不代表作者已同意赛事条款。
- [ ] 已知ZIP且≤500MB；记录登录后的必填字段、字数、上传次数、是否允许URL及额外材料。最新公告区分初赛提案与入围后DEMO。
- [ ] 从[官方公告](https://openjiuwen.com/news/news-artical?id=248)取得创意PPTX模板，核对具体内容并把文案填入，再按公开规则打成ZIP≤500MB。PPTX/ZIP不在本Plan输出白名单，本包未生成；需用户整理或下一任务授权。

## 可直接取用

| 内容 | 位置 | 检查 |
|---|---|---|
| 作品名称/中文三档 | [中文稿](SUBMISSION.zh-CN.md) | 按真实表单上限选90/451/1573字符版本；标题/注释不计入正文 |
| 英文等价摘要 | [英文稿](SUBMISSION.en-US.md) | 核对是否需英文；没有更强技术承诺 |
| 场景/创新/技术方案 | 中文详细稿与Mermaid | 不把架构图当系统运行证据 |
| 代码与功能证据URL | [固定功能SHA](https://github.com/MyKr-YSteinsK/runproof/tree/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8) | 本分支功能不在main；链接不填本地地址 |
| 原件/来源/局限 | [Claim矩阵](CLAIM_EVIDENCE_MATRIX.md) | RPF57/60分开；真实Target与Fixture分开 |
| 演示草稿与4图 | [180秒分镜](DEMO_180S.md) | 仅素材/讲稿，没有成片MP4 |
| 项目文档 | README、复核手册、Manifest | ZIP≤500MB已核；文案按官方PPTX模板整理，不直接把Markdown改后缀上传 |

## 提交前内容核验

- [ ] 当前版本数字为RPF60 Provider2/1340tokens/CNY0.007191估算；不要用RPF59的1332tokens。
- [ ] RPF60订单是确定性Target、配置是SDK scripted Fixture；只有Explorer是真实模型。故障NOT_TRIGGERED，无业务违规发现。
- [ ] RPF57独立会话有真实双角色及观察性L2；不拼接成RPF60因果优势。
- [ ] 没有声称JiuwenSwarm/WorkSwarm已集成、生产级、Issuer签名、独立复现或奖项结果。
- [ ] 所有图标注RECORDED/REVIEWED；没有个人资料、Key、Cookie、私有路径或无权使用媒体。
- [ ] Manifest与实际准备上传文件的SHA一致；不上传整个local目录、旧账本或原始私密请求。

## 由用户执行最终动作

1. 按确认后的字段粘贴文案，填自己的真实团队信息。
2. 选择确实满足规则的附件与固定证据URL；如需视频，本包暂缺，不能勾选“已提供视频”。
3. 逐项预览并确认协议、提交；Codex不执行此动作。
4. 保存最终提交时间与时区、作品/报名编号、成功回执、最终文本和附件的SHA、当时规则截图；这些账号或个人信息留在用户选择的私人位置，不提交公共Git。
5. 若只保存草稿而无成功回执，状态仍为未提交。入围/获奖/阶段接受单独记录，不能由push或材料完成推导。

截至本包交付：`PORTAL_PUBLIC_RULES=VERIFIED / LOGGED_IN_FORM=UNAVAILABLE`，`USER_SUBMISSION=NOT_RUN`。不存在已上传或已通过初赛的声明。
