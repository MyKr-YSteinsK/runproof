# RPF-51 TASK_RESULT

- **Plan ID / Revision:** RPF-51 / rev-2
- **Status:** `PARTIAL`
- **日期：** 2026-10-18
- **仓库 / 分支：** `MyKr-YSteinsK/runproof` / `codex/rpf-51-rev2-http-effect-recovery`
- **唯一正式结果：** 本文件
- **前序结果：** rev-1 仍为 `PARTIAL`；原 `spikes/rpf-51/README.md`、`RESULT.md` 与受保护实现未修改。

## A-01～A-08 验收

| Gate | 状态 | 证据与边界 |
|---|---|---|
| A-01 身份与历史隔离 | PASS | 本地父提交 `6753ac17ee079bf94562bfd9879bfd3c11ff74c0`、指定新分支与 origin 身份吻合；远端 main 在任务开始及 push 前均为 `bda0cd49e50e3181f604324e94877a24b9885334`。rev-1 跟踪文件 diff 为空；旧 `.local/rpf-51/` 只读复制了 Plan 点名的 110 个公开源文件、manifest 和精确 JAR，未枚举或清理旧目录。`docs/reviews/` 只在 Git 状态显示既有 `?? docs/reviews/`，内容未读取、列举或触及。 |
| A-02 单点配置修复与测试 | PASS | Java argv 在同一列表属性源传入 `key/app/env`；key 只传字面量 `${CONFIG_CENTER_API_KEY}`，明文随机凭据只注入子进程环境。实际 Spring 应用启动日志完成 `Tomcat started` 与 `ConfigCenterServerApplication started`，未出现原 rev-1 的 `apiKeys[0].key` 绑定错误。16 项定向测试通过。 |
| A-03 真实服务 readiness | PASS | 真实来源 JAR、Java `17.0.12`、`local`/内存 H2 已核验。runner 自身错误返回 `OWNED_LOOPBACK_SERVICE_NOT_READY`；其退出后只读 OS 复核仍发现任务 JAR 对应 PID `31372`，且 `127.0.0.1:7654` 为该 PID 的 `LISTENING`。结合 Spring 启动日志，服务实际已 ready；runner 的 readiness 检查未认可该监听器，因此没有进入请求阶段。runner 侧的外连审计未运行，见诊断边界。 |
| A-04 真实 HTTP Effect | NOT_RUN | 0 次业务 HTTP 请求；未发送初始 GET、未授权 POST、v1/v2/stale 写入或最终 GET/history/list。没有 Effect Oracle 结论，也没有业务状态变更。唯一启动尝试已消耗；按 Plan 未重启。 |
| A-05 离线 Witness | NOT_RUN | 未生成 `config-http-witness.json`，未执行真实文件的 correct/missing/wrong anchor CLI 检查。定向单测覆盖 `verify_bytes` 的有锚、缺锚、错锚及重算摘要负控，但不替代真实 Witness 验收。 |
| A-06 安全与负控 | PASS | 定向测试覆盖 loopback/方法/path 限制、redirect 禁止跟随、timeout 不重试、伪成功/错误版本/历史和来源错配、digest 与外部锚负控。启动参数与进程记录不含实际 API key；服务日志扫描到 0 个 `CONFIG_CENTER_API_KEY` 名称、0 个 `${CONFIG_CENTER_API_KEY}` 占位文本及 0 个 43 字符 URL-safe token 形态值。真实 HTTP 授权负控因 A-04 未运行。 |
| A-07 回归、费用与新资源收口 | PASS | 全 Runtime 216 项通过、2 项 Docker provider 不可用跳过；RPF-43/44/48/49/50 原锚定 verifier 均 exit 0；`runtime/verify-reviewed-artifacts.py` 与 `ci/verify-public-docs.py` 均 exit 0。rev-2 业务 HTTP / Provider / tokens / cost 均为 0。PID `31372` 被精确识别后停止，复核无该任务 Java 进程、无端口 listener、端口关闭。为保留已消费 marker 与故障证据，rev-2 ignored root 留存 117 个文件、67,409,148 bytes；没有扩散到 Git。另有 3 个 `py_compile` 生成的 ignored `.pyc` 文件共 98,993 bytes；精确删除命令被本机执行策略拒绝，未尝试替代删除方式。 |
| A-08 Git 与完整结果 | FAIL | 本文件、README、诊断、实现与测试可按白名单提交并 push；但真实 HTTP Effect 与真实 Witness 缺失，故未满足本 Gate 完整交付条件。无 PR、merge、tag、release、deploy 或竞赛门户提交。 |

