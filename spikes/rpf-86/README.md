# RPF-86 / rev-1 — Dedicated Owner 准入试点（B 未激活）

本轮研究“历史逻辑身份与新物理写根能否分离”，不修改正式 Router、matrix、Handoff 或 1,232 方法责任账。当前结论是 **B_UNACTIVATED**：一次冻结前原生五方法试运行实际得到 **3 PASS /2 ERROR**，完整准入不成立。

两个 ERROR 均止于 `pinned_sdk_fields()` 请求读取 `spikes/rpf-53/rev-6/config-live-evidence.json`。这个 helper 和历史证书不在本轮精确读取白名单中，Guard 在打开前拒绝。没有读取证书内容，没有扩权、复制历史输入、改原方法或补造 SDK identity。

候选入口（**未接 CI，不表示已经批准运行成功**）：

```sh
python -B -m unittest -v ci.test_run_rpf86_owner_admission
python -B ci/run-rpf86-owner-admission.py --output <fresh-authorized-absolute-root>
```

本地 root 仅限 `.local/rpf-86-owner-admission/` 下新建子目录；A 路径的 CI scope 校验已实现为 `ci-results/rpf86-{run}-{attempt}/`，但本轮不新增 workflow step。输出 CREATE_ONLY；重复 owner/result、旧路径、escape、reparse 和错 CI 身份均拒绝。

子进程先安装 CPython Audit Hook 和 `os.stat/os.lstat/Path.resolve/os.mkdir` 的有限元数据拦截，再 import 原测试。唯一 Runtime 常量 patch 为 `pge_dual_contracts.WORK`；原方法、断言、逻辑 owner `rpf-63` 和源身份源码不改。元数据拦截属于进程局部 harness，不是生产代码变更。Python API 覆盖不等于 kernel sandbox，任意 native syscall/OS process-tree 全量证明仍为 UNAVAILABLE。

正式 harness 单测 **8 PASS**。独立临时子进程仅复核已保留失败 Run 的结果、source snapshot、物理 manifest 和日志绑定，**没有重跑原五方法**。正式五方法执行为 NOT_RUN：已知输入权限不满足，未机械重试。`verify-failure` 模式仅为本次 3/2 负结果核验，不是通用历史 Run 恢复器。

证据：

- [RESULT](RESULT.md)：单一封存 TASK_RESULT，B 决策与逐 Gate。
- [owner-dependency-ledger](owner-dependency-ledger.json)：417 IDs/30 模块，全部仍 required/UNAVAILABLE；仅静态读取指定 30 个文件，未审 helper 标 UNKNOWN。
- [verification](verification-diagnostic.json)：来源、冻结、运行/预算与独立负证据复核。
- [counterexamples](counterexamples.json)：实际旧根 open/mkdir/stat、socket/subprocess、canary、reparse、假绿和进程失败负控。
- [preflight](preflight-diagnostic.json)、[decision](decision.json)：G0 与保留边界。

539 项 required UNAVAILABLE 不减少。三个方法的局部 PASS 不构成正式 dedicated lane admission、Linux 独立执行、历史 Witness 重签或产品发布资格。下一 Plan 需精确授权 helper/证书只读审查，或选择另一 cohort；本轮不自行扩大。
