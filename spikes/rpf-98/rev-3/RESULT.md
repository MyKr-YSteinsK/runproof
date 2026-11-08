# RPF-98/rev-3 结果

Status: PARTIAL（封存时 hosted Linux 测试尚未执行）。Base `5b2cd1eca23f5716090fb13d3fdb6f1833af7d6f`。

Run 42496064999 的 12 项 ERROR 对应的异常签名均为 UNAVAILABLE；不能认定既有失败根因。Router 已增加针对 POSIX 相对 `os.remove`/`os.rmdir` 的有效目录 fd 校验：验证目录类型、procfs 路径、owner 归属与设备/inode，拒绝外部、无法识别、上级及解析后越界的路径。其他平台维持原有限制。针对真实 fd 的临时目录清理、目录内删除和 owner 外 sentinel、上级路径、符号链接及非法 fd 负控，已添加到既有 hosted 安全测试步骤。

本机 Windows 聚焦测试 3 PASS、Linux fd 测试 1 SKIP；不能当 Linux 正控通过。Router/handoff/RPF86/RPF88 与 workflow live pins 按拓扑更新；历史证据、matrix 和测试覆盖要求未改。最终 hosted 12 ID 和负控须看本次真实 Run，539 个历史 UNAVAILABLE 不因源码变更自动解除。

| Gate | 状态 | 说明 |
|---|---|---|
| G0 | PASS | 本地 main 与远端基线一致；相关路径未见冲突。 |
| A01 | PASS | 同 Run 12 方法状态与签名核查，异常签名均不可用。 |
| A02 | NOT_RUN | 封存时 Linux 真 fd 正负控尚未运行。 |
| A03 | NOT_RUN | 修改后的提交身份和完整 live pin 尚待提交后核验。 |
| A04 | NOT_RUN | 本机仅非 Linux 聚焦测试运行，目标 12 项未复验。 |
| A05 | NOT_RUN | 封存时 Git 和 CI 尚未完成。 |
| A06 | PASS | 未运行 Provider、旧 owner、真实业务写，未改原测试或 Matrix。 |

首次 hosted Run 42497088103 在新增 Linux 测试中因测试文件缺少 `sys` 导入而失败；Router 未启动，12 项结果 NOT_RUN。已补充导入，后续 Run 另行核实。
