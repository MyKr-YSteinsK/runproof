# RunProof EffectWitness

## 从解压目录运行

需要 Windows PowerShell 7.2+、Node 22+、带 SQLite 的 CPython 3.11+。在全新目录解压，进入 app/ 后运行：

    .\start.ps1 -PythonExe <绝对路径> -NodeExe <绝对路径>

打开启动器给出的本机地址。勾选一次性确认，运行受控 Agent 实验。先看订单 UNKNOWN、独立读回和已验证反馈，再查看第二轮配置意图、Controller 判定与状态差异。刷新和会话深链读取同一份结果。

完成后下载 Witness。从可信独立渠道获得 SHA-256 后运行：

    .\verify-witness.ps1 -PythonExe <绝对路径> -Witness <文件路径> -ExpectedSha256 <可信摘要>

省略摘要仅执行内容复核。停止服务时使用启动器返回的 nonce：

    .\stop.ps1 -Nonce <nonce>

默认运行使用本机受控 SQLite 与离线参考 Agent，每域一次业务写入，Provider 预约为 0。可在界面查看 RunProof 已审阅的平台样本。工程源目录包含 Java Control Plane、DeepSeek Provider 和 JiuwenSwarm MCP 接入，重建步骤见 ARCHITECTURE.md。
