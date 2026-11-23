# RunProof 运行与恢复

## 环境

从 `MyKr-YSteinsK/runproof` 的实际 Git 根工作。动手前核对根、分支、HEAD、远端、目标路径状态和既有用户改动。Windows 上用已确认的 CPython 可执行文件运行 Python 命令。Python Install Manager 别名曾触发意外安装。

| 部件 | 安装与版本依据 | 2026-11-23 核验 |
| --- | --- | --- |
| Web | `package-lock.json`。新工作区用 `npm ci` 准备依赖，CI 配置使用 Node 22 | Node 24.16.0，本机 Vite、Vitest、TypeScript、React 与锁文件相符 |
| Python Runtime | CI 用 CPython 3.12。`runtime/requirements.txt` 是可选 OTel 路径，SDK 和 JiuwenSwarm 有各自依赖入口 | 本机 CPython 3.14.6 聚焦测试。按相应工作流判断 SDK 版本及兼容性 |
| Java Control Plane | Java 17、Maven、`control-plane/pom.xml` | Java 17.0.12、Maven 3.9.16。离线测试与打包通过。完整多服务运行沿用历史验收 |
| 本机业务环境 | Golden Demo 参照 Docker、PostgreSQL 与 lifecycle；竞赛入口使用本机 Node、CPython SQLite、PowerShell 7.2+ | 本轮审阅与静态复核。新的受控业务会话需要独立目标与资源范围 |

## 快速校验

按修改选取，在仓库根运行。`python` 表示已核对的解释器。在当前 Windows 终端可用 `& $runproofPython` 调用其确切路径。

```powershell
npm test
npm run build
python -B -m unittest -v runtime.tests.test_control_plane_client runtime.tests.test_durable_worker
python -B ci/verify-public-docs.py
python -B runtime/verify-reviewed-artifacts.py
python -B demo/verify-golden-demo.py --root . --json
mvn -q -B test package -f control-plane/pom.xml
```

`npm run build` 包含 TypeScript 检查。Web 构建可通过 `npm run build -- --outDir .local/<task>/web-dist` 写入隔离目录。测试临时文件可将 `TEMP`、`TMP`、`TMPDIR` 导向任务的 `.local/<task>/tmp`。Maven 缓存充足时可用 `-o` 离线复验。本轮 Web、聚焦 Python、Java 与静态证据核查结果见 [CURRENT_STATE](../project/CURRENT_STATE.md)。

## 启动和取证入口

| 目的 | 使用的入口 | 输出及边界 |
| --- | --- | --- |
| Golden Demo | [Demo 指南](../DEMO.zh-CN.md)，`demo/start-demo.ps1` 与 `demo/stop-demo.ps1` | Web `127.0.0.1:4173`，使用 reviewed corpus 和受控服务。仅对本次 owner 使用停止入口。 |
| 记录工作台 | [交付指南](../EFFECTWITNESS_DELIVERY.zh-CN.md)，`demo/effectwitness-delivery.ps1` | 记录型 `/effectwitness/workbench`，独立历史 Evidence。预览服务只读。 |
| 离线参考 Agent | [完整项目包启动](../../demo/competition-bundle/README-COMPLETE.zh-CN.md) · [本地产品指南](../EFFECTWITNESS_LOCAL_PRODUCT.zh-CN.md) | 单会话受控写入和独立 Witness 验证。使用新、受限 owner，记录端口与进程归属。RPF-114 的实际封存见 [RESULT](../../spikes/rpf-114/RESULT.md)。 |
| Live Explorer 或新的物理预算实验 | 对应任务授权、源和 active gate；先读 [当前风险](../project/CURRENT_STATE.md#安全ci-与本地现场) | 观察真实用量、停止条件和能独立核验的回执。旧 UNKNOWN 或预算缺失时保留现场。 |

## 数据和产物

- `runtime/reviewed-*.json` 是已审阅的 synthetic / controlled corpus，供 Web、verifier 和 Demo 使用。按当次运行的 source identity 查源，保留原字节、编码与换行。历史 ZIP 和 PPT 等索引见 [归档](../history/MAINTENANCE_ARCHIVE.md)。
- `spikes/` 同时含实验入口与冻结证据。CI 和 Demo 仍引用其中一部分。`ci-results/` 与 `.local/` 的旧输出按来源、owner、证据身份保留。新增产物按本次任务的隔离路径记录。
- `docs/delete/` 为用户手工清理区。复用旧生成物前核对依赖版本与身份，通常按锁文件重建更可控。凭据、原始账本、私密日志与真实业务数据留在授权环境。
- 外部 `config-center` 只进行了源码审阅。未来联动采用明确版本的新本地实例、独立环境与合成配置，具体执行待用户审批。[联动方案](UPGRADE_REVIEW.md)

## CI 和交付

普通授权交付沿用 `main` 及 scoped commit/push。检查 GitHub 身份和目标远端，核对推送可能触发的工作流，推送后读回 SHA、关键文件和运行状态。Canonical Gate 是发行证据，失败时保留状态与 required coverage。旧手动 Provider 或 conformance workflow 有独立授权和预算，任何一轮的旧配置不自动续用。
