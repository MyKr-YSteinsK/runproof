# RPF-70：Owner/Source 运行时接缝

本目录保存 RPF-70/rev-1 的独立兼容性验证。运行时采用严格版本化的 `OwnerScope`、`SourceCapsule` 和 `AuthorizedOperation`；新 Port 在准备环境、Tool 调用、实际业务入口、独立 Authority 读回和清理前执行授权检查。

模型响应来自 scripted fixture，业务运行于本地 Java/H2 HTTP 与虚构订单 SQLite。Provider 调用、真实模型 usage、费用和 Key 读取均为 0。预算/WAL、SDK child guard 和业务算法沿用冻结的原模块；完整公共 Core 迁移、真实 Provider、Issuer、L2、第三域和 Web 均未建立。

## 入口

从仓库根执行，所有新运行产物仅可位于此前已通过 G0 的 `.local/rpf-70/`。入口使用 `xb` marker；不能清空 marker、重跑同一目录或借用旧任务额度。

```powershell
python -X utf8 -B spikes/rpf-70/probe.py normal
python -X utf8 -B spikes/rpf-70/probe.py fault
python -X utf8 -B spikes/rpf-70/probe.py verify --path .local/rpf-70/fault-manifest.json --sha256 <实际原文件SHA256>
```

`normal-corrective` 是本 Plan 有限纠错额度内的一次独立入口，使用自己的 marker、新 run/DB/WAL。它不覆盖首次 normal 结果。本轮实际使用记录见 [RESULT.md](RESULT.md)。离线 CLI：合法原 SHA 返回 0、缺 SHA 返回 2、原 SHA 错误或语义拒绝返回 3。

`pre-execution` 是负控入口：读取重锚的操作请求，经真实新 Port 的 prepare/invoke 路径；仅在 native 副作用入口安装 tripwire。它验证拒绝发生在 native 业务之前，不能独自证明业务完成。正常/故障正式场景另行执行真实业务和 Reader。

## 证据入口

- [RESULT.md](RESULT.md)：单一中文 TASK_RESULT、对象流向、验收与建议。
- [source-identity-map.json](source-identity-map.json)：全部新执行源码、复用 native 源码的 raw/LF、固定 SDK/JAR pin。
- [verification-diagnostic.json](verification-diagnostic.json)：本轮命令/PID/退出码/日志 SHA、会话摘要、独立读回、OS 二读和历史 CLI。
- [ownership-negative-controls.json](ownership-negative-controls.json)：逐件重锚 CLI 的变异、拒绝和有效性分类。
- [migration-matrix.json](migration-matrix.json)、[capability-assessment.json](capability-assessment.json)、[architecture-decision.json](architecture-decision.json)：执行职责及未证明边界。

完整本轮 WAL、manifest、数据库、日志和变异原件仅保存在 ignored 任务根；公开文件保留其 hash、命令与必要脱敏摘录。历史 RPF66/67/68/69 原件继续由各自原生 CLI 验证；新 manifest 不签发历史结论。

## 范围

该接缝约束可信 controller 装配的两个具体 Port。它不提供针对任意恶意 Python 代码的 OS 沙箱、任意 callable 执行、动态插件、生产权限、签发权或发布权。Authority 结果仍来自独立 HTTP GET / SQLite `mode=ro`，不采用模型文字判断。
