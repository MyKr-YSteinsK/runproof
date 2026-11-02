# RPF-85 / rev-1 — Required Coverage Handoff

数据流：`Router child receipts → immutable ledger → assess → original repository checks → RPF-12 → enforce`。

Router、matrix、Runtime 测试、历史证据和 RPF-12 决策逻辑均不修改。独立验证器只在 portable 方法的 source、身份、selection、原生 progress、result、退出状态与日志 hash 自洽时允许下游诊断继续。它不从 stdout 文本猜结论，也不把 required UNAVAILABLE 当作 PASS/SKIP。

工作流实际接口：

```sh
set +e
python -B ci/run-runtime-contract-tests.py --output "$GITHUB_WORKSPACE/ci-results/rpf84-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
router_rc=$?
set -euo pipefail
python -B ci/verify-runtime-coverage-handoff.py assess \
  --ledger "$GITHUB_WORKSPACE/ci-results/rpf84-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}/ledger.json" \
  --runner-exit "$router_rc" \
  --output "$GITHUB_WORKSPACE/ci-results/rpf85-coverage-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}.json" \
  --run-id "$GITHUB_RUN_ID" --attempt "$GITHUB_RUN_ATTEMPT" --commit "$GITHUB_SHA"
```

只包围 Router 的 `set +e` 保留真实 `$?`。`assess` 失败即阻断原下游检查。原 Java/Node/Docker、RPF-83 聚焦、reviewed artifacts、RPF16/17/18、Golden Demo、Maven/npm 和 fresh RPF-12 命令保持原样。

原 Artifact step 后的 always Barrier：

```sh
python -B ci/verify-runtime-coverage-handoff.py enforce \
  --ledger "$GITHUB_WORKSPACE/ci-results/rpf84-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}/ledger.json" \
  --status "$GITHUB_WORKSPACE/ci-results/rpf85-coverage-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}.json" \
  --run-id "$GITHUB_RUN_ID" --attempt "$GITHUB_RUN_ATTEMPT" --commit "$GITHUB_SHA"
```

`enforce` 重新读取全部来源和执行收据，核对状态 JSON，而非只信任 `all_required_status`。有效覆盖缺口 exit **1**，无效/缺失证据 exit **2**；只有全部 required 真满足才可能 exit **0**。状态永远不授予 Release/Deploy，且独立追加 Job Summary，不改写原 RPF-12 summary。Artifact 保留原两个 RPF-12 文件，并增加 `ci-results/rpf85-coverage-*.json`。

本地测试入口：

```sh
python -B -m unittest -v ci.test_verify_runtime_coverage_handoff
```

本地 fixture 只在新 `.local/rpf-85-coverage-handoff/` 的 fresh 子目录内生成。CLI 的 `--synthetic` 将结果标为 `SYNTHETIC_OFFLINE_TEST`，GitHub Actions 明确拒绝该标志。本地 688 PASS/5 SKIP/539 UNAVAILABLE 是重建的一致性模拟，**不是本轮 Runtime 执行**；实际 Hosted 来源仍以当前 run/commit、真实 Router 收据与完整 source 绑定为准。收据 hash 是同一受控 runner 的来源校验，不是第三方签名或独立 Issuer。

证据入口：[RESULT](RESULT.md)、[G0](preflight-diagnostic.json)、[verification](verification-diagnostic.json)、[counterexamples](counterexamples.json)、[decision](decision.json)。旧 Run `41408665295` 的 Linux 688/5/539 是历史事实；新 hosted 下游结果必须独立观察，不预填成功。
