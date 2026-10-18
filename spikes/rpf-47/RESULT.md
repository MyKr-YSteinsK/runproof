# RPF-47/rev-1｜TASK_RESULT

**Status: PARTIAL**

## 1. 身份、权限与边界

- 仓库：`D:\CS\runproof`，`git rev-parse --show-toplevel` 指向该目录。
- 推荐 Parent / 实际 Base：`codex/rpf-46-live-pge-lab@69dfe3079f5778cf6e569e82cf8382e4e3ec04a8`；本次目标分支：`codex/rpf-47-competition-evidence-demo`，从上述提交创建。`main` 预检 SHA：`bda0cd49e50e3181f604324e94877a24b9885334`。
- 既有远端：`origin` → `https://github.com/MyKr-YSteinsK/runproof.git`。执行前目标远端分支不存在；提交和推送状态见 A-10。
- 根规则及 Plan 47 授权范围已核对。`docs/reviews/` 只从 `git status --short` 知道有既存 `?? docs/reviews/`；本轮没有读取、枚举、打开、修改、移动、暂存或提交其内容。
- 本次没有访问或改动 `.local/rpf-45` / `.local/rpf-46`、其付费账本、证书或 cache-hold；没有修改 `docs/history/**`、历史样本或既有 Plan/RESULT。

## 2. 改动与证据来源

- Web 增加独立 `/effectwitness/recorded` 只读路由、双语来源/结果视图、反馈事件深链，以及 Lab / Live 页通往该视图的链接。页面从跟踪文件内嵌数据，先验证 manifest/源内容固定摘要、来源身份、反馈顺序与业务事实；失败时隐藏证据，不回退测试夹具，不调用 `/api`、Gateway 或 Provider。
- `spikes/rpf-47/` 新增机器可读来源清单、严格离线校验器、创意申报草案、逐秒演示脚本和本结果。根双语 README 与 `web/README.md` 仅增加此功能分支的入口说明。
- 当前分支内容与 `main` 明确分离；上述页面和申报材料是本计划新目标，不代表 `main` 已接受、已发布或已报名。
- 演示来源严格分开：RPF-46 是跟踪的脱敏 Live 研究摘要，级别为 `REPORTED_NOT_FULL_OFFLINE_VERIFIED`；RPF-43 订单和 RPF-44 运维 Witness 是两次不同的历史确定性运行。没有新造 Live 运行，也没有下载或伪造 RPF-46 原 Witness。
- 关键用户可见结论：RPF-46 报告记录 `normal → response-lost`，首轮反馈 hash 在下一轮选择前完成验证并回注；两个订单各一张收据、`PAID → REFUNDED` 且合同满足，第二轮故障已触发并调和；没有发现合同违规。单会话只有有限机制与相关性证据，不证明因果、重现、普遍策略优势或生产能力。历史 Witness 的文件锚不建立签发者身份。

## 3. A-01～A-10 验收

