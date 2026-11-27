# RPF-125 rev-1 · 调查读回失败与 Witness 下载

2026-11-27。在修订前后对同一个合成会话做了 Windows 浏览器对照。基线的调查 GET 失败会禁用 Witness。候选保留会话、时间线和执行时读回，显示独立调查暂不可用。原 Witness 可从独立接口下载，原 CLI 复核通过。[任务正文](https://github.com/MyKr-YSteinsK/runproof/issues/11)

## A01 · 先复现，再核对同一会话

开工时本地与远端 `main` 同为 `b5a5f0e19255352c83da6b7ccfa651828355a900`。基线使用该提交的仓库版启动器。候选修改后按原 nonce 只读重开。在 Windows x64 build 26200 使用 PowerShell 7.6.9、Edge 158.0.4370.33 无头浏览器、Node 24.16.0 和 CPython 3.14.6。用 Edge DevTools 拦截本次浏览器的 `GET /investigation/<id>`，只对该路由注入故障。[原启动器](../../demo/competition-bundle/start.ps1)

| 调查 GET | 基线 | 候选 |
| --- | --- | --- |
| 404 | 显示 `IDENTITY_NOT_FOUND`，Witness 按钮禁用。 | 会话仍为 `COMPLETED`，显示调查证据暂不可用 `GATEWAY_404`。Witness 按钮可用。 |
| 503 | 显示 `READBACK_UNAVAILABLE`，Witness 按钮禁用。 | 同一会话及 12 个可见时间线事件仍在。显示 `GATEWAY_503`，Witness 按钮可用。 |
| 200 | 健康路径可看到本次独立调查。 | 清除注入后点击刷新只读结果，正确报告恢复，仍选中 #7 的 Authority 读回。 |

基线按钮禁用时，独立 `GET /witness/<id>` 返回 200。候选在调查 404 时点击下载，浏览器实际保存 17,192 字节。响应长度、SHA-256、owner、session 和 request 均与原材料一致。原 CLI 退出 0，得到 `CONTENT_CHECKED_LOCAL`、签发者 `NOT_ESTABLISHED`，SHA-256 为 `672c8443fee78c2f1e9885aca8f04789a97ccb4a723277537708e6932ed3b22a`。复核使用当前仓库版本且未提供独立摘要。

## A02 · 拒绝错配与迟到响应

- Vitest 的未完成会话经 `GET /request/<id>` 找回为 `RUNNING`。调查 503 时导出不可用，Witness 请求在发出前被拒绝，起跑许可保持关闭。下一次 GET 取到正确报告，完成结论仍为 `NOT_ESTABLISHED`，导出类型为调查报告。
- 真正查无记录的会话 GET 404 才显示 `IDENTITY_NOT_FOUND`。Vitest 覆盖 capability 404、模式差异、owner、session 和 request 错配。错配分支未请求调查报告。
- 浏览器把旧报告替换为摘要错误的响应时，显示 `WITNESS_HASH_MISMATCH`。把嵌入的 request 改成另一值并重算传输摘要时，显示 `EVIDENCE_IDENTITY`。两次都清除报告，仅保留当前会话及独立的 Witness 入口。Vitest 也拒绝未完成报告宣称完成，以及长度、摘要或身份错误的 Witness。
- 暂停一次旧调查 GET，切换到不存在的会话并等它返回 404，再放行旧报告 200。页面保持新会话的缺失提示，无旧报告或导出入口。刷新读到新有效报告后再放行上一次调查的 503，新报告和按钮保持可用。Vitest 的两项迟到回归将旧 200/503 放在另一个有效会话之后，均未发布旧结果。

## A03 · 请求、同一现场与清理

启动 nonce 为 `ee9e8c13d8b14ccfb9dbfc707323b283`，capability 实例为 `fe329dbd48a344d989d3895565670d53`，session 为 `737e112ea9424cc1819b3b33330396af`，request 为 `09a5fbed-b2ab-40d7-94ee-58a81e7de8b0`。基线在浏览器勾选确认并点击起跑一次，单个 `POST /session` 返回 200。随后都是只读刷新或用原 nonce 重开。

| 浏览器记录 | API GET | 调查 GET | Witness GET | `POST /session` |
| --- | ---: | ---: | ---: | ---: |
| 首次预检 | 2 | 0 | 0 | 0 |
| 基线复现 | 14 | 3 | 1 | 1 |
| 候选取证与迟到补查 | 45 | 14 | 1 | 0 |
| 最终候选 | 35 | 11 | 1 | 0 |
| 合计 | 96 | 28 | 3 | 1 |

首次取证预检把启动 nonce 当作 capability 实例，在起跑前退出。修正后用实际实例确认一次。候选第一次取证等待 503 错误体下载结束而超时，按实际响应状态补查迟到错误。最终候选一次跑完全部浏览器检查。回环服务从未收到注入的错误体，故障仅在该次浏览器的调查 GET 上产生。

用 `mode=ro` 和 `PRAGMA query_only=ON` 读取同一 owner 的 `ledger.sqlite`、`order.sqlite` 和 `ops.sqlite`。仍只有一个请求、一项会话预约、17 个执行事件。订单和配置分别只有一条已提交收据，revision 均为 1，退款为 2500 分。业务库和账本等 6 个文件的摘要、大小、修改时间在基线停机至最终只读停机间逐项一致。除了起跑时获准的两域操作，新增业务写入为 0。真实 Provider 预约、发送和 token 均为 0。按 nonce 和原进程回执停机，4187/8780 均无监听，证据保留。

本机证据根为 `.local/rpf-125/9e6763d23d/`。浏览器脚本、请求及页面回执为 `browser.mjs`、`baseline-repro.json`、`candidate-final.json`，原件前后清单为 `owner-before.json` 和 `owner-final.json`。最终下载实际位于 `candidate-final-download/`，其独立 CLI 输出见 `candidate-final-witness-verification.json`。浏览器回执中的下载相对路径标签沿用了首次候选目录名，以实际下载目录与 CLI 摘要为准。

在仓库根用已核实的可执行文件复跑。基线点击确认一次。修改前停机，候选用同一 nonce 重开。将 `$file` 设为实际保存的 Witness 路径。

```powershell
.\demo\competition-bundle\start.ps1 -PythonExe $py -NodeExe $node
.\demo\competition-bundle\stop.ps1 -Nonce $nonce
.\demo\competition-bundle\start.ps1 -PythonExe $py -NodeExe $node -Reopen $nonce
& $py -B -m runtime.runproof_runtime.effectwitness.competition_agent_verify $file
.\demo\competition-bundle\stop.ps1 -Nonce $nonce
```

## A04 · 回归与交付身份

| 检查 | 实测 |
| --- | --- |
| `npm test` | 退出 0，20 个测试文件、87 项通过，新增 9 项聚焦场景。 |
| `npm run build -- --outDir .local/rpf-125/9e6763d23d/final-web-build` | 退出 0，包含 TypeScript 检查。Vite 保留大 chunk 提示。 |
| `& $py -I -B ci/verify-public-docs.py` | 退出 0，`PUBLIC_DOCS_PASS files=18 pairs=7`。 |
| `git diff --check` | 退出 0，含提交前暂存差异检查。 |

本地覆盖限当前 Reference Agent 页和同一合成 owner。真实 Provider、其他产品入口的浏览器实跑和移动设备验收未运行。Controller、Authority、Verifier、证据格式和 Canonical 工作流沿用原源码。候选浏览器实测的页面及 API Git blob 分别为 `700868a3c09d0bb8e7ef3476b87721c2f59da81a` 和 `105ecf4fbe8da0fa27f4deb6532667acec579c1c`，提交前核对了相同字节。用 `git log -1 --format=%H -- spikes/rpf-125/RESULT.md` 定位交付提交。产品 CI 与 Canonical Gate 各按实际 checkout 核对。
