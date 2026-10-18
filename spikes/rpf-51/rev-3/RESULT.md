# TASK_RESULT｜RPF-51 / rev-3

- **Plan ID / Revision:** `RPF-51 / rev-3`
- **Status:** `PARTIAL`
- **Scope:** 就绪探针 PID 假阴性取证与修复；一次只读真实 Java 诊断。诊断失败后按停止条件不运行正式业务 Scenario。
- **历史状态：** RPF-51 rev-1、rev-2 仍为 `PARTIAL`；本轮未重跑、改写或迁移其结果、Witness、marker、日志或旧运行目录。只从 rev-2 已验证的 task-local 副本读取来源 manifest、源码和 JAR 并复制到新 rev-3 目录。

## A-01～A-08 验收

| Gate | 状态 | 事实 |
|---|---|---|
| A-01 身份、历史与权限 | **PASS** | 根目录 `D:\CS\runproof`；基线/精确 parent `68ac08de12048856fe38aa7e8548ad5bb3516a9b`；分支 `codex/rpf-51-rev3-readiness-http-effect`；origin `https://github.com/MyKr-YSteinsK/runproof.git`。`main` 在执行前后观察为 `bda0cd49e50e3181f604324e94877a24b9885334`。rev-2 远端分支仍指向 parent；rev-3 推送前不存在。`docs/reviews/` 仅在 Git 状态中显示原有 `?? docs/reviews/`，未进入或读取。tracked 改动限定于本 Plan 白名单。 |
| A-02 可靠 readiness 修复 | **PASS** | 纯函数 netstat 解析、loopback/PID/重复监听/不完整输出负控、TCP 成功但 PID 不匹配时有界退避、健康响应与二次身份核对、进程退出及安全清理测试通过。真实诊断定位出 Oracle `javapath` wrapper 启动 JDK 子进程造成的 PID 不匹配；`_java_info()` 已改为读取 launcher 的 `java.home`，直接选择并校验该 JDK 可执行文件。新实现通过测试，但未再启动服务。 |
| A-03 独立只读真实 Java 诊断 | **FAIL** | 唯一诊断启动使用 Java `17.0.12`、受信 JAR、`local`/内存 H2、`127.0.0.1:2018`。探针 `Popen` PID `29916` 是 Oracle `javapath` launcher；Windows CIM/netstat 同时观察到它启动的 JDK 子进程 PID `3856` 持有该 loopback listener。PID 与 Popen PID 不匹配，探针 fail closed，健康 GET `0`、业务 HTTP/POST `0`。诊断 171 轮：159 次 `LISTENER_PID_MISMATCH`、11 次 `TCP_CONNECT_FAILED`、最后 `PROCESS_EXITED`；运行 178.723 秒。只结束身份确认的 PID `3856` 与 `29916`；runner 记录 `process_stopped=true`、`port_closed=true`、`external_connections=[]`。没有联合 PID+HTTP 健康证明，不能 PASS。 |
| A-04 正式外部 HTTP Effect | **NOT_RUN** | A-03 失败，停止条件禁止正式服务启动。`.local/rpf-51-rev3/scenario/started.json` 与 scenario result 均不存在；未发生业务写入。 |
| A-05 离线真实 Witness | **NOT_RUN** | 没有正式业务 HTTP 观察，不生成 `config-http-witness.json`，也不运行真实 Witness 锚验证。`issuer_authenticity=NOT_ESTABLISHED`；同服务信任域仍不构成数据库独立证明或发行者认证。 |
| A-06 安全与负控 | **PASS** | 诊断 argv 使用 `${CONFIG_CENTER_API_KEY}` 占位符；结果记录 `api_key_found_in_log=false`。没有业务请求、Provider/LLM 请求、tokens 或费用；探针只连接 loopback，netstat 外部连接摘要为空。PID 竞争不发送 health GET，健康路径固定 `/actuator/health`，健康响应未被伪造为成功。该结论不声称 OS 级沙箱或远程证明。 |
| A-07 回归、预算与收口 | **PASS** | 定向 EffectWitness 套件 26 项通过；完整 Runtime 226 项通过、2 项 Docker provider 不可用而跳过。RPF-43/44/48/49/50 anchored verifier 均退出 0；`verify-reviewed-artifacts.py`、`verify-public-docs.py` 与 `git diff --check` 通过。真实启动计数为诊断 1、正式 0；业务 Scenario 0；所有本任务进程退出且 2018 端口关闭。 |
| A-08 Git 与 TASK_RESULT | **PASS** | 仅对白名单文件定向暂存、focused commit 并普通 push 到本 Plan 分支；推送后独立核验远端分支 SHA 与本地 HEAD 一致，`main` 未变。未创建 PR、未合并、未发布、未部署。最终 commit SHA 在聊天回执报告，避免 RESULT 自指。 |

## 身份与来源

