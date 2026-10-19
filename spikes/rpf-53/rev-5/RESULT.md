# RPF-53 rev-5｜TASK_RESULT

**Status = PARTIAL**

## 1. 任务身份与结果

- Plan：RPF-53 rev-5，`真实 Provider 配置参数合同可见性与 task-owned JAR 补验收`。
- 仓库：RunProof（仓库根目录）；执行前 HEAD/精确 Parent：`247d9c287e02b70f571d76131cbb8f8d24d65aaf`。
- 分支：`codex/rpf-53-rev5-live-config-contract-jar-closeout`。
- 唯一 `main` 基线：`bda0cd49e50e3181f604324e94877a24b9885334`。
- 本轮最后源码身份与 SDK Fixture 身份一致；无源文件在 Fixture PASS 后修改。
- `docs/reviews/` 的既有 `?? docs/reviews/` 状态保持；未读取、枚举、编辑、暂存或提交其内容。
- 唯一真实 Trial 的 Run ID：`rpf53-live-5c4d76a12e014a4c`。配置服务使用 loopback 与进程内 H2；Trial 已消费，不重跑。

实际业务 Oracle 为 `CONTRACT_SATISFIED_IN_RUN`：从初始 `ABSENT` 出发，Target Agent 经真实 DeepSeek Tool Calls 完成 create v1、update v2，独立 current/history/list 读回最终 `rpf53-v2/version 2/history [2,1]`。但本轮 `verify_bytes` 自检以 `KeyError` 失败，`config-live-evidence.json` 未生成；因此整体状态为 `PARTIAL`，不是已签发的 Live Witness。

## 2. A01–A08 验收

| Gate | 状态 | 证据与限制 |
|---|---|---|
| A01 来源、白名单、历史保护 | PASS | 执行前核验精确 parent、分支、origin、`main` 和固定来源；tracked 改动限于 Plan 白名单。受保护目录状态未变。 |
| A02 Agent 可见合同 + Host Guard | PASS | 冻结字面值、工具说明与 Host 守卫一致；定向 37 项通过，包含错误参数、额外字段、类型、顺序、重复、unknown、拒绝前零 POST 与 JAR 路径正负控。工具参数 Schema 和 Host 精确值检查未放宽。 |
| A03 新源码真实 SDK Fixture | PASS | Attempt 1 的 63 项检查全通过：4 completions、3 SDK-origin Tool Calls、3 个唯一 Tool Returns、回注位置 `[2,3,4]`；Popen/Host-ready/child-report PID 相同；0 Provider HTTPS、0 业务 HTTP、0 Java；退出与清理通过。 |
| A04 真正 Live Provider | PASS | 单一真实 Trial；4 个 Provider 请求、3 个实际 SDK Tool Call/Callback、0 自动重试；Tool 参数被 Host 接受，预算和 usage 可核验。Agent 可见性守卫在每次请求前执行；安全摘要未单独保存每次 message hash，这是留存证据缺口。 |
| A05 独立 HTTP Effect + JAR | PASS | task-owned JAR 的复制身份、`Popen` 与实际 JVM `-jar` 路径均匹配；健康检查、两次 POST、最终三类读回和 Oracle 均通过。 |
| A06 新 Live Witness | FAIL | 证书写入前的独立 verifier 自检失败，`detail_code=KeyError`；证书不存在，correct/missing/wrong anchor 与四类 tamper controls 未运行。未推测触发 KeyError 的具体字段。 |
| A07 回归、预算与安全 | PASS | 隔离完整 Runtime 291 项通过、2 项因 Docker 不可用而跳过；Reviewed Artifacts、Public Docs、7 个历史外部锚及 `git diff --check` 通过。预算、密钥边界、进程/端口与外连检查通过。 |
| A08 TASK_RESULT / Git | PASS | 实现与验收材料的聚焦提交 `07aed9303b78e4c5b7df5ba385fe491c81b90c49` 已普通 push；fresh `ls-remote` 与该分支 SHA 一致，`main` 仍为 `bda0cd49e50e3181f604324e94877a24b9885334`。未创建 PR、合并、发布或部署。 |

## 3. 冻结合同、源码与 JAR 身份

