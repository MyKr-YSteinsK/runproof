# RPF-78 离线预测/拒绝实验（PARTIAL）

本版本是冻结的手工合成实验，level=OFFLINE_SYNTHETIC_FORECAST_RELIABILITY_ONLY；仅fit训练，作者已见challenge。最终106方法测试两次均因一个无效Oracle负控而失败，详见[RESULT](RESULT.md)。不能宣传通过、真实概率校准或真实Agent/业务验收。

在精确Windows source checkout执行纯读取独立CLI：

```powershell
python -X utf8 -B spikes/rpf-78/probe.py verify --file spikes/rpf-78/decision-traces.json --sha 60aab66b6b9a9bd54eb2d446c824a70f74be76c7d668244f2e8a211dfb02f219
python -X utf8 -B -m unittest discover -s runtime/tests -p test_effectwitness_pge_r78.py -v
```

首命令预期exit0；省略--sha为exit2、错误SHA为exit3。第二命令**预期exit1**：`test_negative_39`触发TEST_INVALID_NO_OP。不要把已冻结输入和函数改成能通过后覆盖本次证据。源码身份包括20个raw/LF/blob引用；不同平台换行导致raw差异应报身份不符，不能默默重签。

CLI另有generate/freeze/fit/run/negative有界入口，均为原始设计；本次任务根已有不可覆盖文件，不应重初始化重放。`negative`原始入口在index38停止；58有效子集是由任务私有操作枚举器逐项调用公开冻结`mutant(original,index)`，跳过并记录TEST_INVALID，无修改源码后再独立CLI读取。全部有效变换定义在probe.py，原始失败和续取方法在negative-controls.json，逐项PID/exit/raw/日志SHA可追溯。变体和原始日志只存任务自己的ignored `.local/rpf-78/`。

forecast-calibration-report.json是首次评价前唯一fit持久化导出的原字节；decision-traces.json和stress-shift-report.json是已独立验证的原始重放字节。evaluation-report.json汇总预测误差、全部四策略计数与逐类压力；counterexamples.json保留双向失误、低支持、负收益与旧77只读诊断索引。source-identity-map.json记录冻结、源码提交和独立读回；verification/runtime JSON保存真实失败与资源账本。报告封存A10=NOT_RUN，最终聊天补实际交付SHA，不amend回填。

RPF-74 PAUSED；不含Provider/SDK/真实业务/Authority/生产/merge/deploy权限。下一步建议由Architect决定新修订，先纠正no-op测试选点并在freeze前验证所有变体，不更改本轮失败证据。
