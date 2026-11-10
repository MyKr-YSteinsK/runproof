# RPF-107 SDK Explorer Host Bridge

RPF-107 把固定 SDK 的 `select_experiment(candidate_id)` 回调接到 RPF-106 Controller。模型可见数据限于已验证的 seed 摘要、候选枚举和剩余预算。Host 校验真实工具调用 ID 和参数，再从自身当前账本生成 proposal 与 decision。候选包括订单退款、配置变更和显式停止。

物理路径使用一个绑定 `127.0.0.1` 的 Host 服务。续轮提交后，Host 先持久记录 UNKNOWN，再只读对账并返回 UNKNOWN。若 SDK 随后发出新的模型 POST，Host 会保留入站应用字节并返回 409。拒绝发生在新模型预约之前，模型端点无出站转发路径。任务自有原始证据留在各自 owner；公开 ZIP 仅可由独立只读验证生成。

## 离线验证

在仓库根用已核验的 Python 运行。下面的测试会新建隔离 SQLite owner，HTTP 请求体由测试构造并直接传给 Host。

```bash
git check-ignore -q -- .local/rpf-106/probe
git check-ignore -q -- .local/rpf-107/probe
RPF106_LOCAL_SQLITE=1 RPF107_LOCAL_SQLITE=1 python -B -m unittest -v ci.test_rpf107_contracts ci.test_rpf107_host ci.test_rpf107_oracle ci.test_rpf106_candidates ci.test_rpf106_controller
python -B ci/verify-public-docs.py
```

Hosted 物理入口仅支持经人工审批的 `workflow_dispatch`。先由维护者确认 `rpf-107-physical` 的 Required Reviewers、冻结 `main` 源码，再建立首次 Run，绑定当次 SHA 和 Run ID 后审批。物理运行使用脚本响应和固定 SDK。真实 Provider 和自主 Explorer 属于独立验收。

[封存结果](RESULT.md) · [验收记录](acceptance.json) · [验证诊断](verification-diagnostic.json) · [源码映射](source-map.json)
