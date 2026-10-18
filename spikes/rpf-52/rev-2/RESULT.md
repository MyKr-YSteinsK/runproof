# RPF-52 rev-2 TASK_RESULT：跨域 SDK 配置工具闭环补验收

- **Status: Partial**
- **Run Outcome:** `PLATFORM_ERROR`；`agent_failure=NOT_PROVEN`
- **Effect Contract Outcome:** `INCONCLUSIVE`；`business_violation=NOT_PROVEN`
- **Fault Activation:** `NOT_TRIGGERED`
- **Attribution:** `NOT_ESTABLISHED`
- **Reproduction:** `NOT_TESTED`
- **Repository:** `D:\CS\runproof`
- **Base / branch:** `5d0fa1f81c8362f9eb27fe893756fe8f95fc9e3f` / `codex/rpf-52-rev2-config-target-sdk-recovery`
- **Plan / run:** RPF-52 rev-2 / `rpf52-e66fa8866f2e43bab5484b609430ba0e`

## 结论

rev-1 的 HTTP status 与 JSON business code 混淆、缺少执行事实时误报业务违规问题已修复并通过回归。rev-2 唯一正式 Scenario 已消费一次性 marker；Java 服务健康就绪，SDK child 向 Host 报告了固定 SDK/Python 身份，但 child 随后以 `SDK_ERROR`、exit code 1 结束，未产生任何 completion 或 SDK tool call。该运行没有提交业务 POST，也没有发现业务违规。按合同保留 `PARTIAL`，不重置 marker、不重跑 Scenario、不生成合成 Evidence。

## 实际运行事实

- 冻结 preflight：`.local/rpf-52-rev2/preflight.json`，7,518 bytes，SHA-256 `af51ac17251b16e43cf808378e23b66701d7c22b7cde2bd93c7ce352bd6acc0a`。运行时源码身份 SHA-256 `6358e63ef3557b1f8ca55c9549940f0f5a68e77c93425e0dbf5fa7257b6fbb60`。基础分支和 remote main 与 Plan 相符；rev-2 远端分支在运行前不存在。
- 只读输入身份：config-center commit `0258b9cef02ea74a40989d035c79256c776409c0`；110 个源码文件 manifest SHA-256 `33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`；JAR 66,981,576 bytes，SHA-256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。运行使用 task-owned JAR 副本。
- SDK：CPython `3.12.13`，pydantic-ai-slim `2.57.0`，OpenAI `3.35.1`；两份 pinned RECORD 均 0 mismatch。正式 child 的 `/ready` 身份握手通过，报告的 SDK 与 OpenAI 源码 SHA 分别为 `70863339252f37faf8a0f30bb3503210e99725f5721a2932f3c14bcc359b57fa` 和 `8f4fdba5193967d09ca79bc4504e79bd8c20ba4bd8f09c2df3817501540a39db`。
- Java 17.0.12 直接 JDK 启动；PID 与 listener PID 均为 `29204`，health 为 HTTP `200` / `UP`。controlled stop 后进程退出；Java log 为 5,052 bytes，SHA-256 `986f49a9c8370353e884e1ff0489ed54f70c3c106cff1d7e0755c4fa84cab92f`，secret redact 匹配数为 0。
- Authority 观察：`initial_current` 为 HTTP `404/code 4041`；`initial_history` 为 HTTP `200/code 0/data []`。SDK 失败后只读调和得到 `final_current` HTTP `404/code 4041`、`final_history` HTTP `200/code 0/data []`、`final_list` HTTP `200/code 0/data []`。五个业务请求全部为 GET；POST 为 0；tool trace、completion 均为 0。最终状态仍为空。
- Oracle：`INCONCLUSIVE / PLATFORM_ERROR`。它保留了缺失 inspect/create/update、缺失工具 lineage 和 final readback 的诊断项；执行完整性 gate 将业务违规结论压为 `NOT_PROVEN`。SDK 失败的 child `stage/error_type` 与 Fixture Host 首个拒绝码未被本次本地结果持久化，因此不能可靠归因到具体 SDK/Host 子接口。
- 预算：正式 Scenario 仅 1 次，18,422 ms；health GET 1 / 上限 3，业务 HTTP 5 / 上限 8（目标成功链为 8），Fixture completions 0 / 上限 5，SDK tool calls 0 / 上限 3，Provider HTTPS/API 0，tokens 0，费用 ¥0。
- 安全与清理：SDK child 仅连接 `127.0.0.1`；Java、SDK child 与 Host 均结束，端口 `8056/8057` 现已释放；记录的 SDK/父进程外连均为空。marker SHA-256 `935a23b717b4e15bc198b824d5d1575b28ed982af17c6679064aac5b6e7ecc40`；scenario result 为 7,734 bytes，SHA-256 `72eee61eb751b61aba01f9814f9dc492ab0d726c75c40f5d14d9fe8d8f28b4b0`。
- 未生成 `config-target-fixture-evidence.json`，也未运行针对成功 Evidence 的离线锚验证；没有用模拟样本替代真实 Evidence。

