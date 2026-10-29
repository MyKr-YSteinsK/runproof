# MIGRATION HANDOFF｜用户操作与核验

> 版本 **MIGRATION-2026-10-29-RPF79-rev1**；2026-10-29分支迁移资料，非canonical Project State、非main合并。CURRENT STATE按固定SHA和报告核验；TARGET INTENT保留批准需求；PLANNING CONTEXT不构成执行许可。
>
> 最高明确已接受离线阶段：**RPF-77**（75～77的接受来源为RPF-79正式Plan带入的上一Architect结论，不是本轮重新裁定）。**RPF-78：PARTIAL / PENDING_ARCHITECT_REVIEW**；**RPF-74/rev-4：PAUSED**。先审78再决定修订或下一方向。main=`bda0cd49e50e3181f604324e94877a24b9885334`，迁移Base=`240dbae75cc70f142c7c37a2a3994085063d7ccc`；最新未审查78=`d86528e9927ea2cd7a401da4865829c5a14bfcd2`。证据与验收分开，细节见10/14及SOURCE_EVIDENCE_INDEX.json。

## 交付结构

ProjectSources包含17份完整Markdown，00～14原名保留（两个05），加15新聊天Prompt。公共Git还包括MIGRATION_README、Manifest、Source Evidence Index、RPF79_RESULT；根AGENTS只追加非canonical导航。私有ZIP附Private/PRIVATE-PERSONAL-PREFERENCES.md与ZIP_CONTENTS.json，不进入Git。ZIP的SHA在本地zip-receipt.json及最终交付回执，Manifest不包含自身hash，避免循环。

## 实际迁移步骤（用户手动）

1. 保存并解压交付ZIP，对照Manifest的17份文件名、bytes与SHA；Private notes只在用户决定后自行使用，勿公开传播。
2. 在ChatGPT Project移除/替换旧同名源，上传ProjectSources全部17份Markdown，确保没有旧同名版本并存。ZIP生成与Git Push均不代表自动上传Project。
3. 用户单独把06全文复制到Project Instructions。上传06文件不等于设置已生效；如界面限制字符数，保留完整源与安全条款，明确报告限制，不默默截断。
4. 在同Project新聊天或新Project中粘贴15的首条Prompt；先审RPF78 PARTIAL，再决定rev2或下一研发路线。无须重复孵化访谈或让用户复制数百行报告。
5. 新Architect从14/JSON的固定SHA读实际GitHub文件；再观察当前remote变化，区分RPF79文件交付与Architect接受。main旧canonical文件保留，未合并功能链。

RPF74 PAUSED；比赛登录/提交、PPTX/MP4以及Project上传均无本轮执行。公开目录与私有ZIP不是赛事提交回执。完整偏好仅限用户输入与Plan已知协作信息，不声称覆盖账户全部Memory。