整体保持 `PARTIAL`：配置绑定修复已由真实 Spring 启动支持，真实业务 Effect 与 Witness 仍未验收。runner 的 false-negative readiness 检查及进程未自动退出是本轮实际发现的 harness 问题；没有足够证据在本 Plan 的 one-shot 预算内安全修复后重跑。

## 来源、身份与冻结合同

- RunProof parent：`6753ac17ee079bf94562bfd9879bfd3c11ff74c0`；分支：`codex/rpf-51-rev2-http-effect-recovery`。
- config-center 原 checkout 只读观察为 commit `0258b9cef02ea74a40989d035c79256c776409c0`，工作区干净；没有写入相邻仓库。
- 来源副本来自已验证的 rev-1 本地公开源码/JAR，非 rev-2 重建或外网下载：110 files / 393,800 bytes；manifest SHA-256 `33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`。
- JAR：66,981,576 bytes；SHA-256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。Maven 未运行，未下载依赖。
- 运行时 source SHA-256（preflight 与任务结束时当前源码一致）：`15f47f13cd18786b0d5049a0bda5f9611dd28586df7ffc3fa031c526cfff4785`。
- Execution / Effect / Experiment SHA-256：`3ff4ff852ba2b8928bb17f8842d598978841ee37718876cb37a348792c3a8067` / `703ac9f8d7424a174c18b7539688bea97384c521c6d118f77d8c585253fcc232` / `90f734354a23c2560db3e735b8cab4159910940e4e21732f2bf20956bc7064d7`。
- run id：`rpf51-98c991453820446781dce7b68a12ef66`；app/env：`rpf51-app-f187bd4267bd` / `rpf51-env-a15276b4062c`；config key：`rpf51.value.7eeebfb863ef4014baa583d2087076db`；port：`7654`。这些是本地实验 namespace，不是 API credential。
- 运行预算冻结为 1 个业务 Scenario、12 次 HTTP、0 Provider / 0 tokens / ¥0；实际业务请求为 0。
- 原 rev-1 RESULT 记录 `.local/rpf-51/` 为 2,248 个文件、182,005,301 bytes。本轮未重新枚举该旧目录，未修改其 marker、失败日志或来源副本。

安全的启动参数模板：

```text
java -Djava.io.tmpdir=<task-owned-tmp> -jar <task-owned>/config-center-server-1.0.0.jar --spring.profiles.active=local --server.address=127.0.0.1 --server.port=7654 --security.api-keys[0].key=${CONFIG_CENTER_API_KEY} --security.api-keys[0].app=<synthetic> --security.api-keys[0].env=<synthetic>
```

本次随机 API credential 只由 Python 进程环境注入 JVM；未记录原值、摘要或进程环境内容。

## 唯一真实启动尝试