| Gate | 状态 | 实际证据与限制 |
| --- | --- | --- |
| A-01 身份/权限 | PASS | 预检记录了根目录、Base、`main`、目标分支、`origin` 和状态；目标本地/远端分支原先不存在。唯一预存未跟踪项是受保护的 `docs/reviews/`，仅见状态行且保持不动。无 PR、合并、tag、release、deploy 或报名操作。 |
| A-02 事实/源码矩阵 | PASS | `EVIDENCE_MANIFEST.json` 固定三项来源和 SHA；离线校验器核对 source commit 祖先关系、Git blob / 工作树字节、摘要结构、会话身份、选择、反馈时序、收据和 claim limits。浏览器仅做内嵌摘要/manifest/报告事实检查，不声称认证自身 Git 来源。对因果、业务漏洞、签名身份均明确降级。 |
| A-03 无费可复核 | PASS | 从已推送的公开目标分支重新 `git clone --no-hardlinks` 到 `.local/rpf-47/checkout`；克隆 HEAD `45d049ca54974d374d4ddf6093248722f287a092`，分支匹配，精确检查 `.local/rpf-46` 为不存在。离线 manifest 状态 `VERIFIED`；Provider/new-session/new-trial 均为 0。完整 RPF-46 Session/Witness 未复制。 |
| A-04 Witness/身份/旧样本 | PASS | 独立克隆中 RPF-43、RPF-44 anchored verifier 均为 `VERIFIED_ANCHORED` / native exit 0；缺锚为 `UNANCHORED_INCONCLUSIVE` / native exit 2；错误锚为 `REJECTED` / native exit 3。PowerShell 调用记录 `$LASTEXITCODE`，因命令承载层会把非零进程码归为 1。两份样本 `issuer_authenticity=NOT_ESTABLISHED`，不是 RPF-46 Live。旧 RPF-46 local Witness 未访问。 |
| A-05 真实信息设计 | PASS | `RECORDED` 标签、来源条、双语事实、反馈 → 下一选择 → 业务读回 → 收据/故障 → Witness 边界均写在实际路由和 180 秒脚本内；没有“发现漏洞”结论。浏览器视觉验收独立列在 A-06。 |
| A-06 Web/双语/来源 | NOT_RUN | `npm test -- --cache=false`（15 files / 60 tests）、`npm run typecheck`、`npm run build -- --config .local/rpf-47/vite.config.ts` 均 exit 0；构建提示既有总 JS chunk 约 1.371 MB。`python -B ci/verify-public-docs.py` exit 0（18 files / 7 pairs）。隔离回环地址 `http://127.0.0.2:4174/effectwitness/recorded` 的 HTTP GET 返回 200、HTML 标题为 RunProof；但 CUA 可见浏览器 `getTab(...).getState()` 超时 30 秒后 kernel reset。未实际确认 1280×720、zh/en 切换、event 深链/刷新、断连 fail-closed、键盘焦点和旧只读页面回归，因此本 Gate 不能 PASS。没有清理浏览器缓存或触碰其它应用状态。 |
| A-07 创意申报包 | PASS | `SUBMISSION.md` 含中文名称、短/长简介、用户/场景、技术方案、创新点、边界、英文简介、官方材料字段映射及待用户填写个人信息占位。公告公开信息列明 2026-10-30 日期，不含时刻/时区；最终登录表单未检查，明确 `OFFICIAL_PORTAL_LOGIN_REQUIRED / USER_CHECK`，状态 `NOT_SUBMITTED`。 |
| A-08 三分钟分镜/素材 | PASS（视频不可用） | `DEMO_SCRIPT.md` 时间轴共 180 秒，逐段给出真实画面、旁白、源文件与结论边界，并提供真实只读路由和安全回环启动命令。环境没有可识别的 ffmpeg/ffprobe/OBS/桌面录屏工具；未安装依赖，未产出 MP4，因此视频为 `UNAVAILABLE / NOT_RUN`，没有截图冒充视频。 |
| A-09 回归/清理/成本 | UNAVAILABLE | 本轮 Provider 请求/token/费用均为 0；非测试新业务 trial 为 0。旧付费账本、quarantine 和 cache-hold 没有被访问或修改；本结果不声称核查其内部内容。测试/构建/文档/离线校验均通过，但已生成的 `.local/rpf-47/vite-cache/` 与 `web-build/` 未清理：PowerShell `Remove-Item -Recurse -Force` 被执行策略拒绝，未产生删除副作用。保留目录供本地复核；无新建 quarantine 或业务状态。 |
| A-10 Git/交付 | PASS | 首个 focused commit `45d049ca54974d374d4ddf6093248722f287a092` 已普通 push；随后从 `origin` 独立克隆并确认目标 ref 为同一 SHA。push 前后 `main` 均为 `bda0cd49e50e3181f604324e94877a24b9885334`。其后两个小型结果更新 commit `e8e93f999cdccd535f0d18df12b17770d755eb78` 和 `d2f3e1fbad7f2d1710478d717d043ce464f6c3a7` 也已普通 push；最后一次独立 `ls-remote` 与本地 HEAD 完全一致。精确最终 SHA 同时列于聊天回执，避免在该 SHA 对应的 commit 内自指。未建 PR、未合并、未发布或部署。 |

