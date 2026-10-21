# 官方公告与申报入口核查

核查日期2026-10-21，记录时区UTC+08。`PORTAL_PUBLIC_RULES=VERIFIED`；`LOGGED_IN_FORM=UNAVAILABLE`；`USER_SUBMISSION=NOT_RUN`。

## 最新事实与版本冲突

[官方新闻《首届 openJiuwen 智能体创新大赛火热进行中！》](https://openjiuwen.com/news/news-artical?id=248)创建于2026-09-09、更新于2026-10-20。本次从官方新闻第二页进入，并通过真实浏览器读取正文：**创意提交截止为11月10日，创意评审11月25日前**；初赛材料为名称、简介、场景、技术方案，创意通过后通知DEMO开发（演示视频可在3分钟以内）与项目文档。它取代了旧公告的10月30日/11月15日安排。

[实际submission入口](https://developer.huaweicloud.com/competition/information/1300000328/submission)在PC视口公开显示 **初赛作品提交截止时间：2026-11-10**；上传格式ZIP、≤500MB；未登录无法查看团队提交次数。作品名称宜简洁、避免中文状态符号。提交表示确认拥有完整知识产权或合法授权，获奖后同意在openJiuwen开源并签署CLA。没有点击上传、登录、报名或提交。

因此当前官方日期是 **2026-11-10（日期级已核）**。精确截止时刻、时区、能否改稿及登录后的必填内容仍未知。内部保留 **2026-10-30** 为提前准备目标，不把它继续宣传为最新官方截止；10-31也无当前官方依据。门户倒计时只作辅助，不替代明确日期。

## 来源与访问方式

| 来源 | 发布时间/更新 | 本次实际结果 |
|---|---|---|
| [openJiuwen最新公告](https://openjiuwen.com/news/news-artical?id=248) | 创建09-09，更新10-20 | 浏览器正文读取成功，取得新日期/初赛阶段/模板/账号说明 |
| [华为云旧公告](https://bbs.huaweicloud.com/blogs/882ce6baa17e4785bc3398029e6c79eb) | 2026-09-17 11:17:37，时区未确认 | 搜索索引返回全文；直接open超时。旧10/30只作历史对照 |
| [实际submission入口](https://developer.huaweicloud.com/competition/information/1300000328/submission) | 页面未给更新时间 | PC视口取得当前日期、ZIP/500MB、命名/协议/登录提示；未登录字段不可得 |
| [官方新闻列表](https://openjiuwen.com/news-page?page=2) | 列表显示更新10-20的赛事条目 | 先小视口/AX工具缓慢超时，后PC视口及DOM读到正文；未调用隐藏API |
| [官方文档入口](https://docs.openjiuwen.com/) | 未确认 | 可读，不能替代报名系统 |

最初小视口仅显示“移动端暂不支持上传”，后临时切换1440×900以核实PC规则，结束恢复默认视口。公开DOM文本留在任务ignored目录；PC截图捕获失败，日期和规则以浏览器实际DOM为依据，不谎称截图成功。此前小视口截图可留作访问限制记录，不作为最新规则证明。

## 模板、账号与阶段要求

- 官方正文链接：[中文创意模板PPTX](https://gitcode.com/user-attachments/files-group/9307451/92e19ad1e34948418fca9a0d5b712ada.pptx)、[English template](https://gitcode.com/user-attachments/files-group/9307451/2b31df4f73774db8a515338e9b9b7eb2.pptx)、[参赛FAQ PDF](https://gitcode.com/user-attachments/files-group/9307451/120c8629644844b888f6cea4aa7112e3.pdf)。本次只核实这些链接出现在官方可见正文，未下载/检验模板或FAQ内容；不能声称模板页数/字段已确认。
- 公告区分问卷报名与作品提交；提交阶段须在华为云大赛系统重新报名、组队并完成账号实名认证。用户自行完成，不向Codex提供密码/证件。
- 当前公开阶段没有要求立即交MP4；初赛材料先整理为提案。若登录后的表单出现额外必要视频/格式，以该项为用户待确认，本Plan无PPTX/ZIP/MP4输出权限。
- 公告推荐WorkSwarm，本仓库未实现该集成；推荐不作为已有集成事实。获奖开源/CLA、三方知识产权共享与宣传使用均须用户阅读最终协议后决定。

## 已知与未知字段

| 项目 | 状态 | 后续动作 |
|---|---|---|
| 初赛日期2026-11-10 | PUBLIC_VERIFIED | 用户提交时再次核对 |
| 精确时刻/时区、可否改稿 | UNVERIFIED | 用户登录前后核实，提前完成 |
| ZIP且≤500MB | PUBLIC_VERIFIED | 用户将符合模板的最终材料打包；本包不是上传ZIP |
| 作品名简洁/不含中文状态符号 | PUBLIC_VERIFIED | 标题建议RunProof EffectWitness；副标题放正文 |
| 登录后字段、字数、上传次数 | UNAVAILABLE | 用户PC登录记录实际必填项，不绕过限制 |
| 初赛视频 | 公告阶段不要求立即DEMO；登录后待核 | 不将后续DEMO开发误当当前已完成附件 |
| 模板具体内容/FAQ细节 | NOT_INSPECTED | 用户从官方正文下载核对；本次仅备好可复制内容 |
| 团队/实名认证/最终协议 | USER_ACTION_REQUIRED | 公告1–5人、一队一作品；用户核实资格及授权并自行决定 |

本文件记录公开规则，不提供法律结论，也不代用户接受任何条款。未来规则变化应保存当时页面与提交回执。
