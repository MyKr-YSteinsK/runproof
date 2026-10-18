# RPF-47｜竞赛可信演示与首轮申报材料

本目录和本计划的公开入口只存在于 `codex/rpf-47-competition-evidence-demo` 功能分支，不表示 `main` 已实现或接受本分支内容。它把三类来源分开：RPF-46 已提交 Live 摘要、RPF-43/44 可离线锚定的历史 Witness，以及页面打开时没有新执行的只读回顾。

## 运行只读演示

在此分支的仓库根目录，使用项目已有的 Node 依赖运行 Web 应用：

```powershell
npm run dev -- --host 127.0.0.2 --port 4174 --strictPort
```

打开 `http://127.0.0.2:4174/effectwitness/recorded`。此命令仅在回环地址启动 Vite，使用独立端口以避开本机已有的默认 4173 服务；`--strictPort` 保证端口冲突时直接失败，不会悄悄换端口。该页面从跟踪文件静态读取摘要和历史样本；它不连接 Python Gateway、不请求 Provider、不发起订单/运维试验，也不提供启动实验按钮。浏览器只校验编译进页面的固定摘要、manifest 字段和报告事实；它不能自行读取 Git HEAD 或认证自身来源。需证明 pinned commit 祖先关系和 Git blob 字节时，运行下方离线 CLI。任一固定校验不符时页面 fail closed，不用 fixture 补位。

本页面可在 RPF-45/46 本机 Gateway 未启动时查看。已支付的 RPF-46 原会话 Witness 不在此 checkout；页面不会伪造下载链接或把摘要称作完整 Live Witness。

## 独立离线复核

```powershell
python -B spikes/rpf-47/verify_evidence.py --root .
python -B -m runtime.runproof_runtime.effectwitness.witness_verify spikes/rpf-43/sample-witness.json --expected-sha256 ff4870c3f53251d5bcfc02716ed4e30269bb73ab982c3851485059f30b43391e
python -B -m runtime.runproof_runtime.effectwitness.witness_verify spikes/rpf-44/sample-ops-witness.json --expected-sha256 21b5ded6bdf2a6c602d8016317756b67884351fbffcef60bedbe30fa3f4f8873
```

第一条校验本目录 manifest 固定身份、来源文件 SHA-256、RPF-46 反馈/选择顺序、业务结果及基线提交祖先关系。后两条运行实际离线 verifier。历史样本返回 `VERIFIED_ANCHORED` 只证明有界文件内容与独立给定的 hash 相符；`issuer_authenticity` 仍为 `NOT_ESTABLISHED`。

## 材料与状态

- [SUBMISSION.md](SUBMISSION.md)：可复制的创意申报文字、字段映射和待用户核实项。
- [DEMO_SCRIPT.md](DEMO_SCRIPT.md)：三分钟内逐秒分镜、旁白、来源字幕和拍摄步骤。
- [EVIDENCE_MANIFEST.json](EVIDENCE_MANIFEST.json)：不可由 UI 改写的来源、摘要和竞赛公开信息清单。
- [RESULT.md](RESULT.md)：RPF-47 唯一正式任务结果及 A-01～A-10 证据。

官方华为云公告在可读取的公开索引内容中列明创意提交日期为 **2026-10-30**，但官方可读页面没有给出截止时刻或时区；直接打开公告超时，登录后的报名问卷与最终字段未核实。10-31 不作为延期承诺。作品处于 `NOT_SUBMITTED`，参赛者需自行核对报名页、个人/团队信息及知识产权条款。

本轮没有发现可用的录屏/编码工具，因此没有制作 MP4。可直接在上面的只读路由拍摄；正式拍摄脚本、页面和来源清单见 [DEMO_SCRIPT.md](DEMO_SCRIPT.md)。
