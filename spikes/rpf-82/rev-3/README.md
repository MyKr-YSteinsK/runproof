# RPF-82/rev-3：间接 helper 分类收口与历史源码保全

本修订继续现有 main 工作树，保留 rev-2 的失败结论及三个修复前 CI 输入原始字节。它修复的是分类器的隐含 owner 依赖；Windows basename 与 Linux stdlib 两项独立缺陷仍待另行授权的 rev-4 或后续任务。

## 运行边界

标准库入口保持为 `ci/run-runtime-contract-tests.py`。父进程不导入 Runtime 测试，模块在独立子进程中发现/执行。现有 workflow 仍调用 Router 单测和 CLI，原 Canonical Release Gate、失败传播、权限、触发与 artifact 合同未改。

```text
python -B -m unittest ci/test_run_runtime_contract_tests.py -v
python -B ci/run-runtime-contract-tests.py --inventory-only --output .local/rpf-82-rev-3-classifier-closure/NEW_UNUSED_NAME
```

输出名须在任务已有授权内且未占用；示例不授权任意新根。`--inventory-only` 不执行方法体；未满足条件为 UNAVAILABLE，portable 方法为 NOT_RUN。退出 1 的 `REQUIRED_COVERAGE_UNAVAILABLE` 表示全套覆盖未满足，不等于分类器异常或 portable 全套通过。正式 hosted 入口不带该选项，实际 FAIL/ERROR 继续失败传播；没有以编排成功代替 canonical PASS。

## 有界静态依赖注册

matrix v2 保持所有 57 个明确模块、源码 LF SHA-256、精确类/方法规则和 ALL_DISCOVERED required coverage，增加 RPF-81 的 helper registry。它固定测试源码、contracts/journal/barrier 三个依赖的来源，静态遍历类内 self helper 调用，标记已审查的 owner 构造入口，并拒绝未注册方法、未知/递归/重复 helper、未审查的外部调用和依赖漂移。它不是通用 Python 程序安全分析器。

真实原错误为：

- `ConformanceTests.test_injected_fsync_failure_stop`
- `ConformanceTests.test_injected_write_failure_stop`

两者经 `persist -> Host(..., True) -> Journal(..., create=True) -> c.case_dir -> WORK/sessions/... -> mkdir`。新增 exact `LEGACY_OWNER_ROOT` 路由，reason 为 `HISTORICAL_OWNER_ROOT_NOT_AUTHORIZED`；这表示运行会创建受保护历史 owner，不能泛称缺少 SDK 或冻结 artifact。原有其他测试规则不变，仍保留九个 RPF-81 portable 方法。Plan 提到的 torn/missing-tail 两项原本已经正确归入不可运行前提，不是这次真实 ERROR。

注册表的 owner 入口不可被重新声明为 approved portable；测试使用独立合成源码证明 `test -> helper -> 隐藏 WORK mkdir` 会静态拒绝，而返回整数的 benign helper 可保留并实际执行。模拟 audit event 验证旧路径 mkdir/open 会被守卫先拒绝，不在旧根上调用系统 mkdir/open。

## 新 owner 的 RPF-60 接缝

rev-2 冻结的 RPF-60 测试文件只接受旧 rev-2 owner 和 CI 根，rev-3 不修改它。Router 对这个来源已固定的测试 harness 作临时 owner 适配，将原竞争子进程的完全匹配命令转交同一 Python 的固定 `--r60-race` CLI；保留两个竞争进程、同一输入 plan/path/owner、原 Ledger/reservation 操作和全部原断言。子进程只接收 JSON stdin，不接收可执行输入，不执行原脚本文本，也不更改业务 Runtime。

当前 Router 只写 rev-3 新私有根或已授权 CI 目录，不复用 rev-2 现场。rev-2 测试文件、工作流和六份 rev-2 报告字节均保持原样。

## 来源与结论

`pre-repair-sources/` 是三份仅供审查的原始字节快照，不导入、不执行、不加入测试发现。它们保留 CRLF 原字节，如后续满足交付门禁，暂存须使用命令级 `core.autocrlf=false` 并核对 staged/remote blob 原始字节 hash，不用 LF 规范化冒充 raw identity。本轮因 A05 超时未暂存、未 commit/push。快照和 rev-2 报告的双 hash、修改后的来源身份、两项更正及完整账本见本目录 diagnostics。

本地正式验证只包括 Router 单测、原 RPF-60/RPF-75 聚焦，以及一次完整 inventory/classification；不在本机重跑其它 HTTP/业务测试，也不恢复 RPF74/81 实验。实际执行、NOT_RUN、UNAVAILABLE 和历史来源分开；原 1232 发现数与 hosted testsRun 1118 的差异沿用可核验的 114 个类级 setup/skip 方法解释。

RESULT 在交付前封存；最终 main SHA、Push 和 hosted CI 结果由聊天补证。任何 portable 局部通过均不批准全部 canonical CI、阶段推进、Provider、真实 SDK 或部署。
