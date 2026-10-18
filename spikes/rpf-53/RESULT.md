# RPF-53｜真实 Provider 跨域 Target-Agent 自主配置变更与独立 Effect 证据

- **Plan Revision:** `rev-1`
- **Status:** Partial
- **工作区:** `D:\CS\runproof`
- **分支 / base:** `codex/rpf-53-live-config-target-effect` / `3dfafb7fc286759f212166004e8558e02e0aba48`
- **remote:** `https://github.com/MyKr-YSteinsK/runproof.git`；预检时 `origin/main=bda0cd49e50e3181f604324e94877a24b9885334`，目标远端分支不存在。
- **主结果边界:** A-03 在 Plan 允许的两次 SDK fixture-only 诊断后仍失败；无真实 Provider 请求、Java 进程、业务 HTTP 或 Live Evidence。此结果不把 SDK/平台错误归因给 Agent，也不构成 Live model 失败。

## Gate 结果

| Gate | 状态 | 证据与限制 |
|---|---|---|
| A-01 来源与权限 | PASS | 精确 base、分支、origin、远端 main 和目标分支占用状态已核验。RPF-51 rev-4 公开源码 manifest：110 文件 / 393,800 bytes，SHA-256 `33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`；config-center JAR：66,981,576 bytes，SHA-256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。固定 Python 3.12.13、Pydantic AI 2.57.0、OpenAI 3.35.1 的记录完整性均为 0 mismatch；JDK 为 17.0.12。`DEEPSEEK_API_KEY` 仅以存在性布尔值检查，值未读取或写入。既有 `?? docs/reviews/` 保持未跟踪且未打开、枚举或改动。 |
| A-02 Live 合同、域隔离与预算 | PASS | 新建独立 `config_live_*` 合同、运行时、SDK child 与 verifier；固定 provider/model、来源锚、Loopback、密钥隔离、持久预算预留/未知 usage 停止、零自动重试及精确业务工具顺序。定向 16 项测试覆盖 source commit 错配、未注册工具、越序/错误参数写入不触达 HTTP、预算及 Host 失败响应。当前只证明本地实现/合同测试，不表示 Provider 或 HTTP Scenario 已完成。 |
| A-03 无付费 SDK 全工具预检 | FAIL | `attempt-01` 与允许的 `attempt-02` 均在 SDK import 阶段被 child 文件访问审计拒绝（`RPF53_FILE_ACCESS_DENIED`）；attempt-02 仅记录脱敏 basename `__init__.cpython-312.pyc`、`__init__.py`，未保存路径。两次各用独立 run ID 和不可覆盖 marker，实际 Provider HTTPS、业务 HTTP、Java 数均为 0。attempt-02 的冻结 runtime source SHA-256 为 `354fe032cf844cbefb2fedfdb99ed725820f86120ae99600908657bbfba48e18`。工具注册与四轮 completion 链未到达，离线 fake transport 子流程为 `NOT_RUN`。Plan 诊断额度已耗尽，未执行第三次。 |
| A-04 真实 Provider Target Tool Loop | NOT_RUN | A-03 未通过，未创建真实 Trial marker 或 Provider ledger；零 Provider HTTPS、零 token、费用 ¥0。 |
| A-05 真实 Java HTTP Effect | NOT_RUN | 未启动 Java/H2；零 health GET、零业务 HTTP、零 POST。无 Authority readback 或 Oracle 实验结果。 |
| A-06 独立 Live Evidence | NOT_RUN | 未生成 `config-live-evidence.json`；正确/缺失/错误锚 CLI 与 Live Evidence 篡改矩阵均未运行。没有签发成功 Witness。 |
| A-07 安全、回归与资源 | PASS | 最终干净隔离源码镜像的 Runtime suite：270 tests，19.360 秒，exit 0；2 个 Docker-dependent class setup 因 Docker provider 不可用而 SKIPPED。定向测试 16 项通过；RPF-43、44、48、49、50、51 rev-4、52 rev-3 七个历史锚 verifier 均 exit 0；Reviewed Artifacts、Public Docs（18 files / 7 pairs）及 `git diff --check` 通过。两次 SDK child 均安全退出；未启动 Java 或产生外部/业务请求。 |
| A-08 结果与 Git 交付 | PASS | 单一中文结果、README 与 Partial summary 纳入白名单；按 Plan 做 focused commit，并仅普通 push 到专属 feature branch，随后独立读取远端 SHA。无 PR、merge、main、release 或 deploy；精确 commit/ref SHA 及 main 状态见最终任务回执。 |

