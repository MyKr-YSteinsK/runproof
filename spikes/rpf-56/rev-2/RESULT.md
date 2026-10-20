# TASK_RESULT — RPF-56 rev-2

**Status: Blocked**

日期：2026-10-20（Asia/Shanghai）。环境调查子任务 **PASS**；真实恢复与联合闭环因缺少外部合规恢复记录而阻塞。

## 1. 结论与证据

已从只读系统日志中确认 rev-1 的固定 CPython 被 **Code Integrity 策略强制拒绝**，并非只有通用 WinError 推测。两条 3077 事件分别为：

| 本地时间 UTC+08 | Record ID | 关联 3089 | 目标 flat SHA256 |
|---|---:|---|---|
| 2026-10-20 01:07:23.0602512 | 2083 | 2082、2084，同 ActivityID | 与固定 exe SHA 完全相同 |
| 2026-10-20 01:07:29.1527615 | 2087 | 2086、2088，同 ActivityID | 与固定 exe SHA 完全相同 |

目标和 parent basename 均为 `python.exe`；路径仅保存 SHA。两条 3077 的 requested signing level=2、validated signing level=1、NTSTATUS=`0xc0e90002`。关联 3089 的 TotalSignatureCount=0。依据[微软 App Control 排障文档](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/operations/appcontrol-debugging-and-troubleshooting)，3077 为强制阻止，通过 ActivityID 对应 3089；这些读数足以归类 **POLICY_ENFORCED_FOR_PINNED_BINARY**（历史拒绝：高信心），不等于确定策略维护人或唯一产品归属。

