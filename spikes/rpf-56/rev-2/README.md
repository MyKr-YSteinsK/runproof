# RPF-56 rev-2：Windows 应用控制诊断

本次调查已找到两条 **Code Integrity 3077 强制拒绝事件**，其目标文件 flat SHA256 与固定 CPython 完全一致，且各有 ActivityID 关联的 3089 签名事件。整体状态 **Blocked**：没有设备所有者/管理员提供的合规恢复记录，未启动固定解释器烟测、SDK Fixture、Java 或 Provider。

## 结果入口

- `RESULT.md`：唯一中文 TASK_RESULT、逐 Gate 状态、停止原因及交付事实。
- `environment-diagnostic.json`：最小脱敏事件、解释器 hash、当前安全状态、归因与未知项。没有用户路径、账号、完整策略正文。
- `verification-diagnostic.json`：本轮普通离线验证及来源身份；不代表 rev-2 运行合同验收。
- `session-summary.json`：实际受控进程/模型/业务用量全 0，无真实 Session、无新 Witness。

本轮仅新增以上五个文件。Runtime、测试和 `spikes/rpf-56/probe.py` 保持 Parent 原样；没有新 `diagnose-policy` CLI，也没有把 rev-1 Runner 直接改成可重新执行。诊断用 PowerShell 脚本与隔离测试快照保留在 ignored `.local/rpf-56-rev2/`，仅供本机审阅，不构成安全管理工具。

## 调查方法与限制

普通权限读取文件 SHA/SDK METADATA、CodeIntegrity/AppLocker 指定时段和事件类型、Win32_DeviceGuard 两项 enforcement 字段、SmartAppControlState。首先按 rev-1 实现 commit 前两小时查询，再缩小到 01:07:20–01:07:32；事件均已在本轮读取，无新失败启动探测。

微软将 3077 定义为 App Control 强制阻止，建议通过 ActivityID 关联 3089；[官方排障文档](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/operations/appcontrol-debugging-and-troubleshooting)。当前 CIM usermode enforcement=2，含义为 Enforced，见[官方状态说明](https://learn.microsoft.com/en-us/windows/security/hardware-security/enable-virtualization-based-protection-of-code-integrity?tabs=intune)。本轮没有执行文档中的提权、完整导出、注册表或修复步骤。

事件支持“固定 Python 在 rev-1 失败时被系统 Code Integrity 策略拒绝”；当前 Smart App Control 为 On，但没有据此断言它是唯一管理产品或具体策略所有者。没有历史策略快照，不能证明 RPF-55 成功之后的策略变更原因，也不能把当前文件 hash 一致当作 ABI/RECORD 或执行资格验证。

## 合规恢复所需资料

请设备所有者/有权限的管理员在本 Plan 外决定：

1. 该固定 Python SHA256 `e9f7e4baa0da1c21ffc3c2c2a644459b1a38dced56dfc7846e16f801645d520f` 是否应获得运行许可，哪个主体负责相关策略？
2. 若已通过合法流程恢复，提供真实维护时间、恢复类型及针对该 SHA 的许可确认；不要提供完整私密策略、账号或密钥。

Codex 不代批准或修改策略。本 Plan 的继续执行仍须先核实真实恢复记录，再且仅再做一次原固定 SHA 的受限烟测。未恢复前不重试旧 probe、不换解释器/终端/WSL/容器，不复制、改名、重签、下载安装或提权。不请求 API key。

SDK 恢复并不代表联合实验通过；之后仍需显式 rev-2 合同/新 root/新版本身份、三候选冷进程、执行当天价格核验、共享预算、两个真实角色及两轮真实反馈，最终独立验证真实 Witness。
