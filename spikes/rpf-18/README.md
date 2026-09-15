# RPF-18 Statistical Evaluation 与 Flaky Reliability Gate

RPF-18 在既有 deterministic Evaluation/Quality corpus 旁新增三份统计合同：

- `rpf-statistical-sampling-plan-v1`
- `rpf-statistical-evaluation-v1`
- `rpf-statistical-comparison-v1`

统计合同只消费 immutable Run Evidence 与 RPF-17 Failure Intelligence ref，不修改 RPF-07/RPF-08/RPF-16/RPF-17 历史 artifact。Agent denominator 只包含 `AGENT_PASS + AGENT_FAIL`；Platform/Environment、Invalid、Inconclusive、Cancelled 仍在 attempted/evidence denominator 与 trial matrix 中可见。区间方法固定为 95% Wilson score (`wilson-score-v1`)。`OBSERVED_FLAKY` 是受控语料观察，不是 live failure probability。

## 本地命令

```powershell
python -m unittest discover -s runtime/tests -p 'test_*.py' -v
python spikes/rpf-18/probe.py --build-reviewed --refresh-reviewed
python spikes/rpf-18/probe.py --verify
python spikes/rpf-18/probe.py --run
python spikes/rpf-18/verify-evidence.py
```

`--build-reviewed --refresh-reviewed` 是源码变更后的显式刷新动作；固定样本不会被普通 `--verify` 或运行时自动覆盖。`--run` 创建带 `rpf18` 前缀的临时 PostgreSQL、Control Plane、durable worker 进程与 artifact store，结束时验证 cleanup。

受控 cohort 的结果为：Stable `20/20`、Baseline `10/20`、Flaky `17/20`、Safety `19/20` 但有 zero-tolerance event、Evidence-poor `8/20` 有效且含 Environment/Invalid excluded trials。Stable、Flaky、Safety、Evidence-poor 的 Statistical Decision 分别为 `ELIGIBLE`、`REVIEW_REQUIRED`、`BLOCKED`、`INCONCLUSIVE`；Baseline 通过独立 comparison 参与 `IMPROVED` 判断。固定 reviewed Decision 只表达 decision-only 结果，不执行 release/deploy。

本 probe 不调用 DeepSeek，不创建 broker/scheduler/HA，不引入新数据库表，也不连接真实 Production destructive credentials。
