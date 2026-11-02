# TASK_RESULT — RPF-83 / rev-2

**Status: Partial（封存时：本地实施及聚焦验证完成，Git 交付与 Linux hosted 验证尚未执行）**

- Base：`76088c6e268388fe414956d48cad0242641ae01a`；branch：`main`。
- 稳定 owner：`rpf-83-rev-1-canonical-ci-preconditions`。路径中的 rev-1 不代表追认前轮 G0。
- 本报告在 commit/Push 前封存；未来 SHA、远端 readback、Actions run/step 结论由最终聊天补证，不 amend 回填。

## 实际实施

1. `_safe_denied_basename` 以与宿主 OS 无关的词法分隔处理 Windows、POSIX、UNC 和混合路径，只返回最多 80 个 ASCII 文件名字符。空名、dot/parent、遍历片段、尾分隔符、设备路径、ADS/drive-relative、bytes 和无效 PathLike 返回 `UNKNOWN`；不 resolve、不访问输入文件。原 `C:\Users\Alice\secret token.json -> secret_token.json` 断言保留。
2. 标准库测试通过 `sysconfig` 与已导入 `importlib.metadata` 的真实文件元数据定位，断言它属于确切 stdlib 下的 `importlib/metadata/__init__.py`。原 Guard 未改，允许 stdlib 的同时仍拒绝越界 synthetic path；只调用 audit callback，不打开越界文件。
3. RPF-60 harness 保持 missing-env 失败，补齐 lexical scope、CI workspace/run/attempt 身份与新 CI owner 的 create-only 检查。新增微型测试验证 missing env、已占用、路径逃逸、CI 身份错配和实际 reparse 拒绝；原九个测试方法及核心算法 AST 不变。
4. 工作流增加独立聚焦 Python 进程，并给原 `Run repository contract checks` 配置 fresh owner 环境变量。严格 YAML 对比证明去掉这两处新增内容后与 Base 完全一致：原触发器、`contents: read`、35 分钟、全局 suite、下游 Gate、summary/artifact 均保留。

## 验证与边界

本地环境为 Windows / CPython 3.14.6；不是 Linux/Python 3.12 的执行证明。正式验证两组各一次：跨平台回归 **2/2 PASS**，CI owner 前提 **6/6 PASS**。进程耗时约 0.540/0.444 秒，峰值内存约 31.4/32.6 MiB。每组上限为 60 秒、512 MiB 进程内存（Windows Job Object 强制限制）、1 MiB 合计输出；均正常退出、输出排空，无超限或重复正式测试。

冻结前 AST/compile 和严格 YAML 校验通过；四个 workflow 篡改负控均拒绝。默认 `git diff --check` 将既存 CRLF 的 CR 报成 trailing whitespace；逐条确认只有 CR 后，使用命令级 `cr-at-eol` 兼容原行尾，保留其它 whitespace 检查，exit 0。失败诊断保留，未改系统 Git 配置，未正规化历史源码或证据。

rev-1 子 Windows PowerShell 无法加载 Security 模块的 exit 1 保留为 `CHECK_HOST_ERROR`。rev-2 使用明确的 pwsh 7 对同范围父目录重新核验 owner/ACL/reparse，全部成功；先 stdout、再 exclusive-create 收据并 flush/fsync、最后创建任务根。收据附加 aggregate stdout hash 的 Windows 换行 framing 标注有误，原收据未覆盖：独立诊断提供其实际 CRLF 指纹，并逐项复核全部子进程原始 stdout/stderr hash；核心 G0 检查与时间顺序不变。Windows 目录 fsync 为 `UNAVAILABLE`，文件 fsync 实际完成。

正式实验资源：Provider/API/SDK、Java、Docker、本地业务服务及业务写均 **0**。本地完整 Runtime、RPF-82 Router、RPF-60 九方法模块、旧 Witness/SDK 重演均 **NOT_RUN**。没有访问旧私有 WAL，没有恢复 RPF-74/RPF-81 暂停现场。

## Gate 状态（封存时）

| Gate | 状态 | 证据 / 限制 |
|---|---|---|
| G0 | PASS | 真实 HTTPS Base、干净工作树/index、pwsh ACL、空占/ignore/reparse、hook/CI 边界与持久收据 |
| A01 | PASS | 精确 5M+8A；源码范围 AST 检查；旧证据和 Router 未修改；最终 staged 审查仍需交付时核验 |
| A02 | PASS | 原 basename 断言及同一方法新增安全负控通过 |
| A03 | PASS | 直接来源引用审查与 old/new raw/LF SHA；未改旧 Witness/Source Map/verifier |
| A04 | PASS | 真实 stdlib 允许、越界拒绝；被测 Guard 未扩权 |
| A05 | PASS | 六项 owner 微型测试通过；原九方法 AST 不变，完整模块 NOT_RUN |
| A06 | PASS | 严格 YAML 等价对比与四项篡改负控 |
| A07 | PASS | Windows 正式 2+6 PASS；Linux hosted 尚待实际结果 |
| A08 | NOT_RUN | 封存时 commit/Push/readback 未执行，最终聊天补证 |
| A09 | NOT_RUN | 新 hosted Run 未开始，不能预填 PASS |
| A10 | PASS | TASK_COMPLETE、EVIDENCE_ACCEPTED、STAGE_ADVANCED 分离；无 release/deploy 授权 |

## Source Identity 与剩余义务

Base 中 child 的 raw SHA-256 是 `0d977965f72d2a8ade8d02d0ce4963742cb8952976f012459c58423aefe9bdfe`，本次冻结后为 `d8e01dcb5c8e63a227f188d67c1e2a0b52eb203457e6d6159f24f71ec170d813`。其余 5M old/new 身份与直接依赖逐项见 [source-identity-impact.json](source-identity-impact.json)。动态 source closures 将得到新的摘要；旧 Witness 仍绑定旧身份，不由本轮单元测试重新证明 live 兼容性。

旧 Run `41172290021` 的 `1109 tests / 116 errors / 2 failures / 2 skipped` 来自 Plan 带入的 Architect 固定 SHA 取证，不是本地复跑。原 RPF-75 Audit Hook 污染、Windows-only、历史 SDK/venv、RPF73R2 环境收据、RPF78 frozen inputs 和 RPF60 300 秒问题均继续保留义务，不删除测试，不将 UNAVAILABLE 算 PASS。新 hosted 聚焦 PASS 仍不代表原全局门通过；完整 Canonical Gate 只在原前置检查正常通过后执行。

RPF-82 整体 **PARTIAL**；RPF-74/rev-4 **PAUSED/DEFERRED**；RPF-81/rev-2 **BLOCKED**；产品阶段与 Release Authority 不变。本任务只有在实际交付并取得 hosted 聚焦 PASS 后，才可按 Plan 条件由最终聊天结算为 Complete；不代表 Architect 已接受证据或批准推进阶段。
