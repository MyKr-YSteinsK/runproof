# RPF-83 / rev-2：Canonical CI 跨平台执行前提

本轮仅修复三个确定性问题：拒绝文件诊断的 Windows/POSIX basename、测试侧真实 stdlib 定位，以及 RPF-60 的 fresh CI owner 前提。保留 RPF-75 Audit Hook、原全局 Runtime suite、下游 Canonical Gate 和未激活 RPF-82 Router。

授权范围为 5 个已有文件及 8 个新增文件。生产改动限于 `config_live_external._safe_denied_basename`；SDK/网络/文件读取 Guard 未扩权。RPF-60 原九个测试方法、原断言和业务算法的 AST 不变。本轮不单独运行其九项耗时测试。

独立聚焦入口（工作流先于全局 unittest 导入执行）：

```sh
python -B -m unittest -v \
  runtime.tests.test_effectwitness_config_live.ConfigLiveContractsTests.test_denied_file_diagnostic_keeps_only_a_bounded_safe_basename \
  runtime.tests.test_effectwitness_config_target.ConfigTargetVerifierBoundaryTests.test_sdk_child_guard_allows_reads_from_resolved_base_python_runtime
python -B -m unittest -v ci.test_rpf83_ci_preconditions
```

CI preconditions 只验证 owner admission，所有目录 fixture 留在新的 `ci-results/rpf83-preconditions-{run}-{attempt}-{uuid}` 下。测试构造隔离的 synthetic checkout，用真实 symlink 或 Windows stdlib junction 验证拒绝路径；不运行原九项业务测试，不读取历史 owner。工作流为后续原全局 suite 显式绑定 `ci-results/rpf83-r60-{run_id}-{run_attempt}`；缺环境、已占用或不符合 CI 身份均拒绝。

证据入口：

- [RESULT.md](RESULT.md)：唯一封存 TASK_RESULT；Git/CI 最终收据由交付聊天补证。
- [preflight-diagnostic.json](preflight-diagnostic.json)：rev-2 G0 与 rev-1 检查器故障、收据指纹及时间顺序。
- [source-identity-impact.json](source-identity-impact.json)：旧/新源码身份与直接引用审查；旧 Witness 不重签。
- [verification-diagnostic.json](verification-diagnostic.json)：冻结身份、资源上限、实际命令/退出码/输出摘要。
- [negative-controls.json](negative-controls.json)：basename、stdlib、owner、workflow 负控。
- [ci-failure-ledger.json](ci-failure-ledger.json)：旧 CI 失败来源、未修复义务和封存时尚未运行的新 CI。

本地 Windows 正式聚焦 2+6 tests PASS。Linux 证据须由新 SHA 的 hosted step 实际执行提供。聚焦通过不代表全局 CI、Canonical Release Gate、旧 SDK 复现或产品阶段通过；RPF-82 整体仍 PARTIAL。
