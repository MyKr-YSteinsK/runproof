# RPF-51 TASK_RESULT

- **Plan ID:** RPF-51
- **Revision:** rev-1
- **Status:** PARTIAL
- **日期：** 2026-10-18
- **仓库 / 分支：** RunProof / `codex/rpf-51-config-center-http-effect`
- **唯一主结果：** 本文件

## 验收

| ID | 状态 | 证据与边界 |
|---|---|---|
| A-01 来源、工作区、权限 | PASS | RunProof parent、origin、分支与 config-center 精确源提交已核实；相邻仓库只读。`git status` 仅显示既有 `?? docs/reviews/` 行；该目录内容未读取、列举、打开或触及。 |
| A-02 版本化合同和权限 | PASS | Execution、Effect、Experiment 已冻结并写入 task-local preflight；端口、源码清单、JAR、运行时源码哈希和预算均有绑定。13 项定向测试通过。 |
| A-03 独立 HTTP 服务 | FAIL | 隔离 JAR 构建成功，但服务在 readiness 前因 `ApiKeyProperties` 绑定失败而退出；没有确认 ready 的服务实例。失败原因为 harness 启动属性列表覆盖，见下文。 |
| A-04 真实业务 Effect | NOT_RUN | 未发送任何 HTTP 请求；没有配置变更、stale 请求或业务 Oracle 结论。 |
| A-05 独立 Witness | NOT_RUN | 未生成 `spikes/rpf-51/config-http-witness.json`，因此没有真实 Witness 的外部锚、缺锚或错锚 CLI 结果。没有用合成内容替代真实证书。 |
| A-06 防伪与业务负控 | PASS | 新测试通过，覆盖固定 HTTP 目标/方法、redirect 与 timeout 不重试、未授权成功伪造、stale 版本、历史重复/重算哈希、错误 issuer 和锚定。真实 HTTP token 负控未运行，因为服务未进入 readiness。 |
| A-07 回归、成本、清理 | FAIL | 完整 Runtime 回归 213 项通过、2 项 Docker 相关测试因 Docker provider 不可用而跳过；RPF-43/44/48/49/50 锚定 verifier 和两项仓库检查通过。Provider/token/费用均为 0；自有 Java 子进程已退出，冻结端口无监听。任务临时产物清理命令被本机策略在执行前拒绝；按 Plan 未改用其它删除/移动方式，`.local/rpf-51/` 保留 2,248 个文件、182,005,301 bytes。 |
| A-08 Git 与唯一 TASK_RESULT | FAIL | 本文件、实现和测试按 Plan 白名单交付；但真实 Witness 缺失，故不能满足包含真实证书的完整交付标准。分支 push 与独立 SHA 核验结果在最终任务回执报告；无 PR、merge、tag、release 或 deploy。 |

Plan 明确要求只有成功的 Java HTTP 闭环才可标为 COMPLETE，因此整体为 PARTIAL。此结果没有证明 config-center 的业务 Effect，也不是业务违规、Agent 失败或 Evidence Acceptance。

## 来源与隔离构建

- RunProof 精确 parent：`b3271eaaf408dffa1ecd6f26f1b47fab5cede289`。
- config-center 只读源提交：`0258b9cef02ea74a40989d035c79256c776409c0`；原 checkout 的工作区与索引保持干净。隔离副本来自该提交的公开 Git archive，共 110 个源码文件、393,800 bytes。
- 源清单 SHA-256：`33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`。
- Java：17.0.12；Maven：3.9.16。
- 隔离 Maven package 命令使用 `-pl config-center-server -am package -Dmaven.test.skip=true`，exit 0，耗时 151.472 秒。生成 JAR 为 66,981,576 bytes，SHA-256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。该构建没有运行 config-center 的 Java 测试。
- Maven 独立 task-local repository 最终为 106,283,193 bytes；Maven `-ntp` 日志未提供可单独核对的网络传输总字节。构建未重试，也未再进行依赖下载。

## 合同与真实运行尝试

冻结合同摘要：

