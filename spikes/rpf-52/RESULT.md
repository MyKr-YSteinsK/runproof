# TASK_RESULT

## 1. 结论

- **Plan ID / Revision：** `RPF-52 / rev-1`
- **Status：Partial**
- **判定：** 唯一一次真实场景在 `AUTHORITY_INITIAL` 阶段停止。服务真实启动并接受了只读 HTTP 请求，但探针把 config-center 的成功 envelope 业务码错误地要求为 `200`；真实服务及 RPF-51 rev-4 合同使用 `code: 0` 表示 HTTP 200 成功。因初始 history 被误判为无效，真实 Pydantic AI SDK 子进程没有启动，没有 SDK Tool Loop、业务写入或成功证据。运行后已按 RPF-51 合同将当前源码中的成功码校正为 `0`，并通过静态测试；该修正没有、也不会通过重跑真实场景来验证，因为 Plan 的一次性 marker 已消耗。
- 本次输出中的 `VIOLATION_CONFIRMED` 是旧检查条件不匹配导致的探针裁决，不能作为 config-center 业务违规或 Target Agent 失败证据。此运行应按平台/探针合同缺陷归类；业务效果为未执行，最终为 `INCONCLUSIVE`。

## 2. 仓库、边界与交付身份

- 仓库：`MyKr-YSteinsK/runproof`；远端为计划指定的 GitHub 仓库。基线和当前分支起点均为 `151922a9b891ce9aa6f2d62639109e435f98c8ab`，分支为 `codex/rpf-52-config-target-sdk-fixture`。执行前远端该功能分支不存在；远端 `main` 为 `bda0cd49e50e3181f604324e94877a24b9885334`，与计划冻结值一致。
- 初始及最终状态中可见 `?? docs/reviews/`。该目录内容未读取、未枚举、未修改、未暂存；其余本任务改动均为计划白名单新文件。
- 新建文件：`config_target_contracts.py`（RPF-52 schema/工具合同）、`config_target_bridge.py`（受限工具 Host 与 HTTP 绑定）、`config_target_external.py`（隔离 SDK 子进程入口）、`config_target_verify.py`（纯离线证据核验）、`test_effectwitness_config_target.py`（确定性测试）、`spikes/rpf-52/probe.py`（预检与单次场景编排）、本目录 `README.md` 和本 `RESULT.md`。未修改 `contracts.py`、任何 RPF-51/旧 Witness、`docs/project/**`、`docs/history/**` 或其它受保护路径；未生成 `config-target-fixture-evidence.json`。
- 分支提交及 push SHA 不能由本文件自我引用，最终 commit SHA、远端分支 SHA 和 fresh `main` SHA 由任务聊天回执补充。未授权或执行 PR、merge、deploy、release。

## 3. 冻结身份与真实运行观察

- Run ID：`rpf52-12dbaef49492441981f925595abe116d`。预检 SHA-256：`a2d3e9b6a26306ea138168cee6e288e31fb84d93ecf57630c78e50989e0867de`。
- 外部只读源码：`config-center@0258b9cef02ea74a40989d035c79256c776409c0`；manifest 110 个文件、393,800 bytes，SHA-256 `33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`。JAR 66,981,576 bytes，SHA-256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。
- Java 使用 direct JDK `17.0.12`。真实 Java PID/唯一 listener PID 均为 `33468`，端口 `9569`，loopback health GET 为 `200 / UP`。Agent Host 预留端口 `9570`。Java argv 使用环境变量占位符；API key 未进入 SDK 子进程或证据。
- SDK 分发来自只读固定 RPF-48 包目录并核对 RECORD：Python `3.12.13`、`pydantic-ai-slim 2.57.0`、`openai 3.35.1`；两分发的 RECORD 已核验条目分别为 443/444 与 1999/2000，哈希不匹配均为 0。Pydantic AI 入口源码 SHA-256 `70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa`；OpenAI 源码 SHA-256 `8f4fdba5193967d09ca79bc4504e79bd8c20ba4bd8f09c2df3817501540a39db`。
- 场景实际执行 13,455 ms，在一条 health GET 后观测到 5 条只读业务 GET：`initial_current=404/code 4041`、`initial_history=200/code 0/data []`、`final_current=404/code 4041`、`final_history=200/code 0/data []`、`final_list=200/code 0/data []`。这表明合成 namespace 初始不存在且没有写入；后 3 条是停止时的只读对账。没有 POST。
- 运行阶段：`AUTHORITY_INITIAL`；fixture completion `0`、SDK Tool Call `0`、SDK 子进程未启动（PID `0`，状态 `NOT_COMPLETED`）、SDK ready 未达成。业务 HTTP 共 `5/8`，health GET `1/3`。Provider HTTPS attempts/requests、tokens、费用均为 `0`；父进程和 Java 的外部连接记录为空。
- Java 进程最终已退出，端口已关闭；停止记录的进程 exit code 为 `1`，因此这里仅报告进程退出和端口关闭，不将退出码表述为正常码。Java 日志 5,098 bytes，SHA-256 `f00ce78c2453795becb3411cec20c6849400ab0379b6c138f95d7b631b22edd1`；日志 reader 已停止、overflow=false、API key 匹配数为 0。SDK child 与 Agent Host 也已关闭/未遗留。

