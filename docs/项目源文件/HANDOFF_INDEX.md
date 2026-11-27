# RunProof 阶段验收接手索引

2026-11-27，RPF-127。当前停在阶段验收。阅读本页所在的完整 Git 提交。使用 Project 附件时，以导出清单记录的完整 SHA 与逐文件摘要核对同一版本，再查 [启动入口](00-START_HERE.md) 和 [CURRENT_STATE](../project/CURRENT_STATE.md)。

| 要核对的事项 | 已确认事实 | 入口 |
| --- | --- | --- |
| 当前候选源码与启动 | RPF-126 固定源码 `bc8f72438677dee69b905a3ffbfe27894bc17d06`。Windows 完成源码冷启动、同 nonce 只读重开和独立解包启动。只读重开新增 POST 与业务写入均为 0。 | [固定源码](https://github.com/MyKr-YSteinsK/runproof/tree/bc8f72438677dee69b905a3ffbfe27894bc17d06) · [实跑命令](RUNBOOK.md#rpf-126-离线验收命令) |
| 当前候选包与 Witness | 完整工程 ZIP 为 1,113,163 字节、320 成员。SHA-256 为 `9cd3da5f2b196cbb07fd999a4bc4bbd0640f8da8a63f09f94624f2a6bf5a7ffe`。已验收源码及包内 Witness 内容，外部签发者未建立。 | [RPF-126 公开验收与本机证据索引](https://github.com/MyKr-YSteinsK/runproof/blob/b87795bb5dac151af40b91c32cb01b23847999f8/spikes/rpf-126/RESULT.md) |
| 产品 CI | RPF-126 报告交付 `b87795bb5dac151af40b91c32cb01b23847999f8` 上通过。交接版本查其导出清单内的工作流、attempt 和实际 checkout。 | [基线产品 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45949094891) · [Actions](https://github.com/MyKr-YSteinsK/runproof/actions) |
| Canonical Gate | 同一基线的发行门禁仍受必需覆盖阻塞，两步分别缺 534 和 516 项。RPF-120 的 30 项 Windows 本机复验保留其独立证据。 | [基线 Canonical Gate](https://github.com/MyKr-YSteinsK/runproof/actions/runs/45949094899) · [RPF-120 对账](../../spikes/rpf-120/RESULT.md) |
| 历史封存 | RPF-114 源码 `f6cc79b811fe1381851690800e96c71362cd9a73` 及工程 ZIP、PPT、Submission ZIP 的封存身份可取。旧 Source Map、Witness、WAL、owner 和研究现场各按原索引保留。 | [冻结源码](https://github.com/MyKr-YSteinsK/runproof/tree/f6cc79b811fe1381851690800e96c71362cd9a73) · [封存清单](../../spikes/rpf-114/DELIVERABLES.md) · [维护归档](../history/MAINTENANCE_ARCHIVE.md) |
| 尚未核实 | 初赛实际上传的文件、版本、时间和摘要缺直接确认。封存后到 RPF-126 的 Git 增量可追溯。另有一个旧工程包的实际用途待定，原件原位保留。 | [固定提交对照](https://github.com/MyKr-YSteinsK/runproof/compare/f6cc79b811fe1381851690800e96c71362cd9a73...b87795bb5dac151af40b91c32cb01b23847999f8) · [RPF-127 取证](../../spikes/rpf-127/RESULT.md) |

本轮移动了一棵可重新生成的暂存树，仍可按逐文件摘要恢复。[待清理区](../delete/README.md) · [RPF-127 复核](../../spikes/rpf-127/RESULT.md)

复赛改造、`config-center` 联动与架构取舍仍由用户评审。[稳定目标](../project/PROJECT_BRIEF.md) · [已接受决定](../project/DECISIONS.md) · [升级候选](UPGRADE_REVIEW.md) · [作品集候选](PORTFOLIO.md)