当前 Windows 11 build 26200；DeviceGuard usermode/kernel code integrity enforcement 均为 2（Enforced，[官方枚举](https://learn.microsoft.com/en-us/windows/security/hardware-security/enable-virtualization-based-protection-of-code-integrity?tabs=intune)），SmartAppControlState=`On`。后者是当前状态旁证，没有将其升级为“Smart App Control 是唯一根因”。策略 owner=`UNKNOWN`，无历史策略快照，无法确认 RPF-55 成功后具体何时/为何变更，也未证明 Codex host 另有限制或没有限制。

本轮核对直接 exe SHA=`e9f7e4baa0da1c21ffc3c2c2a644459b1a38dced56dfc7846e16f801645d520f`、launcher SHA=`74e020321eb8f828f0c2cfe865082fcf94aa6e7cf488e8a744d89b9282eaeb83`，均与 RPF-53 固定公开证书身份一致。当前 Authenticode 文件检查为 NotSigned；这不是安装损坏判定，不排除包/目录签名语义。SDK METADATA 仍显示 pydantic-ai-slim 2.57.0 / openai 3.35.1，**没有执行 RECORD/ABI 检查**。本轮未运行受阻二进制。

## 2. 来源、范围与技术选择

Root=`D:/CS/runproof`；执行 Base/Parent=`b6e900f75b2d58944acfa9b9a2568b37583caf86`，父分支 `codex/rpf-56-real-explorer-target-config-pge`。新分支 `codex/rpf-56-rev2-appcontrol-sdk-recovery` 从精确 Parent 创建；origin fetch/push=`https://github.com/MyKr-YSteinsK/runproof.git`。初始 fresh remote 父分支一致、目标分支不存在，main=`bda0cd49e50e3181f604324e94877a24b9885334`。初始 tracked/index clean，仅用户原有 `?? docs/reviews/`；未进入、读取或枚举该目录。

读取了适用 AGENTS、Project State、自包含 rev-2 Plan、rev-1 tracked 诊断/结果、直接相关 RPF-53/55 helper/合同和公开固定证书。**没有打开旧 `.local/rpf-56/**` 或旧 RPF-53/55 运行材料。** 新 task root `.local/rpf-56-rev2/` 创建前确认不存在、父路径无 reparse point，并确认被 `.gitignore` 忽略。

只读诊断先以 rev-1 实现 commit `8fa28da` 时间 01:17:14 前两小时作为近似失败窗口（2026-10-19 23:17:14 至 2026-10-20 01:17:14），没有伪造原失败精确时间。随后按已匹配记录缩小到 01:07:20–01:07:32。三条渠道可读，查询均未达到 300 条上限；CodeIntegrity 匹配 2×3077、4×3089；AppLocker EXE/DLL 与 MSI/Script 在所查窗口未匹配。未命中不证明没有相关规则。没有保存无关事件、完整用户路径、用户/机器 ID、原始策略正文或自由模型文本。

本次只交付五个 rev-2 新文档/JSON。D-02 仍不成立，因此未迁移 Runtime/Session schema/Base/branch/JAR/Runner root，未添加诊断 CLI，未改 Explorer/Target/Verifier/测试。避免为尚不允许运行的路径制造“已恢复”身份；后续迁移及跨版本拒绝测试仍需落实，不可直接使用旧 probe。未更改任何系统策略、注册表、服务、安全设置或权限，`OS_POLICY_CHANGED_BY_CODEX=false`；无安装、复制、重签、fallback、提权或换终端执行。

## 3. Acceptance

| Gate | 状态 | 证据或未完成项 |
|---|---|---|
| A-01 仓库与权限 | PASS | 精确 Parent、新分支、远端、main、规则、ignore/link、白名单和保护核验。 |
| A-02 策略取证 | PASS | 实际匹配 3077 + ActivityID 关联 3089；文件 pin、当前策略状态与未知项有脱敏记录。 |
| A-03 安全恢复 | UNAVAILABLE | 无 owner/admin 合规恢复记录，不具备一次直接 smoke 的准入；未做烟测。 |
| A-04 rev-2 合同/总账 | NOT_RUN | 没有迁移运行合同；原 rev-1 离线协议另行复验，不能算 rev-2 PASS。 |
| A-05 三 SDK 冷启动 | NOT_RUN | A-03 未成立，实际固定 SDK Fixture=0。 |
| A-06 真实双 Agent/业务 | NOT_RUN | Provider/Java/HTTP/POST 全 0，无 Session。 |
| A-07 真实反馈时序 | NOT_RUN | 无真实选择、第一轮反馈和第二轮请求。 |
| A-08 新联合 Witness | NOT_RUN | no-valid-Witness，`rev-2/config-pge-evidence.json` 必须不存在。 |
| A-09 回归与交付质量 | PASS | 12 定向、325 Runtime（2 Docker skips）、九旧锚、Reviewed/Public Docs 通过；只复验未变更协议，不替代集成。 |
| A-10 Git/TASK_RESULT | PASS | 五个新报告已 focused commit、普通 push，fresh 远端 SHA 与本地一致，main/Parent 不变；本交付记录单独提交收口。 |

## 4. 验证与成本

本轮普通离线验证使用现有一般 Python（shell command launcher SHA=`5da5ad3f515a97310adaa03019a110de8cab9f275767a6571c7b2a722c89eae9`；实际 `sys.executable` 文件 SHA=`03168c01b7b7491423350e82c26fee71f35b43694d1319d3c668bda6903a0c38`），只运行测试/离线 verifier，未用于加载或执行固定 SDK、替代真实 Target 或绕过拒绝。隔离源码快照位于新 task root 内，旧测试中相对 `.local/rpf-56` 路径仅解析到该新快照内部，与仓库旧运行目录无交集。子进程环境不带 key；回归 guard 阻止 Java/Docker 及非 loopback socket。

定向 12 项通过；完整 Runtime 325 项通过，2 项 Docker 环境跳过。两种合成会话（有信息增量与合法重复）各自 correct/missing/wrong SHA exit=0/2/3，11 类 rehashed tamper 均拒绝：伪造选择、反馈 hash/时序、分角色预算拆分、重复 POST、虚假故障触发、namespace 拼接、假 ACK、source、SDK PID、cleanup。它们为 rev-1 原协议在本轮的复验，并非 rev-2 新证书。九件旧独立 SHA 锚、Reviewed/Public Docs 均 exit 0。详情写入 `verification-diagnostic.json`；快照全部 source map、verifier、测试 hash 均与执行代码一致，因为本轮没有改动代码。执行与交付的 runtime source identity 完全相同，所有版本事实与 rev-1 保持区分。

固定 CPython smoke=0、固定 SDK 元数据进程启动=0、SDK Fixture=0、Provider request/token/CNY=0/0/0、JVM/业务 HTTP/POST/health=0/0/0/0。没有读取 API key，没有真实 Session/ledger/started marker，只有诊断及合成测试账本。没有本轮受控 SDK/JVM/服务或待定模型请求需要清理。诊断脚本、过滤后的事件投影、隔离快照及测试日志保留 ignored 新 task root，无旧目录清理。

研究结果 L1/L2=`NOT_RUN`、H1=`NOT_PROVEN`。发行者真实性、数据库独立权威、独立复现、WorkSwarm、归因等边界仍按原合同保留：`NOT_ESTABLISHED / NOT_ESTABLISHED / NOT_TESTED / NOT_PROVEN / CORRELATIONAL_ONLY`。本轮无付费资格，未作新的模型定价核验或模型请求。

## 5. 最小外部决策与下一阶段

需要设备所有者/有权限管理员在本 Plan 外确认：固定 SHA 的 Python 是否应允许运行、谁维护命中策略；若已合规恢复，提供真实维护时间、恢复类型和该 SHA 的许可确认。无需提供完整策略/账号/凭据。Codex 不代批准、不改策略；当前不请求 API key，也不继续试启动。

取得可核验恢复事实后，先落实显式 rev-2 schema/owner/root/Base/branch/Source freeze 与跨版负控，再做且仅做一次固定解释器 smoke；若仍 4551 即停止。全部前置通过才有三次 SDK Fixture 和一个新两轮真实 Session 的资格。恢复本身不使 RPF-56 Complete。

首次报告交付 commit=`6e478b795fb76378aeac65517992f92beb38f241`，已普通 push 至新分支，fresh `git ls-remote` 与本地一致；Parent 仍为 `b6e900f75b2d58944acfa9b9a2568b37583caf86`，main 仍为 `bda0cd49e50e3181f604324e94877a24b9885334`。工作树只剩用户原有 `?? docs/reviews/` 外层状态。只新增五个白名单文件，旧 Runtime、测试、rev-1 报告和所有旧 tracked 材料未改。密钥模式/公开 JSON 绝对路径/范围审查通过；未请求 hosted CI（该分支不匹配 main 自动 Gate）。本次无 PR、main merge/push、tag、release、workflow dispatch 或 deploy。本交付记录单独提交收口，最终 SHA 放在聊天回执。
