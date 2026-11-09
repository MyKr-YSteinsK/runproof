# EffectWitness 记录型演示

将 ZIP 解压到新目录，在该目录用 Node.js 校验清单并启动预览：

```powershell
node .\effectwitness-preview.cjs verify
node .\effectwitness-preview.cjs
```

打开 `http://127.0.0.1:4174/effectwitness/workbench`。服务在前台运行，按 Ctrl+C 退出。若端口占用，确认其他回环端口空闲后可运行 `node .\effectwitness-preview.cjs serve . 4175`，并把地址端口改为 4175。解压前对照旁路回执检查 ZIP SHA-256。清单记录构建提交和成员哈希，交接时请通过可信渠道取得回执。

## 三分钟演示

1. **0:00–0:40** 选择**订单与退款**，依次核对预期、禁止和未知结果合同。写入结果未知时，先做只读对账。
2. **0:40–1:45** 进入**调查已记录的事实**。打开事件查看上下文，再点**返回工作台**。URL 保留场景与事件。查看反馈链和状态差异，也可切换语言后刷新查看同一事件。
3. **1:45–2:50** 打开**核对 Witness 与边界**，切到**运维配置**。该域展示单独的历史 Witness，同会话时间线与状态差异缺失。点击**查看来源与离线复核**检查历史材料。工作台分别标注记录证据、受控本机和实时 Provider 的可用级别。

如果深链事件找不到，使用 `?domain=order` 打开工作台，从已验证列表重新选择。如果源校验失败，界面显示 UNAVAILABLE，可使用固定提交和下列 CLI 排查。

## 从仓库构建并核查

使用现有 Node/npm 和锁文件依赖，在没有 Vite 环境文件的 checkout 中构建已提交版本。在仓库根目录的 PowerShell 中执行：

```powershell
.\demo\effectwitness-delivery.ps1 Build
.\demo\effectwitness-delivery.ps1 Package -RunRoot <RunRoot>
.\demo\effectwitness-delivery.ps1 Verify -BundleRoot <独立解压目录>
.\demo\effectwitness-delivery.ps1 Preview -BundleRoot <独立解压目录>
```

替换为 Build 输出的路径，必要时以 `-NodeExe` 指定已核实的绝对路径。Verify 短暂绑定回环端口执行 HTTP 核查，完成后释放端口。

可选证据 CLI 在仓库内运行，需要已核实的 Python 解释器：

```text
python -B spikes/rpf-47/verify_evidence.py --root .
python -B -m runtime.runproof_runtime.effectwitness.witness_verify spikes/rpf-43/sample-witness.json --expected-sha256 ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e
python -B -m runtime.runproof_runtime.effectwitness.witness_verify spikes/rpf-44/sample-ops-witness.json --expected-sha256 21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873
```

该包只展示历史记录。订单研究摘要与两份 Witness 样本拥有各自的历史身份，签发者身份仍未建立。新 Explorer 会话、跨域权威状态、发布资格和赛事提交均不在本演示范围内。
