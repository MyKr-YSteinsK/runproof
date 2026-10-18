# RPF-52 rev-2：跨域 SDK 配置工具闭环补验收

本轮从 `5d0fa1f81c8362f9eb27fe893756fe8f95fc9e3f` 建立专用分支
`codex/rpf-52-rev2-config-target-sdk-recovery`，只修复 rev-1 的协议/结果分类并执行一次全新的零 Provider Fixture 场景。rev-1 的 `RESULT.md`、源码锚和本地一次性状态作为历史保留，不复用其 run ID、端口、marker、日志或证据路径。

## 修复内容

- 成功 envelope 必须是 HTTP `200` 且 JSON `code: 0`；初始不存在必须是 HTTP `404` 且 JSON `code: 4041`。HTTP 状态与 JSON 业务码分别校验。
- 缺少 SDK、工具链或必要 Authority 事实时，Oracle 返回 `INCONCLUSIVE`，Run Outcome 为 `PLATFORM_ERROR`；`agent_failure` 与 `business_violation` 保持 `NOT_PROVEN`。诊断违规项仍可保留，不能据此签发业务违规 Witness。
- 失败的 inspect/create 回包会关闭后续写入；update 前重新检查 inspect/create 的完整 envelope 和版本/值。
- 新运行数据仅写入被忽略的 `.local/rpf-52-rev2/`。运行 JAR 是从已核验的 rev-4 精确 JAR 复制到该目录后再启动；SDK 使用固定 CPython 3.12.13 直接运行，并只读引用固定 RPF-48 SDK 分发目录，不下载依赖。Windows Application Control 拒绝启动本地 venv 解释器，因此正式 child 绑定到已验证的固定解释器身份。

## 执行顺序

先完成协议单测、静态检查、Runtime 回归和 SDK/JAR 身份预检，再冻结一次新的 preflight：

```powershell
python -B -m unittest runtime.tests.test_effectwitness_config_target -v
python -B spikes/rpf-52/probe.py --prepare
python -B spikes/rpf-52/probe.py --run-scenario
```

`--prepare` 只创建本轮 preflight 并校验任务专属 JAR 副本和 SDK 身份；正式 Scenario 由唯一一次 `--run-scenario` 启动。marker 写入后禁止重置或重跑。成功 Evidence 仅可能写到本目录的 `config-target-fixture-evidence.json`；完整验收结论写入 `RESULT.md`。Fixture 不证明真实模型自主决策、生产真实性、数据库级独立权威或独立复现。