- run id：`rpf51-7f1e3a9c87114599a518068625653a73`；冻结 loopback 端口：`8421`。
- RunProof runtime source SHA-256：`c6784f4a4a84b7c9ff903702c58f4b94af2363670c78420a93a29c1648440c5f`。
- Execution / Effect / Experiment SHA-256：`287800df6cc13a589f6c912750cdf108f2f098d4b4435430c0e390120c2d26b4` / `b9ec8e6938a6be7bec72c74a8cdbcfe9a5b251048c01f7da6234a51d2c0248a9` / `a589b75ce0a57142ce45dc61d5b62b9c84770cf64188f01acc99d90e12f5169d`。
- provider requests：0；tokens：0；费用：¥0。
- 唯一 `--run` 启动自有 Java 子进程后，进程在 readiness 等待阶段退出，失败码 `OWNED_SERVICE_EXITED_BEFORE_READY`。启动日志显示 `security.apiKeys[0].key` 绑定值为空。结合启动命令以命令行属性单独覆盖同一列表的 `app/env` 项、而 API key 由 `CONFIG_CENTER_API_KEY` 环境变量供 YAML 展开，根因判断为 Spring 列表属性覆盖使 key 项丢失；这是 harness 启动配置问题，不是 config-center 业务结果。
- 失败发生于第一条 HTTP 前：实际 HTTP 请求数为 0，没有 POST，也没有用户或外部 config-center 状态改变。该子进程自行退出；事后没有 Java 进程，端口 8421 无监听。由于未达到 readiness，失败记录没有持久化 PID/run record。
- 一次性 `started` 标记已消费。按 Plan 的 1 个真实 Scenario 配额，不清除标记、不复用预留合同、不重跑。后续代码修正和新 Scenario 需要新的授权任务/合同。

## 回归与历史证据

- 定向命令：`py -3.14 -B -m unittest runtime.tests.test_effectwitness_config_http -v` — 13 tests，PASS。
- 全 Runtime 命令：`py -3.14 -B -m unittest discover -s runtime/tests -p 'test_*.py' -v` — 在 `.local/rpf-51/regression-src2` 的干净隔离副本执行；213 tests，PASS，2 skipped（Docker provider unavailable）。首个测试副本缺少只读 RPF-50 `probe.py` 源文件而产生 `SOURCE_FILE_UNAVAILABLE`；补足夹具后在新的干净副本重跑通过，原仓库的历史本地目录未作为测试输出目录。
- 历史 SHA 锚 verifier：RPF-43 `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e`、RPF-44 `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873`、RPF-48 `c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2`、RPF-49 `04ac629bbfb54a4b85eddf902bbf765db7c57ea0c509e0b539280858c7d4bc9b`、RPF-50 `b8f288db5dd76a142bbfb69a04d15ce9206d2cd9dbe28ef6effdb59382f5ef4a` — 全部 exit 0，均报告 anchored/content-verified 状态。
- `py -3.14 -B runtime/verify-reviewed-artifacts.py` — exit 0。
- `py -3.14 -B ci/verify-public-docs.py` — exit 0，18 files / 7 pairs。
- 新 Witness 的 correct/missing/wrong anchor exit code 语义由 13 项定向测试中的合成单测覆盖；没有真实 RPF-51 文件可供独立核验。

## 隔离与交付边界

RunProof 改动限于 `config_http_contracts.py`、`config_http_adapter.py`、`config_http_oracle.py`、`config_http_witness.py`、对应测试，以及本目录 `probe.py`、本文件和 `README.md`。不写入 config-center checkout，不改 Project State、旧 spike 或 CI；`docs/reviews/**` 保持未触及。清理命令被本机策略在执行前拒绝，没有文件被删除；没有尝试替代递归删除或移动操作。临时源码/build/test 副本与 preflight、started/failure 记录、source manifest、构建/启动日志仍留在 ignored `.local/rpf-51/` 中，共 2,248 个文件、182,005,301 bytes；其中保留失败日志以支持复核。

分支 `codex/rpf-51-config-center-http-effect` 从上述精确 parent 建立。push 前 origin `main` 为 `bda0cd49e50e3181f604324e94877a24b9885334`，目标 feature ref 当时不存在。经检查的 Release Gate 仅在 `main` push、指向 `main` 的 PR 或手动触发时运行，没有发布/部署动作。最终 feature ref 与 main 的远端观察值由本任务回执给出，避免在此文件内产生自指 SHA。
