# RPF-82/rev-2：隔离 Runtime 测试与保留覆盖责任

本修订将每个已跟踪 `runtime/tests/test_*.py` 模块的导入、unittest 方法发现和执行放入独立 Python 子进程。父 Router 不导入测试模块；RPF-75 的原始离线 audit hook 保留在其专用进程。RPF-60 测试 harness 接收显式任务临时根，其竞争子进程获得同一 owner；旧 Runtime 和历史证据不变。

## 使用与退出值

在仓库根执行（标准库 Python；不安装历史 SDK）：

```text
python -B -m unittest ci/test_run_runtime_contract_tests.py -v
python -B ci/run-runtime-contract-tests.py --output ci-results/runtime-contract-tests
```

输出目录必须未占用，且位于本轮授权私有根或 `ci-results/`。每次独立发现和执行保存受控原始日志、SHA-256、exit、timeout/truncation 和方法结算；`ledger.json` 是汇总入口。`--inventory-only` 只做发现，`--only runtime/tests/test_NAME.py` 只执行指定模块的 portable 方法，仍发现并记录其余模块。

`0` 要求全部必需方法实际通过或取得 unittest 原生 SKIP，且没有覆盖缺口。测试失败、子进程失结算/超时/截断、发现变化及 `REQUIRED_COVERAGE_UNAVAILABLE` 返回 `1`；无效输入、schema 或清单返回 `2`。聚焦或仅发现的结果不能当作完整套件 PASS。原 Canonical Release Gate 的失败传播和 required coverage 未放宽。

## 精确路由与来源

`ci/runtime-contract-test-matrix.json` 显式登记所有模块、LF-normalized SHA-256、默认 PORTABLE 和类/方法级例外。源码 identity 漂移、新增/漏登记模块、空/重复/未知方法、例外重叠或未命中均失败关闭。执行进程再次核对完整 discovery IDs，防止导入时动态方法变化。矩阵不是自动根据失败结果重新分类的工具。

| 路由 | 本轮执行和责任 |
|---|---|
| PORTABLE | 保留原方法和断言，独立进程真实执行；实际 FAIL/ERROR 不降级 |
| WINDOWS_NATIVE | 明确 Windows 环境或 junction 前提；不模拟 OS，不新增 Windows CI job |
| DEDICATED_RUNNER | RPF73R2 受信进程收据，或写死历史 task owner 的 fixture；不访问旧根、不伪造/移植收据 |
| LEGACY_SDK_PRECONDITION | 固定 SDK/旧 venv/JAR/launcher 输入和执行；本轮不安装、不运行、不读取旧私有输入 |
| FROZEN_PRIVATE_ARTIFACT | 私有冻结 RPF78 输入，或测试会读取旧私有路径；不复制/生成替代数据 |

所有路由均 `required=true`。未满足的方法登记 UNAVAILABLE，必须由后续授权解决，不能计为 PASS 或取消原覆盖责任。纯 ABI/内存方法仍保留 portable；类级例外只用于该类真实公共 setup 本身要求前提的情形。

新增 Router 的文件/回环/进程 guard 用于暴露本轮测试越界，违规按真实 ERROR 传播；它不是操作系统沙箱，也不构成 Provider 执行或生产授权。仅标准库测试控制进程和源码审查后的 localhost fixture 获授权。日志只在 ignored 任务目录内保留；公开 ledger 不含 raw traceback 或宿主路径。

## 证据边界

固定 Base 为 `531338ad88e9ba8e6d4d4b271b10fbe7d161d46e`，原失败 Run 为 `40920947296`。完整真实发现有 1232 个方法；旧 CI 的 1118 testsRun 不包括 114 个被类级 setup 错误/skip 挡住的方法（RPF67 27、RPF68 15、RPF78 frozen 67、Docker 2、RPF05 3）。这不是新增/删除测试。

G0 Attempt-01 收据 INVALID，永久保留；Attempt-02 单独先检查、stdout 输出，再 exclusive-create/flush/fsync 收据，随后创建授权私有根。Windows 标准库目录 fsync 不可用，文件 fsync 实际完成。最终运行、质量门和未完成项以本目录 RESULT/diagnostics 为准；最终 Git/hosted CI 回执在交付聊天独立补证，不 amend 已封存报告。

两项独立路径 basename/stdlib 断言及 Runtime 实现原样保留，Linux 结论不从 Windows 测试推导。RPF74 PAUSED、RPF81/rev2 BLOCKED 和 RPF78/rev1 A08 FAIL 不变；本修订不恢复旧实验、不读取私有 WAL、不调用 Provider/真实 SDK、不部署。