模型可见任务和工具帮助明确要求：先 `inspect_config`；若初始状态为 `ABSENT`，按 `create_config_v1({"value":"rpf53-v1"})` 创建，再按 `update_config_v2({"expected_version":1,"value":"rpf53-v2"})` 更新；遇到 `UNKNOWN` 或 `REJECTED` 停止写操作。固定业务合同、版本、顺序、Oracle 和 POST 上限未变。Host 仍在写请求之前做精确参数及顺序断言。

| 本轮执行源 | SHA-256 |
|---|---|
| `runtime/runproof_runtime/effectwitness/config_live_contracts.py` | `deb51ec013c70e0c22fdca066bf0054302763aa56d11037c66caff3da5da39d9` |
| `runtime/runproof_runtime/effectwitness/config_live_external.py` | `0d977965f72d2a8ade8d02d0ce4963742cb8952976f012459c58423aefe9bdfe` |
| `runtime/runproof_runtime/effectwitness/config_live_runtime.py` | `97cd8fea12ab3f8594d0f6218af882afe490c8ea293435680ce82d00a399339c` |
| `runtime/runproof_runtime/effectwitness/config_live_verify.py` | `07939da055b6600d2ab270fb22393b9bbdf63842e91c85345d6fa41f36932569` |
| `runtime/tests/test_effectwitness_config_live.py` | `e081a94ededb182002c971f60c7e9f49f8dbb3f5b519ebd6918750655ae31869` |
| `spikes/rpf-53/probe.py` | `19a09b34297e354c4577af17ea744cb9c93d0663248caf68b0b6e2900896332f` |

六文件 aggregate runtime source SHA-256：`574b595c095cb172b24e6f57ba9bd5d6069be96d758704f2b271a58c0edb8a01`。Tool Schema SHA-256：`58bcb979a92486b7371153a5d3d098bcf0f2cae30f78004e09af5ff901bf3174`。

config-center 固定来源为 commit `0258b9cef02ea74a40989d035c79256c776409c0`，110 个源文件 / 393,800 bytes，manifest SHA-256 `33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`。本轮 task-owned JAR 仅以相对路径记录：`.local/rpf-53-rev5/jar/config-center-server-1.0.0.jar`；来源与副本均为 66,981,576 bytes、SHA-256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。路径位于 task root、无链接组件、`Popen -jar` 和 JVM 实际命令行检查均为 `true`。外部 JAR 的绝对路径没有写入本文件。

Pinned Python 为 3.12.13，Pydantic AI 为 2.57.0，OpenAI SDK 为 3.35.1；SDK RECORD mismatch 均为 0。JDK 为 17.0.12。

## 4. 真实 SDK Fixture-only Attempt 1

- 命令：`python -B spikes/rpf-53/probe.py --diagnostic`；exit 0，`PASS`。
- Run ID：`rpf53-diag-f30769cc5d654146`；result SHA-256：`077437552114c1444db34cd155aa79150620938d1c560b46960513590d2465b3`；marker SHA-256：`a98d7f8640600b1d90edb250155276579da195116e78497737c1e2488bd96d9c`。
- Fixture source SHA 与本报告第 3 节六文件 aggregate SHA 相同。Result 中 63/63 个 acceptance checks 为 `true`。
- 真实 SDK 子进程 Popen/Host-ready/report PID 均为 `33480`，exit 0；4 completions、3 calls、3 unique returns，位置 `[2,3,4]`；0 Provider HTTPS、0 业务 HTTP、0 Java。Fixture Host、loopback 端口与子进程均关闭，外连为空。
- SDK 摘要：`sdk-fixture-preflight.json`，10,553 bytes，SHA-256 `66d4f1defd0607b29a62301927cc0a5763a575ac8844f66a3583ae4b55b58054`。详细脱敏字段见该文件；Fixture usage 不代表 Provider usage 或费用。

## 5. 唯一真实 Provider + config-center Trial

### 5.1 Provider 请求和 Tool lineage