## A-01～A-08

| Gate | 状态 | 事实 |
|---|---|---|
| A-01 身份和历史保护 | PASS | 精确 base/branch 与 remote main 已在 preflight 及冻结复核中核验；index 未暂存；rev-1 路径及 `.local/rpf-52/**` 未读写；`docs/reviews/` 未读取或触碰，继续保持未跟踪。 |
| A-02 旧协议修正与防误报 | PASS | 成功 `200/code 0`、初始不存在 `404/code 4041` 独立校验；失败 envelope 会阻止后续写入；rev-1 五次只读 GET/零 SDK 负控为 `INCONCLUSIVE / PLATFORM_ERROR`。RPF-52 定向 20 项通过。 |
| A-03 真实 Pydantic AI Fixture Tool Loop | FAIL | child readiness 与 SDK 源身份通过；正式 SDK child 为 `SDK_ERROR`，exit 1、0 completion、0 tool call、0 tool return。无 Provider 调用。 |
| A-04 真实 HTTP Effect 与 Oracle | FAIL | Java/H2 服务 health 通过；没有业务 POST 或目标配置变更，无法达到 8 请求、v2/version 2 与 history `[2,1]` 的成功合同。Oracle 正确降级为平台错误且不判业务违规。 |
| A-05 有锚离线 Evidence | NOT_RUN | A-03/A-04 未通过，因此未生成或验证成功 Evidence；签发者真实性仍未建立。 |
| A-06 安全与预算 | PASS | 唯一正式运行、计数均未超过上限、0 Provider/0 tokens/¥0；进程、端口和外连检查通过。 |
| A-07 回归与兼容 | PASS | 隔离源码副本全 Runtime `247` 项通过、`2` 项因 Docker provider 不可用而跳过；Reviewed Artifacts、Public Docs 及 RPF-43/44/48/49/50/51-rev-4 历史锚均通过。Golden Demo 未运行，因本次不涉及 Demo。 |
| A-08 Git 与结果交付 | PASS | 本 README、此 TASK_RESULT 与白名单源码按授权聚焦提交并普通 push 至 rev-2 分支；最终 SHA、远端 ref 与 main 未变事实由本任务回执报告。无 PR、merge、release 或 deploy。 |

## 修复、验证和运行环境说明

- 修复范围限于 `config_target_contracts.py`、`config_target_bridge.py`、`config_target_external.py`、`config_target_verify.py`、`test_effectwitness_config_target.py` 与原 RPF-52 probe。新增协议表驱动测试、零 SDK/零 POST 平台错误负控、read-only SDK guard 回归，以及 rev-2 独立任务根/身份/结果路径。
- 预检期间 Windows Application Control 拒绝启动本地生成的 venv 解释器（`WinError 4551`）；此时未启动服务或写入 preflight。随后改用已验证的固定 CPython 3.12.13 直接运行，并从 RPF-48 pinned `site-packages` 只读加载 SDK。正式 SDK 在 `/ready` 后未完成 completion；child 阶段和异常类型未保存，不能将预检成功当作正式工具闭环通过，也不能进一步归因。
- SDK 文件守卫增加了对当前固定解释器实际解析后 runtime root 的只读访问；原因是 Windows 应用容器将标准库映射到该解释器自己的 `LocalCache` 路径。真实 SDK 的 Fixture-only 只读预检使用一个 synthetic `inspect_config`：2 次固定 completion、1 次 tool callback、0 tokens、0 业务 HTTP 写入、无 guard denial；该预检不计入正式 Scenario，也不证明正式闭环。
- 环境策略拒绝删除本轮创建的诊断脚本；按合同保留于 ignored `.local/rpf-52-rev2/`，未换用其他手段清理。失败预检创建的 task-owned venv 也保留但不参与正式运行。task root 当前共 530 个文件、74,475,731 bytes，含 JAR 副本与隔离 Runtime 回归副本，不进入 Git。
- 交付状态仅代表本 rev-2 分支工程结果。它不等于 EVIDENCE_ACCEPTED 或 STAGE_ADVANCED；真实 SDK/Tool/业务 Effect/Evidence 闭环仍未证明，WorkSwarm 与真实模型自主决策仍为 `NOT_PROVEN`。