## 诊断与来源身份

| Attempt | Run ID | 结果 | 诊断事实 |
|---|---|---|---|
| 01 | `rpf53-diag-cf1867d638694e88` | FAIL / PLATFORM | `sdk_import` 阶段 `PermissionError` / `RPF53_FILE_ACCESS_DENIED`；旧摘要未包含文件名。Provider HTTPS 0、业务 HTTP 0、Java 0。result 812 bytes，SHA-256 `f43d760b18caa19cc2f86baf5183cd60d3f01457cb89a7ebc2ccf41fae09bc7e`。 |
| 02 | `rpf53-diag-0e8ca8ee1ed340ad` | FAIL / PLATFORM | 修正了子进程使用固定 SDK 不存在的 `httpx` 导入、改用环境中固定的 `httpx2`，并增加脱敏 basename 记录与回归；仍在 `sdk_import` 被同类文件访问审计拒绝。Provider HTTPS 0、业务 HTTP 0、Java 0。result 879 bytes，SHA-256 `3653be7e8ae77e9951efd2124542615be075c9111b5cfc37e275eacf23eab843`。 |

Attempt-02 冻结的运行时来源摘要为 `354fe032cf844cbefb2fedfdb99ed725820f86120ae99600908657bbfba48e18`。定向负控和格式收口后的最终代码摘要为 `65f5b217ab4a80a22ac705813e51079aa555a6e75201bd4fa3a43698940ff77d`；后者不冒充 attempt-02 身份，也没有用于任何 Live Trial。

## 费用、资源与信任边界

- 正式 Provider Trial：`NOT_STARTED`；Provider HTTPS requests `0`；Provider tokens `0`；估算费用 `¥0`。环境预检只确认 key 存在，不读取 key 值；child 环境构造不传递 Provider 或 config-center key。
- Java/H2、HTTP Authority、真实配置变更、业务违规判定、真实 Agent 行为、PGE、WorkSwarm：均 `NOT_RUN` / `NOT_PROVEN`。`business_violation=NOT_PROVEN`，不表示证明系统安全。
- 即使未来产生离线锚定 Evidence，issuer authenticity 和数据库独立权威仍需另行证明；Python audit hook 不能称为 OS sandbox。
- 本次换算采用 DeepSeek 官方 Flash 峰时 cache-miss 输入 USD 0.30/M、输出 USD 1.20/M，并使用预算系数 ¥15/USD（不是实时汇率报价）：[官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)。Tool Calls/API 行为参考[官方 Tool Calls 指南](https://api-docs.deepseek.com/guides/tool_calls/)及[Chat Completion API](https://api-docs.deepseek.com/api/create-chat-completion/)。该预算仅是预检上界；本轮没有实际请求或消费。

## 文件与清理

- Git 白名单内新增：`runtime/runproof_runtime/effectwitness/config_live_contracts.py`、`config_live_runtime.py`、`config_live_external.py`、`config_live_verify.py`、`runtime/tests/test_effectwitness_config_live.py`、`spikes/rpf-53/probe.py`、本目录 `README.md`、`RESULT.md`、`live-summary.json`。未生成 `config-live-evidence.json`。
- `.local/rpf-53/` 保留两份 fixture-only 诊断 marker/result、两套 task-owned SDK scratch、两份 base preflight、最终 Runtime regression 镜像及日志；没有 Provider ledger、正式 Scenario marker、Java 日志或 Evidence。第一次 Runtime 镜像立即复跑时遇到一次 Windows loopback connection reset；改用全新隔离镜像后的最终 270 项 suite 通过。尝试清理已创建的旧隔离镜像时 PowerShell 删除命令被工具策略拒绝，因此保留在忽略目录，没有改用其他删除方式。
- Git 只处理本 Plan 白名单路径。旧 RPF-43～52 artifacts 未改写；`docs/project/**`、`docs/history/**`、CI、Web 与 Control Plane 未更改。用户目录 `docs/reviews/` 未触碰。

**FROZEN:** Provider 真实 Trial、Java/H2 与 Live Evidence 因 A-03 未通过而不运行。**DELEGATED_TO_CODEX:** 已完成 rev-1 白名单代码、定向与全 Runtime 验收、脱敏 Partial 记录及 feature-branch 交付；没有扩大诊断、费用或生产权限。后续必须在新授权下解决子进程文件访问边界并重新冻结来源身份。
