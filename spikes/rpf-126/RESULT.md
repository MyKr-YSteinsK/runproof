# RPF-126 rev-1 · 当前离线交付验收

2026-11-27。固定候选 `bc8f72438677dee69b905a3ffbfe27894bc17d06` 通过 Windows 源码冷启动、故障调查、同会话只读重开和完整工程包验收。源码与解包应用各确认一次独立的合成会话，真实 Provider 预约、发送和 token 均为 0。实测无启动、证据、恢复或交接阻塞。本轮交付验收记录，留待阶段验收。[任务正文](https://github.com/MyKr-YSteinsK/runproof/issues/12)

## A01 · 从干净源码检出启动

开工时本地和远端 `main` 都是该候选。在 `.local/rpf-126/c6ec65f9/src/` 新建 detached 检出，耗时 2.229 秒。初始 Git 状态为空，无 `.local`、`node_modules`、`dist` 或环境配置文件。使用 Windows x64 build 26200、NTFS、PowerShell 7.6.9、Git for Windows 2.54.0、Node 24.16.0、npm 11.13.0、CPython 3.14.6、SQLite 3.50.4 和 Edge 158.0.4370.33 无头浏览器。仅使用已经核对的可执行文件。

先完成依赖准备。`npm ci --offline` 从本机 npm 缓存按锁文件装入 89 个包，退出 0，耗时 8.972 秒。`package-lock.json` SHA-256 为 `4780c717117d195edf51c4763a9bcc7f2ea3e50a29b55b8ab0dd6e15eae8044f`。依赖安装完成后，从该检出按 README 和 Runbook 命令启动，6.317 秒就绪，退出 0。应用监听本机回环 4187 和 8780。[中文 README](../../README.zh-CN.md) · [运行手册](../../docs/项目源文件/RUNBOOK.md#本地-reference-agent)

实际命令如下。`$proof` 为本轮隔离根，`$py` 和 `$node` 为已核实的绝对路径，其余变量来自本次回执。源码命令在新检出根执行。运行开始时只在浏览器勾选并确认一次。

```powershell
npm ci --offline --no-audit --no-fund --logs-dir (Join-Path $proof 'npm-logs')
.\demo\competition-bundle\start.ps1 -PythonExe $py -NodeExe $node
.\demo\competition-bundle\stop.ps1 -Nonce $sourceNonce
.\demo\competition-bundle\start.ps1 -PythonExe $py -NodeExe $node -Reopen $sourceNonce
& $py -B -m runtime.runproof_runtime.effectwitness.competition_agent_verify $sourceWitness
.\demo\competition-bundle\stop.ps1 -Nonce $sourceNonce
```

## A02 · 同一会话的故障、业务读回和恢复

启动 nonce 为 `f9119e50d78b4187831723025e726e4d`，capability 实例为 `eeaa4e94842d42c68f2b5d1b4ba55fa9`，session 为 `8e0d5f76317348f3bc0426157bb94acb`，request 为 `4277ea36-fa5f-4eda-9240-4ae885dcfde1`。实际 `POST /session` 一次，HTTP 200。会话记录为 `COMPLETED`，页面显示 12 个关键时间线事件，底层记录 17 个事件。

订单 `refund_order` 意图 #3 经 Controller 在 #4 批准。持久写入意图 #5 后，工具在 #6 返回 `UNKNOWN_OUTCOME`。#7 Authority 读回该 operation `8e0d5f76317348f3bc0426157bb94acb-order`，仅有收据 `receipt-46a23f0f6ea3a83a717910e7`，状态 `COMMITTED`，退款 2500 分，订单 revision 1。#8 反馈 SHA-256 为 `5bc09559e30590d25c01d82f0b9da2fc4e450bcdedf936a18f7c4d16ebac36ca`。#11 的 `apply_config` 使用相同输入反馈摘要，#12 单独批准配置操作。该域也仅有一条收据 `receipt-dd11584a5a18cb28082007c1`，状态 `APPLIED`，revision 1。

按回执停止后用原 nonce 只读重开，6.201 秒就绪，退出 0。浏览器打开原 session 的 #7，在本次调查 GET 上注入一次 503。页面保留会话和已记录的读回，提示 `GATEWAY_503`，Witness GET 仍返回 200。刷新读回得到原报告，`content_sha256` 为 `2c79912a1b1843ef18e8e5b93b8b35f83adf33d0ce08a1bee849c1deca0e0806`。用原 CLI 复核重开后实际下载的 Witness，退出 0 并返回 `CONTENT_CHECKED_LOCAL` 和 `NOT_ESTABLISHED`。重开前后的 Witness 都是 17,192 字节，SHA-256 均为 `4437043fd2741394180dbb0a792e5921bb4918961cc8a77f19df3cacd02a490d`。

对三份 SQLite 使用 `mode=ro` 和 `PRAGMA query_only=ON` 分别回查账本、订单和配置。仍只有原 request、两域原 operation 和各自一条收据。只读重开新增 POST 和业务写入均为 0，owner 内 6 个文件摘要、大小和修改时间逐项一致。按原 nonce 回执停机。

## A03 · 完整工程包与独立验真

从 A01 的同一 Git 提交用当前 `--complete` 入口生成候选 ZIP。构建退出 0，含 TypeScript 与 Vite 生产构建，用时 53.933 秒。用仓库已有的独立验证器解到新目录，退出 0，用时 5.425 秒。验证器逐个核对路径、字节数和摘要，以及内外层 `site` manifest 和 `app/source` 的 Runtime 字节。[打包入口](../../demo/competition-bundle/build-bundle.mjs) · [独立解包验证](../../ci/test_rpf114_competition_bundle.py) · [包内启动说明](../../demo/competition-bundle/README-COMPLETE.zh-CN.md)

| 项目 | 实测 |
| --- | --- |
| ZIP | `RunProof-EffectWitness-Complete-Project.zip`，1,113,163 字节 |
| ZIP SHA-256 | `9cd3da5f2b196cbb07fd999a4bc4bbd0640f8da8a63f09f94624f2a6bf5a7ffe`，与 sidecar 和独立解包结果吻合 |
| 归档源 | `bc8f72438677dee69b905a3ffbfe27894bc17d06` |
| 完整成员清单 | 解包根 `bundle-manifest.json`，SHA-256 `0f0a308602eb2878c327112170406129e211c484c280759dd316bac73ef8c795` |
| 成员实测 | 共 320 项。`app/` 33 项，其中 `site` 11 项。`source/` 283 项。根 4 项为 manifest、启动说明、架构与许可说明。 |
| 启动条件 | 新解包 `app/` 起初无 `node_modules`、`.local` 或 `.env`。PATH 仅保留系统目录，不提供 Git 或 npm。只传已核实的 Python、Node 绝对路径，5.041 秒就绪。 |

包内浏览器确认一次后，获得独立 nonce `b5c470ddcbfd48fab2950fcb6eb7b139`、owner `ab1bd24a9f2442f3a912ac1816a3267b`、request `cbf32002-f26e-4d05-bd74-8b5b568ea4ae` 及 session `8727ccf18ea14c12857e7cf85e5ab8d0`。订单与配置各有一条收据，SQLite 只读回查通过。包内实际下载的 Witness 为 17,192 字节，SHA-256 为 `24cd2562a962f999a21dae3bdb7196d31fa4ee1af38216ab8ae076d3acef46b2`，与其自身账本匹配。包内 `verify-witness.ps1` 调原 verifier，正常文件退出 0，返回 `CONTENT_CHECKED_LOCAL` 和 `NOT_ESTABLISHED`。一次性副本配错误的全零摘要时退出 3，原因为 `WITNESS_DIGEST`。原文件与副本的哈希复查一致。包内 owner 单独按回执停机，两个回环端口都无监听。

```powershell
& $node demo/competition-bundle/build-bundle.mjs $buildNonce $py --complete
& $py -I -B ci/test_rpf114_competition_bundle.py $zip $freshExtraction
# 以下在新解包的 app/ 目录执行
.\start.ps1 -PythonExe $py -NodeExe $node
.\verify-witness.ps1 -PythonExe $py -Witness $packageWitness
.\verify-witness.ps1 -PythonExe $py -Witness $disposableCopy -ExpectedSha256 ('0' * 64)
.\stop.ps1 -Nonce $packageNonce
```

| 浏览器路径 | API GET | 调查 GET | Witness GET | `POST /session` |
| --- | ---: | ---: | ---: | ---: |
| 新源码检出 | 9 | 2 | 1 | 1 |
| 源码同 nonce 只读重开 | 10 | 3（含注入的 503） | 1 | 0 |
| 新目录解包 | 9 | 2 | 1 | 1 |

## A04 · 维护收口

| 本机检查 | 结果 |
| --- | --- |
| `npm test -- web/src/features/effectwitness/CompetitionAgentPage.test.tsx` | 12 项通过，退出 0 |
| `& $py -B -m unittest -v ci.test_rpf114_competition_bundle` | 2 项通过，退出 0 |
| `& $node --test ci/test_rpf113_competition_server.mjs` | 1 项通过，退出 0 |
| `& $py -I -B ci/verify-public-docs.py` | `PUBLIC_DOCS_PASS files=18 pairs=7`，退出 0 |
| `git diff --check` | 退出 0 |

代码和启动入口按原候选验收，交付只写本报告和当前状态。构建仍有 Vite 大 chunk 提示。实跑范围为本机离线 Reference Agent。包内只读重开、Java Control Plane、JiuwenSwarm、跨仓集成和历史矩阵复跑未执行。基线产品 CI 通过，Canonical 的两道必需覆盖分别缺 534 项和 516 项。交付提交的两条 CI 独立按实际 checkout 核对，回执保存在本轮证据根的 `ci-delivery.json`。[基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45942969794) · [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45942969812)

### 本轮取证与公开索引

本机根为 `.local/rpf-126/c6ec65f9/`。`preparation.json` 保存检出、锁文件和安装回执。`source-run.json`、`source-readonly.json`、`bundle-run.json` 保存页面和请求。`source-before.json` 与 `source-after.json` 记录六份原件的比较。`bundle-build.json`、`bundle-extract.json` 和 `unpacked/bundle-manifest.json` 记录完整包位置及成员身份。`source-verify.json`、`bundle-verify.json` 和 `bundle-negative-summary.json` 保存两份内容复核和拒绝回执。

| 所需公开材料 | 入口 |
| --- | --- |
| 当前工作入口、交接与运行方式 | [README](../../README.md) · [中文 README](../../README.zh-CN.md) · [项目源文件](../../docs/项目源文件/00-START_HERE.md) · [Runbook](../../docs/项目源文件/RUNBOOK.md) |
| 与本次验收相关的历史结论 | [RPF-122 干净检出](../rpf-122/RESULT.md) · [RPF-125 调查故障](../rpf-125/RESULT.md) · [RPF-124 本机复验证据边界](../rpf-124/RESULT.md) |
| 项目状态及既有归档目录 | [当前状态](../../docs/project/CURRENT_STATE.md) · [维护归档索引](../../docs/history/MAINTENANCE_ARCHIVE.md) |
