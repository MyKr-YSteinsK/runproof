# 离线校验与只读观摩

这里“可复核”指检查已发布文件与限定语义，**不等于独立重现模型/业务实验**。本次实际使用已安装CPython 3.14.6，4个原Verifier CLI均exit0，未调用Provider、SDK或Java。无需读旧运行目录、API Key或服务端token。

## 1. 取得准确功能快照

在用户选择的工作位置自行克隆已有公开仓库（本次任务没有另做clone）：

```powershell
git clone https://github.com/MyKr-YSteinsK/runproof.git runproof-review
Set-Location runproof-review
git checkout --detach 1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8
git rev-parse HEAD
$env:PYTHONDONTWRITEBYTECODE='1'
python --version
```

应读到上方完整SHA；不要checkout main后假定包含本功能。离线CLI只读跟踪源码/证书，使用现有Python标准库；依赖或解释器不足时报告UNAVAILABLE，不安装/更换旧冻结SDK。RPF60运行时SDK/Java依赖不属于离线检查前提。

## 2. 外部锚与原Verifier

从仓库根分别执行，4个模块与参数名已实际核对：

```powershell
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.config_pge_coverage_verify spikes/rpf-57/config-pge-coverage-evidence.json --sha256 76dd7077d75e6dd8ad319bb6e17a01209faadee9fe94d276f3b85e73e88abbe7
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_shared_verify spikes/rpf-58/rev-2/cross-domain-portability-evidence.json --sha256 03aa9ac84f725de982b537a8882b27b764aaf6da9868b9a65a2cdcfd6e4d208d
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.pge_select_verify spikes/rpf-59/cross-domain-selection-evidence.json --sha256 0bb359ca78c7c0415afef30ff959d41112da3f5155e5ae18e68be28735f9996a
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.lab_cross_domain_verify spikes/rpf-60/cross-domain-live-evidence.json --sha256 81422d26a6ea1406d66d73fecfe0a98a09310a81812faf84e95ed896679b8df9
```

4份原件HTTP公开读取均200，完整字节数/VerifierSHA在Manifest。当前正确锚exit0；CLI定义为缺外部锚exit2、错误/无效证据exit3。0/2/3及语义tamper矩阵在RPF60历史诊断已执行，本次不把历史负控写成新运行。

可另用 `Get-FileHash -Algorithm SHA256 -LiteralPath <原件路径>` 检查同一原始文件；不要另存JSON后重新格式化，raw锚按原字节计算。

## 3. 生成已有REVIEWED投影（没有服务器或业务）

```powershell
python -X utf8 -B -c "import json; from runtime.runproof_runtime.effectwitness.lab_cross_domain_projection import reviewed; p=reviewed(); print(json.dumps({'source':p['source'],'session_id':p['session_id'],'status':p['status'],'witness':p['witness']},ensure_ascii=False))"
```

此函数从固定RPF59原件开始，经原Verifier后构造投影；本次实际PASS，source=REVIEWED。它不构造CrossDomainStore、不启动Gateway、不创建Session、不执行模型/业务、不读取旧local账本。RPF59与RPF60页面不共用Session。

## 4. 本机页面与不可用退路

- 已配置并获授权的既有本地只读观摩环境中，`/effectwitness/cross-domain/reviewed`显示固定RPF59 REVIEWED投影；Gateway不可用应明确UNAVAILABLE。**本Plan没有启动旧Gateway**：原CLI会创建旧task存储，且无新任务root参数；不为观摩重开付费模式或改存储根绕过额度。
- 新checkout只有文件，不会包含旧Live状态。RPF60 Session详情URL也不会自动凭公开Witness重建LIVE服务；使用本包截图和公开Witness审查。
- 不具备Gateway时，可用本包PNG+离线CLI说明当前能力；RPF46原`/effectwitness/recorded`是更早的独立静态录制页，不冒充RPF59/60。
- 如本机已有Web依赖，以下只启动现有Vite（不启用代理和任何Gateway）。命令可用性由固定config/CLI源码检查支持；**本次未启动Vite或运行浏览器本地QA**。

```powershell
$env:RPF_EW_LAB_ENABLED='0'
$env:RPF_EW_LAB_TASK_OUTPUT='0'
$env:VITE_CONTROL_PLANE_DATA_SOURCE='api'
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4185 --strictPort --configLoader runner --cacheDir .local/rpf-61/vite-cache
```

先确认4185未占用；否则停止，不终止别人的服务。打开 `http://127.0.0.1:4185/effectwitness/recorded` 查看静态RPF46；打开 `/effectwitness/cross-domain/reviewed`会在缺Gateway时准确降级。既有canonical页面仍为API-backed读取，不用fixture兜底。完成后Ctrl+C关闭。没有node_modules时该步骤UNAVAILABLE，不在本任务安装依赖。

原功能启动说明见 [RPF60 README](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/README.md)，它描述已耗尽quota的历史Gate，本包不授权重跑metadata/cold/live或重置marker/WAL。不要执行demo/fixture/controlled-run/probe或退款/POST。当前截图中的LIVE仅为历史实际运行时标记。
