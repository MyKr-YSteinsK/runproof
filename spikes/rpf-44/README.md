# RPF-44｜跨域 Witness 核心

本轮采用方案 B：`CONTROLLED_OPS_LOCAL_SIMULATION`。SQLite 真正持久提交虚构 release/config 与 operation receipt；独立只读连接读回，纯函数 oracle 判断业务效果。`RPF28_DOCKER_INTEGRATION_NOT_PROVEN`。

## 离线核验已提交样本

从仓库根目录执行；只需 Python 标准库，不需要数据库、Docker、Provider 或凭据。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m runtime.runproof_runtime.effectwitness.witness_verify spikes/rpf-44/sample-ops-witness.json --expected-sha256 21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873
python -m runtime.runproof_runtime.effectwitness.witness_verify spikes/rpf-43/sample-witness.json --expected-sha256 ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e
```

锚定成功 exit `0`；省略独立可信 SHA 时 `UNANCHORED_INCONCLUSIVE` / exit `2`；错误锚或不合法内容 `REJECTED` / exit `3`。锚应来自独立可信 Git/产物记录，不能采信待验文件的自报值。本文所列 SHA 仅在本文所在提交也可信时构成锚来源。两版均为 unsigned，`issuer_authenticity=NOT_ESTABLISHED`。

## 共享与领域边界

| 分类 | 模块 / 入口 |
| --- | --- |
| SHARED_CORE | `engine.Budget/Orchestrator`：统一预算、派发、UNKNOWN 阻断及 reconcile ports |
| SHARED_CORE | `cross_contracts.CrossContracts`：不可变 canonical bytes；新 Execution/Experiment schema |
| SHARED_CORE | `cross_trial.run_trial`：两域同一捕获、事件、反馈与清理流程 |
| SHARED_CORE | `witness_verify.verify_bytes/verify_file/main`：大小、canonical JSON、duplicate keys、可信外部锚及版本分发；既有事件/故障基础校验复用 |
| SHARED_CORE | `cross_core.validate_bundle/validate_contracts/validate_snapshot/project_feedback`：固定域注册、身份、摘要、来源、事件引用、四轴与白名单反馈 |
| ORDER_DOMAIN | `orders.OrderSandbox/AuthorityReader/OrderAdapter`；`effect_oracle.evaluate_order_effect` |
| OPS_DOMAIN | `ops.OpsSandbox/OpsAuthorityReader/OpsAdapter`；`ops_oracle.evaluate_ops_effect` |

静态注册仅支持 `order` / `ops` 与 oracle `1`。JSON 无法指定 import、类名、路径、命令或 endpoint。新 Witness `rpf-effect-witness-v2` 使用 `rpf-cross-execution-v1`、`rpf-cross-experiment-v1/owner=rpf-44`；Ops Effect 为 `rpf-ops-effect-v1`。旧 `FrozenContracts` v1/v2/v3 的 owner/字段规则未放宽；旧 Witness v1 保留原严格验证路径和原样本字节。

当前 v2 可离线接受的捕获轮廓是 response-lost + 完整 reconcile 的九事件证书；normal / planned-not-triggered 是运行及测试覆盖，不伪称已触发故障。反馈复算不构成运维真实 LLM PGE L2。

## 确定性测试

先把所有临时输出限制在本任务目录；不安装依赖。

```powershell
New-Item -ItemType Directory -Force .local/rpf-44/tmp
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=(Resolve-Path .local/rpf-44/tmp).Path
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
python -m unittest runtime.tests.test_effectwitness_ops runtime.tests.test_effectwitness_witness runtime.tests.test_effectwitness_pilot runtime.tests.test_effectwitness_pge -v
python -m unittest discover -s runtime/tests -t . -p 'test_*.py' -v
```

旧三组测试仅改变夹具根目录，重定向到 `.local/rpf-44/compat-runtime/**`，不读写旧 `.local/rpf-40/41/42/43`。`test_effectwitness_ops` 的离线子进程禁止数据库、socket、Docker、Provider、执行器导入，并对真实两域夹具及历史样本验证 `0/2/3`。

## 有状态入口与限制

`python -m runtime.runproof_runtime.effectwitness.cross_trial --domain order` 创建 fresh trial，只输出摘要、不保留订单证书。`--domain ops --output spikes/rpf-44/sample-ops-witness.json` 仅允许该精确输出且文件必须不存在；已交付样本禁止覆盖，不应为展示重复运行。

CLI 在 `.local/rpf-44/trial-budget.json` 先持久预留，失败也耗额度：最多 3 次 / 45 分钟；每次共享预算最多 8 步 / 900 秒，Provider 请求/Token/费用均为 0。当前 CLI 只面向单执行器串行受控实验，不具备并发调度/并发账本保证。试验异常时保留 DB 到 `.local/quarantine/rpf-44/<run-id>`；成功时先冻结 authority 证据，再 reset/readback、删除精确 SQLite 文件并移除本次目录。

验收、实际身份、摘要及后续边界见 [RESULT.md](RESULT.md)。本分支未合并 main；Web/API Lab、真实运维 LLM PGE、Docker 正式对接与 PKI 均未在本轮实现。
