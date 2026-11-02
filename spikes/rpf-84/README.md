# RPF-84 / rev-1 — Canonical CI 隔离与 RPF-66 历史来源

本轮选择 **A_ACTIVATED_FAIL_CLOSED**：复用已有 Router，将原全局 unittest 一行替换为独立模块进程执行。RPF-83 聚焦 step、原其它 checks、触发器、权限和 35 分钟 job 上限保持不变。

```sh
python -B -m unittest -v ci.test_run_runtime_contract_tests
python -B ci/run-runtime-contract-tests.py --inventory-only --output <authorized-absolute-root>
python -B ci/run-runtime-contract-tests.py --output <authorized-absolute-root>
```

本机 root 仅限本轮 `.local/rpf-84-ci-isolation/` 的 fresh 子目录；hosted 使用 `ci-results/rpf84-{run_id}-{run_attempt}/`。命令使用 CREATE_ONLY，不复用已有输出根。完整执行只运行 PORTABLE 方法；其它 required 义务留在账本中为 UNAVAILABLE，导致非零退出。禁止使用旧 RPF-82 私有根补 fixture 或复活预算。

本地实际 inventory 为 **57 模块 / 1232 唯一方法 ID**，与历史身份集合相同；不是复用历史 PASS。其中 **693 PORTABLE / 539 UNAVAILABLE**。本地没有执行完整 Runtime lane；正式 Router 单元 **41 PASS**，另有真实 RPF-60 两子进程竞争聚焦 **1 PASS**。

RPF-66 历史等价断言固定在旧 Git blob，不再随当前 sanitizer 漂移。Git 对象逐字节证明只有一处 max_tokens 256→512；Windows checkout 的 CRLF raw hash 与 LF 映射分别记录。独立控制验证冻结 Guard 的五项拒绝。原完整方法仍依赖历史 `fresh()` owner，维持 DEDICATED_RUNNER/UNAVAILABLE，未用独立控制冒充其 PASS。

证据导航：

- [RESULT.md](RESULT.md)：封存时逐 Gate 事实及限制；未来 Git/CI 由最终聊天补证。
- [preflight-diagnostic.json](preflight-diagnostic.json)：G0 收据指纹、退出码及创建顺序。
- [isolation-coverage-ledger.json](isolation-coverage-ledger.json)：1232 个方法的 required route/disposition、实际动态发现与聚焦收据。
- [source-identity-ledger.json](source-identity-ledger.json)：5M old/new SHA、R66 blob 来源与 EOL 分栏。
- [counterexamples.json](counterexamples.json)：原 32 项保留、新负控及真实 child 收据。
- [verification-diagnostic.json](verification-diagnostic.json)：源冻结、正式执行、预算与回收边界。
- [decision.json](decision.json)：A 激活理由、覆盖缺口、未改变的产品状态。

完整 hosted 验证须查看新 commit 对应 Actions；独立聚焦 PASS 不代表 fresh Canonical Gate PASS，UNAVAILABLE 不算 PASS/SKIP。每 child 最多 300 秒、2 MiB 输出，完整 lane 最多 1500 秒；剩余 deadline 钳制后续 child，超时精确 kill/wait，不宣称获得 OS group 全后代回收证明。
