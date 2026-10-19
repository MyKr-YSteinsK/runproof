# RPF-53 rev-2 TASK_RESULT

**Status: Partial**
**Plan:** RPF-53 rev-2 — 可信 SDK 只读边界修复与真实 Provider 跨域闭环补验收

## 结论

本轮修复并测试了可信 SDK 只读边界；两次获准的 SDK Fixture 诊断均保留为失败记录，A-03 未通过。第二次诊断完成 3 次 SDK-origin Tool Call 和 3 次结果回注，之后子进程以 `TypeError` 退出。检查发现报告代码将 Pydantic AI 的 `result.usage` 属性误作函数调用，现已修正；该最终改动没有再次运行 SDK 诊断。两次额度已耗尽，未执行第三次。

因此 A-04 真实 Provider、A-05 Java/H2 业务 Effect、A-06 独立 Live Evidence 均为 `NOT_RUN`。本轮 Provider HTTPS 请求、业务 HTTP 请求和 Java 进程数均为 0；没有 Live Evidence，不裁定业务成功、失败或违规。

## 基线与来源身份

- 仓库基线：`a8f2369b89d1c1a9e3e46438c2f4f5c35fcc96d7`；工作分支：`codex/rpf-53-rev2-sdk-import-guard-live-recovery`。预检时 main 为 `bda0cd49e50e3181f604324e94877a24b9885334`；目标 feature 分支当时不存在。
- 最终 RPF-53 Runtime source SHA-256：`be5bf311f8280fac835af7b434b11145cec4bf1722f02b3010f95e14239f3d64`。attempt-01 / attempt-02 实际运行的 source SHA 分别为 `1d15146f47074700af5c18262d3fc4a9e7d057147f805b85fcfc7ccdbe2bcf67` / `d2ac0e20eb95ebb664be18134d4ebd6fc9c361f3f2b5d59eb3f02191ab4a556d`；最终 usage 属性修正晚于 attempt-02，未被 SDK 端到端运行验证。
- 只读 config-center 来源：commit `0258b9cef02ea74a40989d035c79256c776409c0`，manifest SHA-256 `33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`（110 files）；JAR SHA-256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。
- 固定 SDK：Python `3.12.13`、Pydantic AI `2.57.0`、OpenAI `3.35.1`。发行 RECORD 哈希不匹配均为 0。SDK root binding SHA-256 `d4c8fbc3564e7f3357af9ab8a08b1a1cfa04cc7d971895e76e2607c791f2428a`；Python runtime mapping SHA-256 `dec9f9d7796996df26044bc49811e758d2cc3731f11ef6fb0f6872ce88719b4e`。Java 身份只读检查为 JDK `17.0.12`；没有启动 Java 进程。

## A-01～A-08 验收