- 命令：`py -3.14 -B spikes/rpf-51/probe.py --run`；started 时间 `2026-10-18T10:08:31.564Z`，runner failure marker 为 `OWNED_LOOPBACK_SERVICE_NOT_READY`，Codex 执行结果 exit `1`。
- task-owned JAR 日志显示 Java `17.0.12`，`Tomcat started on port 7654`，随后 `ConfigCenterServerApplication started`。runner 在 readiness 等待后仍判失败，并返回前没有完成预期子进程退出。
- runner 返回后，CIM 查询确认唯一匹配任务 JAR 的 Java PID 为 `31372`；netstat 实际观察到 `127.0.0.1:7654 LISTENING PID 31372`。为停止这一精确任务 PID，执行 `Stop-Process -Id 31372 -Force`；其后任务 Java 进程数为 0、listener 数为 0、`_port_closed(7654)=true`。
- API adapter 位于 readiness 成功分支之后，因此业务 HTTP 请求为 0；未执行 `external_connections` runner 审计。该次现象证明应用启动配置可绑定，但没有证明 HTTP 业务合同。
- startup/failure 的去敏观察见 [startup-diagnostic.json](startup-diagnostic.json)。原始本机服务日志只留在 ignored `.local/rpf-51-rev2/`，没有提交。

## 回归、清理与未完成项

- `py -3.14 -B -m unittest runtime.tests.test_effectwitness_config_http -v`：16 tests，PASS。
- `py -3.14 -B -m unittest discover -s runtime/tests -p 'test_*.py'`：216 tests，PASS；2 skipped（Docker provider unavailable）。
- RPF-43 `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e`、RPF-44 `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873`、RPF-48 `c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2`、RPF-49 `04ac629bbfb54a4b85eddf902bbf765db7c57ea0c509e0b539280858c7d4bc9b`、RPF-50 `b8f288db5dd76a142bbfb69a04d15ce9206d2cd9dbe28ef6effdb59382f5ef4a`：各自 anchored verifier 均 exit 0。
- `py -3.14 -B runtime/verify-reviewed-artifacts.py`：exit 0。`py -3.14 -B ci/verify-public-docs.py`：exit 0，18 files / 7 pairs。`git diff --check`：exit 0。
- rev-2 task root 保留 preflight、started、failure marker、来源副本、JAR、临时回归输出及本机日志；保留 one-shot 证据，未删除/重置。rev-1 旧目录应继续单独保留。
- 被策略阻止清理的 3 个 ignored `.pyc` 精确路径与大小：`spikes/rpf-51/__pycache__/probe.cpython-314.pyc` (45,776 B)、`runtime/runproof_runtime/effectwitness/__pycache__/config_http_contracts.cpython-314.pyc` (21,830 B)、`runtime/tests/__pycache__/test_effectwitness_config_http.cpython-314.pyc` (31,387 B)。删除命令在执行前被拒绝；未改用其他 shell/语言/删除方法。
- 唯一阻止本 Plan 完整完成的是：runner readiness 识别失败后未进入真实 HTTP Scenario；one-shot 服务启动已消费，不能重启补跑。真实 HTTP Effect、Witness CLI exit 0/2/3 和 runner 外连审计均保持 `NOT_RUN`。下一步需由 Main 另行审查新的 harness readiness/owned-process lifecycle 方案与新鲜 Scenario 授权。

## Git 交付

- 修改范围限于 `spikes/rpf-51/probe.py`、`runtime/runproof_runtime/effectwitness/config_http_contracts.py`、`runtime/tests/test_effectwitness_config_http.py` 和 `spikes/rpf-51/rev-2/{README.md,RESULT.md,startup-diagnostic.json}`；没有生成真实 Witness，没有改旧 rev-1 文件、Project State、CI 或 config-center 仓库。
- Push 前 origin `main` 为 `bda0cd49e50e3181f604324e94877a24b9885334`，rev-1 feature branch 为 `6753ac17ee079bf94562bfd9879bfd3c11ff74c0`，rev-2 远端分支不存在。
- focused commit / ordinary push / push 后独立 `ls-remote` 核验均按本 Plan 完成；本文件不自指回填所在 commit SHA，最终 SHA 与远端 ref 核验值由最终对话回执记录。
- 没有 PR、merge main、release、tag、deploy、真实生产操作或竞赛门户提交。
