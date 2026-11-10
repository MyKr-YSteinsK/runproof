# EffectWitness 本地受控产品

这个 Windows 可选启动配置创建一个双域虚构 SQLite 会话。确定性策略在独立读回订单事实并验证反馈后，才选择配置实验。付费真实 Explorer 已禁用，Provider 预约为零。

使用已安装且支持 SQLite 的 CPython 3.11+、Node 与现有 Vite 依赖。在仓库根目录执行：

```powershell
.\demo\start-effectwitness-product.ps1 -PythonExe <绝对-python.exe-路径> -NodeExe <绝对-node.exe-路径>
```

1. 打开 `http://127.0.0.1:4187/effectwitness/live-local`。确认虚构本地会话，然后点击**启动本地会话**。
2. 查看冻结候选、订单 **UNKNOWN_OUTCOME**、只读收据及验证反馈，再查看 **SELECT_OPS** 与配置差异。如果读回无法确认，会话进入 **RECONCILE_REQUIRED** 并停止后续写入。
3. 会话 **COMPLETED** 后下载 Witness。在同一版本 checkout 中运行离线验证器。有独立可信的 SHA-256 时传入该值。

```text
python -B -m runtime.runproof_runtime.effectwitness.product_local_verify <witness.json> --expected-sha256 <可信-sha256>
```

页面显示下载时的哈希，可用于核对传输。外部锚需通过另行可信的渠道取得。无外部锚只返回 CONTENT_CHECKED_LOCAL。外部 Issuer 与因果优势尚未建立。

刷新页面或点击**刷新只读状态**可以查询上次请求。URL 支持会话和事件书签。每个 live owner 最多接纳两个会话，每域一次写入，重启延续原预算。停止时使用进程身份回执：

```powershell
.\demo\stop-effectwitness-product.ps1
```

停止后保留任务 owner 内的 ledger 与业务数据库。重启加载原状态，中断会话进入只读对账或人工审查。4174 的静态预览使用独立的记录型交付入口。[记录型交付指南](EFFECTWITNESS_DELIVERY.zh-CN.md)

## 比赛单会话入口

在 Windows PowerShell 7.2+ 中使用同一套已安装的 CPython、Node 和 Vite 依赖。

```powershell
.\demo\start-effectwitness-competition.ps1 -PythonExe <绝对-python.exe-路径> -NodeExe <绝对-node.exe-路径>
```

启动器分配新 owner，输出 URL 和停止用的 nonce。沿用上面的浏览器确认、只读核对和 Witness 下载流程。比赛入口只接纳一个新请求，额度用尽后仍可只读查看该会话。

```powershell
.\demo\stop-effectwitness-competition.ps1 -Nonce <启动器返回的nonce>
```

停止器按 PID、可执行文件与启动时刻核对进程身份，保留账本和本地数据库。[实测结果](../spikes/rpf-112/RESULT.md) · [比赛截图与来源](../spikes/rpf-112/PPT_ASSETS.md)