## 4. 来源身份与可复核输出

- RPF-46 来源提交：`69dfe3079f5778cf6e569e82cf8382e4e3ec04a8`。
- 固定源摘要：RPF-46 `session-report.json` `f450803b8fd3ec51fe2663ba95370577c92f0eb70cc0dd05f4d7e5b98ab25d15`；RPF-43 `sample-witness.json` `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e`；RPF-44 `sample-ops-witness.json` `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873`。
- manifest 固定 SHA-256：`6a9ebe1f1d5a759c8335275dc4a16afbe939ef9aa7eac041756dfd3ec434cdbf`。校验器适配 Windows Git CRLF 工作树时先规范化换行，再要求工作树规范化字节与指定 Git commit blob 完全相同。
- 两份历史样本的离线 verifier `VERIFIED_ANCHORED`；独立克隆再次验证。缺可信锚会 `UNANCHORED_INCONCLUSIVE`（exit 2），错误锚为 `REJECTED`（exit 3）。锚只绑定有界文件内容，不证明 issuer 身份。
- 竞赛日期证据：[华为云云社区官方赛事公告](https://bbs.huaweicloud.com/blogs/882ce6baa17e4785bc3398029e6c79eb)，公开索引内容标注发布于 2026-09-17，并列创意提交日期 2026-10-30；直接打开本次超时。公开可读公告没有截止小时/时区；另见 10-31 日期冲突，但未验证为官方延期。官方 openJiuwen 赛事中心本次可读页没有显示赛事项目。问卷/登录门户字段、最终日期精度、上传格式仍 `OFFICIAL_UNCONFIRMED`，交用户登录核实。
- 视频：未创建；`.local/rpf-47/media/` 没有 MP4，故无可报告的文件字节数、时长、编码或 hash。真实拍摄入口、逐段来源与旁白在 `DEMO_SCRIPT.md`；画面必须持续标 `RECORDED`，不拼接成单次运行。

## 5. 实际命令

下列源码/文档验证在本仓库完成，除特别说明均 exit 0：

```text
npm test -- --cache=false                   PASS · 15 files / 60 tests
npm run typecheck                           PASS
npm run build -- --config .local/rpf-47/vite.config.ts  PASS · 156 modules; 1.371 MB JS chunk warning
python -B ci/verify-public-docs.py           PASS · 18 files / 7 pairs
python -B spikes/rpf-47/verify_evidence.py --root .      PASS · status=VERIFIED; zero provider/trial budgets
python -B -m runtime.runproof_runtime.effectwitness.witness_verify spikes/rpf-43/sample-witness.json --expected-sha256 ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e  PASS · VERIFIED_ANCHORED
python -B -m runtime.runproof_runtime.effectwitness.witness_verify spikes/rpf-44/sample-ops-witness.json --expected-sha256 21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873  PASS · VERIFIED_ANCHORED
```

独立克隆中的 manifest 和锚定/负向 witness 命令输出已按 A-03/A-04 记录。没有执行 Docker 正式接入或 Live/provider 命令。

## 6. 本机隔离产物与下一步

- 本轮只在 `.local/rpf-47/` 创建/保留任务产物；独立新克隆保留作 A-03/A-04 复核证据。生成的 `vite-cache/` 与 `web-build/` 保留在该任务目录内；递归删除命令被执行策略拒绝，故没有再尝试规避。`tmp/`、`logs/`、`media/` 未用于存放提交物，未创建 quarantine。旧 Plan 40–46 本机数据不在写入或清理范围内。
- 后续用户动作：在可用桌面浏览器按 1280×720 完成语言、事件深链/刷新、键盘和错误态验收；若提交门户确认实际硬性要求 MP4，则在有录屏工具的本机按脚本录制并检查 ≤180 秒；登录官方报名问卷核实截止时刻/时区、字段、附件和 IP 条款；由用户自行决定是否报名、上传和最终提交。
- 当前无源代码安全或数据结论阻塞项；未完成 GUI 体验 Gate、录屏文件和报名门户人工核对是 `PARTIAL` 的原因。`SUBMISSION_PREPARED` 不等于报名或作品已提交。