| Gate | 状态 | 事实 |
|---|---|---|
| A-01 身份与历史隔离 | PASS | 从指定 parent 创建指定新分支；保留 rev-1 资产；仅六个白名单源码文件有修改；`docs/reviews/` 始终未进入、枚举或读取。预检未发现 feature 分支远端目标。 |
| A-02 可信 SDK 只读守卫 | PASS | SDK root 由固定父进程核验并绑定 SHA；拒读项经同一固定解释器复核为配置中的精确 `python312.zip` runtime archive。只允许该精确文件项，不允许其父目录。SDK/runtime 读写、任务 scratch、相似 basename、用户目录、junction/symlink、进程、DNS 与 socket denylist 定向测试通过；父子映射哈希相同。 |
| A-03 真实 SDK Fixture | FAIL | attempt-01 因 `python312.zip` 读拒绝及 Host `SDK_TOOL_SCHEMA_SHAPE` 失败，0 工具调用。attempt-02 无 guard denial、Host rejection 或外连；完成 3 个工具调用和 3 个返回回注，但最终 SDK 报告为 `TypeError`，且 4 次 completion 数未安全持久化，故不把 A-03 记为 PASS。两次子进程、Host、监听线程和端口均已关闭。 |
| A-04 真实 Provider Target Agent | NOT_RUN | A-03 未通过，不进入付费 Scenario。预检仅记录 key 存在；Provider 请求数 0。 |
| A-05 独立 Java HTTP Effect | NOT_RUN | Java 进程、业务 HTTP 请求均为 0。 |
| A-06 独立 Live Evidence | NOT_RUN | `config-live-evidence.json` 未创建；没有可验证的 Live Witness。 |
| A-07 回归与资源 | PARTIAL | 定向测试 23/23 通过。隔离镜像全 Runtime 套件 277 项：2 个 loopback 用例首次报 Windows `10053`、2 项 Docker 测试因 Docker provider 不可用而跳过；两项 loopback 用例分别单测复跑通过，但不把首次全量套件记为 PASS。Reviewed Artifacts、Public Docs、七个历史锚验证、AST 和 `git diff --check` 通过。 |
| A-08 Git 与 TASK_RESULT | PASS | 完成 focused commit、对指定 feature branch 的普通 push，并通过新鲜远端 SHA 与 main 校验；无 PR、merge、release 或 deploy。最终 commit/remote SHA 在本次任务聊天回执提供，按 Plan 不在本文件自引用。 |

## 两次 SDK 诊断

| Attempt | Run ID | 运行源码 SHA | 结果 |
|---|---|---|---|
| 01 | `rpf53-diag-cef9c6b4dea54733` | `1d15146f47074700af5c18262d3fc4a9e7d057147f805b85fcfc7ccdbe2bcf67` | `ModelHTTPError`，`sdk_run`；拒读类别 `OUTSIDE_ALLOWED`，安全 basename `python312.zip`；Host 拒绝码 `SDK_TOOL_SCHEMA_SHAPE`。Provider/Java/业务 HTTP 均为 0。 |
| 02 | `rpf53-diag-cc1eb8eef8ff4d5c` | `d2ac0e20eb95ebb664be18134d4ebd6fc9c361f3f2b5d59eb3f02191ab4a556d` | `TypeError`，`sdk_run`；3 次 SDK 工具调用、3 次返回回注、3 次合成 backend 调用；guard denial、Host rejection、Provider/Java/业务 HTTP 均为 0。completion 总数没有写入安全结果，不能补推为已验证计数。 |

两次诊断详情和清理字段见 [sdk-read-guard-diagnostic.json](sdk-read-guard-diagnostic.json)。诊断额度已用尽；本轮不生成第三个 marker、不执行真实 Scenario，也不创建成功 Evidence。SDK 错误后的 `result.usage` 属性修正仅通过定向测试/静态检查，等待新的 Plan 批准下一次真实 SDK 诊断。

## 验证命令

- `python -B -m unittest runtime.tests.test_effectwitness_config_live -v` — 23 tests passed。
- `python -B -m unittest discover -s runtime/tests -t . -p 'test_*.py' -v` — 在 `.local/rpf-53-rev2/tests/full-runtime-mirror` 隔离镜像运行；277 tests，2 errors、2 skipped；两项错误用例单独复跑均通过，完整套件状态保持 PARTIAL。
- `python -B runtime/verify-reviewed-artifacts.py` — PASS。
- `python -B ci/verify-public-docs.py` — PASS。
- 离线历史锚验证：RPF-43、RPF-44、RPF-48、RPF-49、RPF-50、RPF-51 rev-4、RPF-52 rev-3 — 全部 PASS。
- AST 解析 6 个白名单源码文件通过；`git diff --check` 通过。

## 信任边界

`issuer_authenticity=NOT_ESTABLISHED`、`database_independent_authority=NOT_ESTABLISHED`、`independent_reproduction=NOT_TESTED`。受控 Fixture 诊断不证明真实 Provider 的模型行为；没有 Live Evidence，不得宣称真实业务 Effect、攻击成功或违规已确认。