官方文档在 2026-10-19 核验：`deepseek-flash` 指向 DeepSeek-V4.1-Flash-1017，OpenAI-compatible base URL 为 `https://api.deepseek.com`，Chat Completions 路径为 `/chat/completions`，支持 Tool Calls。Peak cache-miss input/output 价格为 `$0.30/$1.20` 每百万 tokens；预算估算使用 Plan 固定的 15 CNY/USD 上界换算，不是实时汇率报价。参见 [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)、[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [2026-10-17 model update](https://api-docs.deepseek.com/news/news261017/)。

| Attempt | Provider response ID | Tool Call | 本次请求回注的旧 Tool Return | Prompt / completion / total tokens |
|---:|---|---|---|---:|
| 1 | `769b3073-35bd-43ac-9eeb-b055c161a0d4` | `inspect_config` — `call_00_XYBpj9OZRAjau3JkGe3j4483` | 无 | 648 / 29 / 677 |
| 2 | `e829d711-8340-4d34-88ac-5e0ef2588c3c` | `create_config_v1` — `call_00_4lq4qiZjDdke5wc1EHtV5104` | `call_00_XYBpj9OZRAjau3JkGe3j4483` | 695 / 55 / 750 |
| 3 | `57f4cdb9-ca3d-4053-8929-051e77a662c9` | `update_config_v2` — `call_00_oa72fTE79ofbMd91gVXe1807` | 前两次 Tool Call | 780 / 74 / 854 |
| 4 | `f3559fba-ac77-4157-bd2b-d367415b42f2` | 无 | 三次 Tool Call | 884 / 92 / 976 |

SDK 汇总为 4 requests、3 Tool Calls、3 Tool Callbacks；Host `tool_rejections=[]`，自动重试为 0。三个 Tool Call 的 Return 分别在后续 Provider 请求 2、3、4 回注。摘要中未保存模型自由文本、私有推理或 API key。

### 5.2 HTTP Effect 与独立读回

| 顺序 | 操作 | HTTP / 业务 code | 观察 |
|---:|---|---|---|
| 1 | initial current | GET 404 / 4041 | 不存在 |
| 2 | initial history | GET 200 / 0 | 空历史 |
| 3 | Agent inspect | GET 404 / 4041 | 不存在 |
| 4 | create v1 | POST 200 / 0 | version 1 |
| 5 | update v2 | POST 200 / 0 | version 2 |
| 6 | final current | GET 200 / 0 | `rpf53-v2/version 2` |
| 7 | final history | GET 200 / 0 | versions `[2,1]` |
| 8 | final list | GET 200 / 0 | 当前仅 version 2 |

总计 8 个业务 HTTP 请求、2 个 POST、6 个业务 GET；另有 1 个 health GET，返回 `200/UP`。Oracle gaps/violations 均为空，`business_violation=NOT_PROVEN`、`agent_failure=NOT_PROVEN`。

### 5.3 预算、JAR 与清理

- Provider 报告 usage：3,007 input + 250 output = 3,257 tokens；4 HTTPS attempts；usage known；0 automatic retries；1 Trial。
- 按固定 peak rate 与 15 CNY/USD 假设计算的费用上界为 `¥0.0180315`，不代表账户实际扣款。低于 12,000 tokens、6 requests、8 tools、12 HTTP、2 POST、3 health GET、1,200 seconds 与 `¥1.00` 上限。
- JVM PID/listener PID 均为 `9004`；SDK Popen/Host-ready/report PID 均为 `16368`。SDK exit 0；Java 已停止、listener 已关闭、外连为空。Java 受控停止记录 exit code `1`，未隐藏。Host 已关闭，cleanup 为 true。
- Java 实际 `-jar` 命令行摘要为 `1e3169513c2713714452fc4b330fb47bf89a2f32ef6370cf33ec2b7ee3bedb75`；task-owned 副本 SHA/size 与第 3 节相同。Java redacted log 为 5,605 bytes，redactions=0，overflow=false。
- Live summary：14,002 bytes，SHA-256 `b330cd4bcb5bd3b67cda0ca2e734ae5645692a78c56a601f4fb5a86c96ba5989`。该文件记录 `status=PARTIAL` 和 Evidence 自检错误。

### 5.4 前置检查漂移与 Witness 自检失败

首次 `--run-scenario` 在 `_live_preflight` 返回 `PREFLIGHT_SOURCE_DRIFT`，发生于 Java 启动、Live marker、Provider ledger 和 Provider 请求之前；当时 scenario 目录为空。原因是 Fixture 成功后新增的允许输出文件改变了 `git status` 路径列表，而预检比较将该可变列表按字节身份冻结。为保留 Fixture 证据且不改动冻结源码，文件原字节暂存到 task-owned ignored preflight 目录后重新执行门控；前后 SHA-256 相同，Trial 后已恢复公开副本。该状态列表比较缺陷仍待后续 Plan 修复。

真实业务 Oracle 完成后，Probe 在 `verify_bytes` 自检处捕获 `LIVE_EVIDENCE_SELF_CHECK_FAILED`，`detail_code=KeyError`。没有足够留存信息确认触发 KeyError 的具体字段，本报告不猜测。失败发生在 Evidence 文件写入之前，因此：

- `config-live-evidence.json` 不存在；本轮没有有效 Live Evidence。
- correct/missing/wrong external anchor 的独立子进程验证与四类 tamper controls 均未运行。
- `A06=FAIL`，不因真实业务 Effect 已成功而降级该门槛。
- 本 Plan 的唯一 Trial 已用完；不能用第二次 Provider 调用修补该证书。

## 6. 回归与安全验收

| 命令 / 工作 | 结果 |
|---|---|
| `python -B -m unittest runtime.tests.test_effectwitness_config_live -v` | exit 0；37 tests OK |
| Runtime 隔离快照 `python -B -m unittest discover -s runtime/tests -t . -p 'test_*.py' -v` | exit 0；291 tests，2 skipped，0 failures/errors；21.595 s |
| `python -B runtime/verify-reviewed-artifacts.py` | exit 0；历史与当前 reviewed artifacts PASS |
| `python -B ci/verify-public-docs.py` | exit 0；`PUBLIC_DOCS_PASS files=18 pairs=7` |
| `git diff --check` | exit 0 |

Runtime 快照来自精确 parent 的 `runtime/` 与 `spikes/`，只覆盖六个获准源文件；不包含 `docs/`，因此未读取 `docs/reviews/`。Manifest SHA-256 `966a96f024054d5df195e1c893787ddad6436632907b0612fe0a0879a0889f37`。全量日志保存在 ignored task root 的 `tests/runtime-tests-attempt-01.log`。两个跳过组为 `test_docker_integration` 与 `test_rpf05_runtime`，原因均为 `Docker provider unavailable: RuntimeFailure`。

七个未修改历史样本以各自外部 SHA 锚运行，全部 exit 0：

| 历史样本 | 外部 SHA-256 | 状态 |
|---|---|---|
| RPF-43 Witness | `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e` | `VERIFIED_ANCHORED` |
| RPF-44 Ops Witness | `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873` | `VERIFIED_ANCHORED` |
| RPF-48 Target summary | `c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2` | `CONTENT_VERIFIED_ANCHORED` |
| RPF-49 Recovery summary | `04ac629bbfb54a4b85eddf902bbf765db7c57ea0c509e0b539280858c7d4bc9b` | `CONTENT_VERIFIED_ANCHORED` |
| RPF-50 violation Witness | `b8f288db5dd76a142bbfb69a04d15ce9206d2cd9dbe28ef6effdb59382f5ef4a` | `VERIFIED_ANCHORED` |
| RPF-51 rev-4 HTTP Witness | `c569bd62a6691c84e8995359578fc4ff34f0ea417158a0c0893309c029df363d` | `VERIFIED_ANCHORED` |
| RPF-52 rev-3 config-target Evidence | `2bbc002e5a83dabc4aa9b9ddfea733532ef8b29f789181a19debb7ed9437eb27` | `VERIFIED_ANCHORED` |

安全观察：Provider key 仅由父 Host 读取；SDK child 的 provider/business key 均为 absent，guard denials 为空；Fixture 与 Live SDK 外连列表为空；Java 外连列表为空，loopback listener 已关闭。所有 Provider 文本/私有推理均未写入普通 summary。Python audit hook 属 defense-in-depth，不是 OS sandbox。

## 7. 交付与未完成项

Tracked 文件仅限六个获准源码/测试文件与本 rev-5 的 README、TASK_RESULT、Live summary、SDK Fixture summary。`.local/rpf-53-rev5/**`、task-owned JAR、Runtime 快照和日志保持 ignored。未创建 Evidence；未修改 Project State、历史 Plan、workflow、Java 外部仓库或 `docs/reviews/`。

当前交付行为：A01–A05、A07 通过；A06 失败；总体 `PARTIAL`。下一次若继续，需要新 Plan 修复 Evidence self-check 的 `KeyError` 和 preflight 状态列表比较，再完成新的 Fixture/Live 授权门槛；本文件不授权重跑 Provider。

**A08 Git 交付：PASS。TASK_RESULT 本次闭环更新会随文档补充提交一并推送。**
