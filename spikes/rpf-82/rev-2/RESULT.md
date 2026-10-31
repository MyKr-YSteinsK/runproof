# TASK_RESULT — RPF-82/rev-2

**Status: Partial**。Attempt-02 G0 有效，隔离 Router、RPF-75 正负控与 RPF-60 自持根验证有实际局部通过。冻结后一次分层汇总发现两项分类遗漏，A04 FAIL；按 Plan §5.4 停止进一步扩大修改。未 commit、未 push、未触发新 hosted CI，正式 Canonical Release Gate NOT_RUN。

## 基线、G0 与现场保全

- 仓库为 `MyKr-YSteinsK/runproof`，现有 main 单工作树，Base/当前 HEAD 为 `531338ad88e9ba8e6d4d4b271b10fbe7d161d46e`。
- 本地 `git -c http.sslBackend=schannel -c http.sslVerify=true ls-remote origin refs/heads/main` 真实返回固定 SHA，网络已恢复。未关闭证书校验、修改持久网络配置或借 GitHub API 代替本地 Git。此前 TLS 故障根因未确证。
- Attempt-02 重新逐项核验根、分支、HEAD、tracked-clean、remote、worktree 元数据、AGENTS/Project State、workflow blob、ACL、平台、空占路径、ignore/reparse。ACL 使用当前实际 pwsh，并显式 Stop/try/catch/exit，根与 `.local` 两项 exit 均为 0。
- 收据 stdout 先输出，新的 `.local/rpf-82-rev-2-g0-receipt-attempt-02.json` exclusive-create、flush/fsync，随后才创建 `.local/rpf-82-rev-2-ci-isolation-attempt-02/`。原始收据 hash 与各项 stdout/stderr hash 见 preflight diagnostic。Windows 标准库目录 fsync 为 UNAVAILABLE；文件 fsync 已实际完成。
- Attempt-01 的错误 PASS 收据仍为 INVALID，旧收据/旧任务根原样保留，没有重开或回填。不访问 docs/reviews、旧私有 WAL、历史证书；不恢复 RPF74/rev4 或 RPF81/rev2 暂停实验。

## 实现与真实验证

现有工作树内为精确 2M+9A：工作流入口替换为 Router 单测与 Router CLI；RPF-60 只改 harness 的 owner/temp root 和竞争子进程路径传递；新增 Runner、matrix、单测及本目录六份文档/diagnostics。原 RPF-75 Probe/audit hook、两项 rev-3 独立断言与其 Runtime 实现均未修改。

- Runner 标准库单测最终 22/22 PASS。覆盖输入 schema、duplicate JSON/nonfinite、漏/重复/新增模块、source drift、例外重叠/未知方法、虚假 PASS、原生类 skip、known failure 不可隐藏、owned root、环境 allowlist、真实 hook/兄弟进程、crash/timeout/截断/缺结果等。
- 初次单测有未关闭 stdout pipe 的 ResourceWarning，冻结前修正并保留早期日志。冻结前 RPF-60 聚焦首次出现 Router 未适配 Windows `subprocess.Popen` 审计参数（executable=None、serialized command），以及 120 秒超时；原日志/身份保留。修正编排层参数处理后，RPF-60 原 9 项全部 PASS，用时 244.694 秒，模块 timeout 调为 300 秒，整体预算仍 1800 秒，workflow 35 分钟不变。
- RPF-75 聚焦 87 PASS、1 UNAVAILABLE（旧 private absent.json 读取前提）。原 audit hook 仍拒绝 subprocess/socket 事件，真实 subprocess 被拦截；新兄弟进程完成 5 字节 127.0.0.1 回环及当前 Python 子进程 exit 0。
- 冻结后负控包含真实 crash exit 7、timeout=true、输出 2097153 bytes 导致 truncated=true、exit 0 但无结算文件、执行前完整 inventory 被改导致 exit 2。均不得得到 PASS；原始 child 输出和 launch receipts 位于新任务根，公开仅保留有界数据/hash。
- AST/compile（内存、不产生 pycache）、strict JSON/schema/duplicate/nonfinite 负控、真实 PyYAML parse、Git diff check 已完成。冻结来源 LF SHA-256 见 verification diagnostic；汇总后核验身份未变。

## 一次分层汇总及覆盖账本

当前环境为 Windows/Python 3.14.6，不是原 hosted Linux/Python 3.12 环境。57 个模块均由独立子进程真实 TestLoader 发现，43 个模块进入 portable 执行；发现 1232 项，每项恰好一个 route，全部 required=true。

