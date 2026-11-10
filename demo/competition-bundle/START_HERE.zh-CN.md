# EffectWitness 比赛演示

本包预编译了 Web 界面。运行需要 Windows PowerShell 7.2+、Node 22+ 和带 SQLite 的 CPython 3.11+。先用另行收到的 ZIP SHA-256 核对压缩包，再解压到一个全新的目录。在解压根的 PowerShell 中执行，替换两项绝对路径：

```powershell
.\start.ps1 -PythonExe <python.exe绝对路径> -NodeExe <node.exe绝对路径>
```

1. 打开启动器返回的本机链接。浏览器勾选一次性确认框，然后点击启动。启动器另行输出停止用的 nonce。
2. 检查订单的 `UNKNOWN_OUTCOME`、SQLite 只读收据、已验证反馈与 `SELECT_OPS`，再检查配置状态差异。进入 `RECONCILE_REQUIRED` 时仅使用只读刷新。
3. 完成后下载 Witness。另行取得可信 SHA-256 时传入；省略该参数仅执行本地内容验证。

```powershell
.\verify-witness.ps1 -PythonExe <python.exe绝对路径> -Witness <已下载文件路径> -ExpectedSha256 <独立取得的SHA-256>
.\stop.ps1 -Nonce <启动器返回的nonce>
```

每次解压只接受一次启动和一个新会话，业务库与进程收据保存在解压目录自己的 `.local`。两个服务仅监听 127.0.0.1 的 4187 和 8780，端口冲突时启动会停止。浏览器刷新和会话深链仍可只读打开已完成结果。

演示使用虚构订单和配置、真实本地 SQLite 与确定性规则策略。Provider 调用为零。离线验证建立内容和摘要绑定，外部签发者身份及发布资格未建立。