## 4. 源码身份与合同修正

- 真实运行冻结的 Runtime source identity：`d2aacad013fea8bde963085f897defbd1bec9422be25afccb2f6169a6d8c29a8`。该值及对应单次运行记录保留不变。
- 运行后根据 RPF-51 rev-4 `config_http_oracle` / Witness 已使用的成功响应合同，将 RPF-52 bridge、Oracle、probe 和测试中的 HTTP 200 成功 envelope `code` 从错误预期 `200` 修正为 `0`。当前源码 identity 为 `cbf17f2122df311ae0381ab6716c19d55c71620bad32081e8e391d6e0dcaca98`。这是 post-run 静态修正，未进入已冻结场景，也没有 live 验证；不把当前 identity 倒填到运行记录。
- 本轮选择在 `config_target_*` 中隔离新 schema/工具链，并保留旧 `config_http_*` 与 RPF-48/49 订单合同。没有把 RPF-51 的固定 11 请求 Witness 套用到新工具时序。

## 5. 证据及验收状态

- **没有成功 evidence 文件**，因此无 evidence 字节数/SHA、外部锚 exit `0/2/3` 结果，也没有执行四类重新计算 SHA 的篡改负控。未生成或伪造 SDK execution、Target effect、Tool Call lineage 或成功 Witness。
- A-01：PASS（基线、分支、远端状态及保护边界核对；reviews 未触碰）。A-02：PASS（静态合同、工具 allowlist 与既有 schema 隔离由定向测试覆盖）。A-03：NOT SATISFIED（真实 SDK 未启动）。A-04：NOT SATISFIED（Java 服务与只读 HTTP 可用，但无 SDK 工具调用和业务写效果）。A-05：NOT RUN（无有效场景证据）。A-06：PASS（预算未超、0 Provider/Token/费用、无外连、key 日志匹配为 0、Java/端口已关闭；Java exit code 1 已如实保留）。A-07：PASS，具体命令结果见下。A-08：RESULT 已形成；提交/push 与远端 SHA 由聊天回执报告。
- RPF-52 定向测试：`python -B -m unittest runtime.tests.test_effectwitness_config_target -v`，15/15 PASS。探针 `--help` 正常退出；静态检查确认当前 `_check_initial_state` 接受业务码 `0`，拒绝 `200`（`REAL_ENVELOPE_CODE_CONTRACT_PASS`）。
- 完整 Runtime 回归在 `.local/rpf-52/runtime-regression-src` 的任务本地源码副本上运行，命令为 `python -B -m unittest discover -s runtime/tests -p 'test_*.py' -v`：242 tests，`OK (skipped=2)`。两个 skip 为 Docker 不可用的 `test_docker_integration` 与 `test_rpf05_runtime`。该副本包含本轮 5 个 Runtime/测试文件；没有覆盖或读取其它 RPF 旧运行目录。
- `python -B runtime/verify-reviewed-artifacts.py`：PASS；`python -B ci/verify-public-docs.py`：`PUBLIC_DOCS_PASS files=18 pairs=7`；`git diff --check`：PASS。Golden demo 未运行，记为 NOT_APPLICABLE（本轮新增隔离模块未影响该路径）。
- 历史样本核验均 PASS：RPF-43 `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e`；RPF-44 `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873`；RPF-48 `c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2`；RPF-49 `04ac629bbfb54a4b85eddf902bbf765db7c57ea0c509e0b539280858c7d4bc9b`；RPF-50 `b8f288db5dd76a142bbfb69a04d15ce9206d2cd9dbe28ef6effdb59382f5ef4a`；RPF-51 rev-4 `c569bd62a6691c84e8995359578fc4ff34f0ea417158a0c0893309c029df363d`。RPF-51 readiness diagnostic 保持 4,692 bytes，SHA-256 `b98842e65a62a68355e426cb6411a486180604fbb4d30d3daef39c3ae68e0533`。

## 6. 临时资源与后续边界

- `.local/rpf-52/` 保留本任务预检、scenario marker/result、日志、SDK venv/tmp、Java tmp，以及完整 Runtime 回归副本和压缩归档；测量任务文件总量约 9,152,126 bytes。删除这两个回归临时产物的精确清理操作被命令安全策略拒绝；未尝试用其它机制绕过。它们位于被忽略的任务本地目录，不会暂存或提交。旧 `.local/rpf-48/**`、`rpf-49/**`、`rpf-51*/**` 未清理或重置。
- `scenario-started.json` 已存在且不重置；本 Plan 不再执行 `--prepare` 或 `--run-scenario`。若要验证修正后的 SDK 闭环，必须由新 Plan 授权一个新的 run ID/marker、完整 preflight 和一次新场景。任何真实 Provider/PGE 试验仍需另行确定预算、凭据与副作用边界。本次不声称模型自主决策、数据库级独立权威、签发者真实性或独立复现。