| route | discovered | PASS | 原生 SKIP | UNAVAILABLE | ERROR |
|---|---:|---:|---:|---:|---:|
| PORTABLE | 695 | 688 | 5 | 0 | 2 |
| WINDOWS_NATIVE | 35 | 0 | 0 | 35 | 0 |
| DEDICATED_RUNNER | 417 | 0 | 0 | 417 | 0 |
| LEGACY_SDK_PRECONDITION | 16 | 0 | 0 | 16 | 0 |
| FROZEN_PRIVATE_ARTIFACT | 69 | 0 | 0 | 69 | 0 |
| 合计 | 1232 | 688 | 5 | 537 | 2 |

`executed=true` 表示所选 suite 已返回 unittest 状态；5 个类级原生 SKIP 的方法体没有执行，不能视作断言通过。690 个方法进入方法体，688 PASS、2 ERROR。537 项未执行，不计 PASS。Windows 路由的原受信环境/历史 owner 并未因此获执行授权；本轮也没有新增 Windows CI job。实际 Linux portable 复验尚未进行，A04 不能据本机结果称为完整通过。

原固定 Run 40920947296 的 117 errors 已重新按原日志核对：audit hook 41、RPF60 父目录 2、旧 venv 12、_winapi 5、SYSTEMROOT 30、RPF73R2 收据 26、RPF78 冻结输入 1。发现数比 testsRun 1118 多 114，来自旧类级 setup 错误/skip 挡住的方法：RPF67 27、RPF68 15、RPF78 frozen 67、Docker 2、RPF05 3；不是删减测试。

### 两项新增分类反例：原 ERROR 封存

- `test_effectwitness_pge_r81.ConformanceTests.test_injected_fsync_failure_stop`
- `test_effectwitness_pge_r81.ConformanceTests.test_injected_write_failure_stop`

矩阵此前将它们默认归为 PORTABLE，遗漏 `self.persist(...) -> Host -> Journal -> mkdir` 的间接历史 owner 依赖。执行发生历史路径求值，但在真正 mkdir 前被 Router audit guard 以 `RPF82_PROTECTED_PATH` 拒绝；没有执行 Journal 写入或读取旧 WAL。它们记为真实 ERROR，不能算产品故障已复现或 RPF81 恢复已启动。分类器存在这项语义遗漏，A04 FAIL；本轮不在冻结后改桶、覆写失败结算或再跑完整汇总。

下一次修订可考虑按 `persist` helper 的实际前提校正这两个 exact selector，并以保留当前候选/失败身份的新冻结候选验证；这是一项后续建议，本轮未实施。不能移植旧 receipt、复制私有输入或降低 required coverage。

### 两项既有独立缺陷仍未解决

Windows basename 脱敏和 Linux stdlib 定位的原方法都保留 PORTABLE、原源码/期望不变。本机 Windows 实际均 PASS；固定 hosted Linux 原记录均 FAIL。平台差异不能宣称修复，它们继续留待 rev-3 的独立授权。

## Gate 与 Git/CI 收口

| Gate | 实际状态 | 说明 |
|---|---|---|
| G0 | PASS | Attempt-02 有效收据；旧失败现场保全 |
| A01 | PASS | 仅 2M+9A；无旧 Runtime/Probe/证据修改 |
| A02 | PASS | 57 模块、1232 IDs 一对一路由；语义正确性另列 A04 |
| A03 | PASS | 原 hook 仍有效、兄弟进程可用、父进程未受污染 |
| A04 | FAIL | 两个 helper 的 owner 前提漏分；Linux/历史环境覆盖缺口保留 |
| A05 | PASS | RPF60 新根、缺父目录负控、9 个原方法和竞争断言通过 |
| A06 | PASS | 本轮可执行 Router/guard/失败传播/格式负控通过；未伪造历史收据 |
| A07 | NOT_RUN | 未新 push，未触发新 hosted run；原 Run 仍 FAILED |
| A08 | NOT_RUN | A04 未过，未满足推送最低门；无 commit/push |
| A09 | PASS | RPF82 整体 PARTIAL、RPF74 PAUSED、RPF81/rev2 BLOCKED、RPF78/rev1 A08 FAIL 保留 |

报告/代码保存在本地工作树，没有被 GitHub 接受或完成交付。没有修改三份 Project State、历史报告或原 Run 结论。Provider 调用、真实 SDK child、生产/外部业务写、部署/发布均为 0；本机/Actions 实际费用 UNAVAILABLE。冻结来源和失败证据保留，不以隔离层局部成功代替 Canonical Release Gate PASS。
