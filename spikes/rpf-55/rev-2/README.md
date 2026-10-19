# RPF-55 rev-2｜冷进程修复与三场景 Witness

本轮完成三个新鲜 Java/H2 场景：normal、planned-but-inhibited、local-delivery-suppressed。Target 是真实 Pydantic AI SDK 2.57.0/OpenAI SDK 3.35.1 加固定 Fixture；Provider/tokens/费用均为0。三个场景各自使用全新 Runner、SDK、JVM、Run ID与namespace，没有拼接rev-1观察。

- [中文主结果](RESULT.md)：身份、验收、运行及交付事实。
- [三场景摘要](experiment-summary.json)：Run/PID/合同/故障/预算和清理。
- [正式新 Witness](config-experiment-evidence.json)：`rpf55-config-experiment-evidence-v2`。
- [离线验证记录](offline-verification.json)：外部锚、七类重新锚定篡改、执行与验证器身份、纯离线导出修复。

## 只读核验

```powershell
python -B -m unittest runtime.tests.test_effectwitness_config_experiment -v
python -B -m runtime.runproof_runtime.effectwitness.config_experiment_verify spikes/rpf-55/rev-2/config-experiment-evidence.json --sha256 e5caa1a4578262132a7e779efdf481c1e9c4649cd8bbd7adfbd4c747575ca2c8
```

正确外部SHA/完整证书exit0，缺SHA exit2，错锚或非法证据exit3。重算内外摘要不能绕过false_trigger、namespace splice、duplicate POST、Authority、cleanup、SDK callback、false ACK检查。新版本拒绝rev-1合同，旧失败摘要保留原状。

## 冷进程与正式入口

当前入口 `spikes/rpf-55/probe.py` 使用新 `.local/rpf-55-rev2/`，旧根目录README/RESULT记录rev-1历史，不能为新运行授权。SDK每次从固定配置解析直接CPython3.12.13，校验exe/launcher hash、RECORD及版本，再显式Popen；不使用helper的进程内缓存，也不执行wrapper fallback。

实际运行序列为：`preflight` → 三个独立进程的 `cold-check --candidate <candidate>` → 三个独立进程的 `fixture --candidate <candidate>` → `run-controlled`。正式父进程预注册三合同后，以三个新OS进程的 `scene --candidate <candidate>` 顺序执行。`verify-offline` 仅整理已保存的候选，不启动SDK/Java。

本轮正式配额已消费3 JVM、24业务HTTP、6 POST、3 health GET；三个Tier1诊断已用完。未使用可选readiness-only JVM。**不要删除marker或再次运行受控入口。** 后续新业务运行需要新Plan和新额度。

## 故障与来源边界

normal与inhibited均正常完成4 completions、3 Tool Calls与3唯一回注，inhibited实际记录 `FAULT_INHIBITED`。suppressed在真实update HTTP200/code0/v2后扣留一次成功Tool回复，返回明确HTTP400，SDK因RuntimeError停止；只读current/history/list确认v2/[2,1]。通道为 `EXPLICIT_TOOL_DELIVERY_ERROR`，不称TCP丢包。

三场景运行时使用同一冻结执行版，源文件已在提交 `67da2e49f08687f930323af8b6b999b14dd0e0de` **事后保存**，可据证书source map核对。正式运行时HEAD仍是Plan Base。收尾仅修复了已授权离线验证记录的导出路径范围；执行哈希不改写。Verifier v2.1与导出修复源码分别记录，初始candidate/Scene/marker/ledger保留。新Verifier只额外识别这一份精确冻结执行版，不接受任意历史source替换；所有业务、故障和SDK判据保持。

原始health包含本机disk path，仅保存在ignored raw文件；公开证书是明确标注的status-only投影与原body摘要。配置GET与写端仍属于同一Java服务信任域。Issuer真实性、数据库独立Authority未建立；独立复现未测试；真实模型、Explorer、PGE闭环和WorkSwarm均未因此得到证明。
