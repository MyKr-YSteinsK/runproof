# RPF-51 rev-4：真实 JDK 就绪复验与 HTTP Witness

## 目标与边界

本轮在独立 task-local 根中复用已校验的 config-center 源码副本与 JAR，先用直连 JDK 可执行文件完成只读 health 诊断，再执行一次受控的 HTTP 业务 Scenario。旧 rev-1、rev-2、rev-3 的运行状态与证据保持冻结。

- RunProof 基线：`1c4c3a382808a98613b1e659dfcddbc1d5ebc67e`
- 分支：`codex/rpf-51-rev4-real-jdk-http-effect`
- 外部只读来源：`MyKr-YSteinsK/config-center@0258b9cef02ea74a40989d035c79256c776409c0`
- Java：17.0.12；启动器解析到的直接 JDK：`C:\Program Files\Java\jdk-17\bin\java.exe`
- Scenario：仅 `127.0.0.1`、`local` profile、内存 H2；最多 12 个业务 HTTP 请求；Provider、tokens 与费用预算均为 0。

## 受限执行顺序

每次诊断使用单独的 attempt 目录、端口和 marker。只允许最多 2 次只读 readiness 启动；第 2 次必须由第 1 次安全停止的特定 Harness 故障及代码修复证明其必要性。一次诊断 PASS 后停止诊断，不再启动第二次。

```powershell
python -B spikes/rpf-51/probe.py --prepare-diagnostic --attempt 1
python -B spikes/rpf-51/probe.py --diagnose --attempt 1
python -B spikes/rpf-51/probe.py --prepare-scenario
python -B spikes/rpf-51/probe.py --run-scenario
```

业务 Scenario 只能在 `readiness-diagnostic.json` 选择出完整 PASS 后准备。启动后不可重试或重置；不确定的 POST 结果只能用只读 GET/history 对账。

## 离线 Witness 验证

本轮生成真实 HTTP Witness 后，用独立 Python 进程和从报告/外部记录取得的完整 SHA 验证：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.config_http_witness spikes/rpf-51/rev-4/config-http-witness.json --expected-sha256 c569bd62a6691c84e8995359578fc4ff34f0ea417158a0c0893309c029df363d
```

正确锚、缺失锚、错误锚的退出码分别为 `0 / 2 / 3`。Witness 证明本轮受控 HTTP 服务中的观察结果和确定性 Oracle，不建立签发者真实性或数据库级独立权威；Target Agent 未执行。

## 本轮结果

完整 Gate、实际诊断、HTTP 观察、Witness 与验证结果见 [RESULT.md](RESULT.md)。