- RunProof 执行前 HEAD 与 parent 均为 `68ac08de12048856fe38aa7e8548ad5bb3516a9b`；本地分支从该精确 parent 创建。Feature push 不触发 main 专属 Release Gate；未执行 Release、Deploy 或手动 workflow。
- 只读来源：`MyKr-YSteinsK/config-center@0258b9cef02ea74a40989d035c79256c776409c0`。源清单为 110 文件、393,800 bytes，manifest SHA-256 `33861f89974fab845521b38aeefbc62d2579e5fe7daa4b79af52230a90e1f343`；JAR 为 66,981,576 bytes，SHA-256 `906e7d923f31454b046bf306f3eab844ae51cf9c6da85b3d43c32896980c9f70`。来源从既有 rev-2 task-local 已验证副本复制，未构建、下载依赖或修改 config-center 仓库。
- 诊断冻结的 Runtime source digest：`4b25004811fdd5fb9d59fb7e26d3c60257aebbf9b5f4e38185831fb88ba24b24`。诊断后基于真实 PID 根因修改 launcher 解析；最终代码 digest 为 `5dd9cb3ff005263bf037948ba21aca6f80e7b679d7910f90daab6d5a66805922`。两者不同，因此本轮诊断结果不能被用来解锁最终代码上的业务运行。
- 诊断 ID `rpf51-diag-be57a4a75ea0402e9ea6cfeb17d026f1`；JAR、端口、运行时身份分别记录于 `readiness-diagnostic.json`。诊断结果 SHA-256 `6251eaaa773fa3b44fce4038e6d5d5e11fb37e81834e44ff707a15fb8ff195bc`。诊断时段为 `2026-10-18T11:08:08.853Z` 至 `2026-10-18T11:11:07.914Z`。Windows 进程树及 listener PID 的去敏关联观察已补入 readiness 摘要；摘要 3,905 bytes，小于 16 KiB。
- 新 `.local/rpf-51-rev3/` 共保留 119 个文件、67,446,540 bytes，包括核验后的源码/JAR 与本轮诊断材料。未执行删除；正式 scenario 目录和 marker 未创建。旧 rev-1/rev-2 运行目录与 one-shot marker 未触碰。

## Readiness 修复与诊断结论

原探针通过 `shutil.which("java")` 得到 `C:\Program Files\Common Files\Oracle\Java\javapath\java.EXE`。该 launcher 的 Popen PID 为 `29916`，实际 JDK 可执行文件 `C:\Program Files\Java\jdk-17\bin\java.EXE` 对应子进程 PID `3856`，后者监听 `127.0.0.1:2018`。因此 TCP 已可连接，但原探针只把 listener PID 与 Popen PID 比较，持续报告 `LISTENER_PID_MISMATCH`，并按安全合同拒绝发 HTTP。TCP 成功分支已有有界退避，未发生忙等。

修复后的 `_java_info()` 先向 launcher 查询 Java properties，读取 `java.home`，再直接使用 `bin/java.exe`（非 Windows 使用 `bin/java`）并独立校验 Java 17 版本。新增单测确认返回的是该直接 JDK 路径。由于诊断 one-shot 已消费，修复只得到代码与测试验证；没有声称其已通过新的真实 PID/listener/health 联合诊断。

## 验证记录

- `python -B -m unittest runtime.tests.test_effectwitness_config_http -q`：26 tests，exit 0。
- `python -B -m unittest discover -s runtime/tests -p 'test_*.py' -q`：226 tests，exit 0，`OK (skipped=2)`。2 项是 `test_docker_integration` 与 `test_rpf05_runtime` 的 Docker provider 不可用跳过；运行期间 OTel bounded queue/export timeout 日志未导致测试失败。
- `python -B runtime/verify-reviewed-artifacts.py`：PASS；source digest `cd31a021550f680a3ca512d210b9533a262fb734a769d4f8d3f6bee11adacaf7`。
- `python -B ci/verify-public-docs.py`：`PUBLIC_DOCS_PASS files=18 pairs=7`。
- 既有离线锚验证：RPF-43 `ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e`；RPF-44 `21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873`；RPF-48 `c00eb35fec0710ff0acd43fc09d5a2b318ff795e27af40dff4b86a9f732af4a2`；RPF-49 `04ac629bbfb54a4b85eddf902bbf765db7c57ea0c509e0b539280858c7d4bc9b`；RPF-50 `b8f288db5dd76a142bbfb69a04d15ce9206d2cd9dbe28ef6effdb59382f5ef4a`，均为各自既有 verifier 接受的锚定结果、exit 0。
- `git diff --check`：PASS。没有 Key、Authorization 或运行日志被加入 tracked 文件。

## 限制与后续

本轮停止于 A-03。A-04/A-05 保持 `NOT_RUN`，RPF-51 整体为 `PARTIAL`，不能申请 `COMPLETE`。下一步若要验证 direct JDK PID 与健康 HTTP，需要新的 Plan 授权新的诊断 one-shot；只有新诊断完整 PASS 后才可考虑新的业务 Scenario。该 Plan 的一次 Java 诊断额度已消费，不可重置或重试。

本分支提交和远端 SHA 在聊天回执中记录；本 RESULT 随最终提交一起冻结，不回填自身所在 commit SHA。
