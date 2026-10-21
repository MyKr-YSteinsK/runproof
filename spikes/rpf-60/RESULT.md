# TASK_RESULT · RPF-60

Plan ID：`RPF-60`；Revision：`rev-1`；日期：2026-10-21。
Status: Complete

## 结果与身份

原 Desktop Web 已接入版本化跨域 Gateway。真实浏览器确认并启动一次新 Session，两次真实 Explorer 选择驱动订单和配置受控业务；页面读取同一 Session 的结果，下载的新 Witness 与服务端原件逐字节一致，独立离线校验通过。源码实现、实验执行、独立验证、分支交付分别记录于下文与诊断文件；阶段接受仍待 Architect。

- Root：`D:/CS/runproof`；精确 Base/父分支 HEAD：`c07236b72aea6690ba96d193178fc105f685ea50`。
- 新分支：`codex/rpf-60-cross-domain-live-lab-gateway-ui`；origin：`https://github.com/MyKr-YSteinsK/runproof.git`。
- `main` 保持 `bda0cd49e50e3181f604324e94877a24b9885334`；父分支为 `codex/rpf-59-cross-domain-real-explorer-selection`。focused commit、普通 push 与 fresh remote SHA 在聊天交付回执中报告，不循环改写本文件。
- `docs/reviews/` 仅观察到顶层未跟踪条目，未进入、枚举、读取或暂存。Project State、历史目录、RPF40–59 源码和旧 Witness 均保持原字节。旧 ignored 运行账本未读取。
- `EVIDENCE_ACCEPTED=PENDING_ARCHITECT_REVIEW`；`STAGE_ADVANCED=NOT_DECIDED`。

## 实现与设计选择

保留 FROZEN 的权限、静态两候选、来源分级、独立 Oracle、预算、未知停写与历史不可变合同。采用 RECOMMENDED 的 `/effectwitness-api/cross-domain` 静态命名空间、有界 DTO、可信 REVIEWED 投影、独立版本化 Runner 和同一 Session 页面；DELEGATED 的实现采用单进程线程执行、磁盘 WAL、OS lease、永久预约与只读重启恢复，不引入调度服务或任意执行注册表。

新增 Runtime 文件为 `lab_cross_domain_contracts.py`、`lab_cross_domain.py`、`lab_cross_domain_verify.py`、`lab_cross_domain_projection.py`。分别持有合同/Provider shape、共享账本与静态领域 Port、纯离线验证、Gateway store/投影。旧 `lab_gateway.py` 新增 allowlist；`lab_store.py` 增加默认兼容的 read_only/task-root 参数。订单与配置分别静态派发 `ORDER_PORT` / `CONFIG_PORT`，从不调用旧 RPF59 `probe.py live`，不 monkeypatch 历史全局路径。

新内核为 RPF58 共享 Ledger/TaskGuard 与 RPF59 Explorer/反馈合同的版本化适配，订单 Port 使用 `OrderSandbox` / `AuthorityReader` / `effect_oracle`；配置使用稳定 `TargetHost`、Journal、ConfigLiveHttp、SDK身份与固定 Java helper。配置场景谓词保留 RPF55 原语义，`CANDIDATES` 仅局部别名为 `CONFIG_CANDIDATES`；order/config execute/verify 使用各自新符号。源码复制/适配的维护成本集中在新内核、合同和 Verifier，后续稳定抽取需要独立 Plan。具体文件行数与源 SHA 见本次 source map/本地 `source-lines.json`；这些文件不是对旧证书的重新签发。

版本化复制/适配及新增编排的实际行数：共享/订单/配置合并内核725行，合同237行，Verifier133行，Gateway store/投影233行，共1328行；这包含复制、身份改写和新逻辑，不能当作1328行完全独立原创实现。新增Python测试237+68行。Web新页面35行、API32行、翻译4行、测试10行（部分采用长行）；原集成文件仅59行新增/6行删除。稳定旧依赖16个文件均只读复用。

Web 新增 `CrossDomainPage.tsx`、`crossDomainApi.ts`、`crossDomainCopy.ts` 与邻接测试，App 仅新增路由，AppShell 仅新增导航，lab.css 增加局部布局，Vite 增加 rpf60 输出隔离。新页面有实际 zh/en 翻译、来源/权限说明、费用确认、Run/反馈 Timeline、State Diff、事件深链、取消请求状态、原始 SHA 与独立校验入口。UI 只展示服务端派生事实，无伪进度。Browser hash checked 与 offline verifier result 分开。

新显式跨域 opt-in 进程将旧免费 Lab 写操作禁用，以免旁路新增业务资源；原默认 Gateway 模式行为保持，原订单/ops 选择页与 RPF46 Recorded 页面保留。新进程不允许同时启用旧付费模式。该隔离选择在 README 与 Gateway diagnostic 中明确披露。

## 验收

| 验收 | 状态 | 实际证据 |
|---|---|---|
| A-01 身份、安全范围 | PASS | 精确 Base、新分支、origin、task root 与 workflow 触发审计；无部署副作用 |
| A-02 历史证据分层 | PASS | 原 RPF59 raw SHA `0bb359ca78c7c0415afef30ff959d41112da3f5155e5ae18e68be28735f9996a`，原 Verifier 后投影；REVIEWED 与 LIVE 分离 |
| A-03 Gateway | PASS | 实际 HTTP Token401/Origin403/Host403/类型415/过大413/错误对象及路由404；幂等、恢复、cancel、quota、lease、重启测试 |
| A-04 共享内核/领域 | PASS | 4 种合法候选顺序各25类 rehash 负控；预算、未来反馈、未知写、权限/源失败关闭 |
| A-05 UI 基线 | PASS | Web64测试、typecheck/build；真实 zh/en、Timeline/State Diff、键盘深链、旧Lab/Recorded、Gateway不可用；canonical Overview 无后端时准确 API unavailable |
| A-06 浏览器操作 | PASS | 先免费真实 Gateway 读取；随后实际 checkbox/Start，经前端 POST202 创建唯一新 Session |
| A-07 真实 Live | PASS | DeepSeek2请求，两领域受控业务/Oracle、Round1反馈先于Round2输入冻结，同源Session |
| A-08 Witness | PASS | 下载字节一致；独立 CLI正确/缺失/错锚=0/2/3，25等价语义负控及4额外语义负控均拒绝 |
| A-09 预算/资源/机密 | PASS | 2请求/1340tokens；源码冻结、无未知usage/未决mutation；全部拥有的服务/业务端口与进程退出，秘密不入Git/DTO |
| A-10 回归/Git | PASS | Runtime394项完成（2 Docker skipped）、Web64项、12历史锚、Reviewed/Public checks；focused branch交付 |

Runtime targeted9项与Gateway HTTP4项通过。全 Runtime 首轮隔离镜像遗漏 Plan 的测试父目录，2项初始化报错；仅为镜像创建该目录，保持源码 SHA 不变后重跑全套，保留首轮日志。Docker两项 skipped 不构成 Docker验证。Web build有原有500kB chunk提示。未运行 Maven、hosted CI、生产部署或物理移动设备；canonical Control Plane 未启动，浏览器验证的是旧页面 API 不可用时失败关闭，未声称该后端在线成功。

交付差异检查保留冻结新Python测试末尾的一个空白行（`git diff --check` 的 blank-at-eof 提示）；没有为格式提示改写已运行的源码。其余尾部空格检查通过。

12件历史证书43/44/48/49/50/51r4/52r3/53r6/55r2/56r4/57v1/58r2均按原 raw SHA 与原独立 CLI exit0。完整原锚、命令模块和诊断见 `verification-diagnostic.json`。

## 本轮真实会话

- Session：`rpf60-session-ff259b8d1bef494b`；request_id：`9cd8a718-05d3-494a-a463-5a0e440aaa7c`。
- 浏览器 `POST /effectwitness-api/cross-domain/sessions` 仅一次，HTTP202；CDP id `29820.1352`。无CLI代替浏览器启动业务。
- Round1：`order-refund/normal`；Run `rpf60-order-da9b1127b5424628`；真实 ToolCall `call_00_jjEzS6RGEBcVHRgemfTu1578`。
  fresh SQLite PAID/refund0/revision0 → REFUNDED2500/revision1，唯一收据。独立只读 receipt Reader/HMAC + effect oracle通过，最终另开RO/query_only连接读回一致。
- Round2：`config-java-http/planned-but-inhibited`；Run `rpf60-config-2e979367c8d54805`；真实 ToolCall `call_00_BUSqb1erAEW0hcU72yBX8958`。
  真实 Java17/H2 ABSENT→v1→v2/history `[2,1]`，同服务GET Authority通过。fault planned=true / triggered=false / observed=false，状态 `NOT_TRIGGERED` / `FAULT_INHIBITED`。
- Explorer返回模型 `deepseek-flash`；response ids `e694cda0-e24c-491a-947f-97858200fd76`、`8219aade-5242-4e60-b118-94c0916a9fce`。只保存白名单ToolCall/shape/usage，无自由正文或私有推理。
- 两轮 usage：466+40=506、788+46=834；总prompt1254/completion86/**1340 tokens**。保守估算上界 **CNY0.007191**，不是账单；6000tokens/**CNY0.108**预约不返还，任务硬上限CNY0.15。计价守卫见[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)与源合同：峰值USD0.30/1.20每百万tokens乘15保守系数，不冒称实时汇率。
- 正式2 Trials；SQLite1/退款1、JVM1、正式SDK1、业务HTTP8/POST2/health1。health预约3，另2未用且无I/O。无Provider重试、未知usage或未决mutation。
- 免费metadata1 PASS，cold1 PASS、cold2 NOT_RUN。cold popen/ready/report真实PID同为20236；正式SDK10592、Java5752，SDK scripted4 completions/3 tools。SDK执行子进程总2（cold1+formal1）。
- 共享账本83帧/82事件，单调时间跨度30.8084855秒。候选变化和时序属于观测，理由 `RATIONALE_NOT_RECORDED`；两个领域verified事实数1/2不能相加为跨域信息增益。

## 证书与源码身份

新公开原件：`cross-domain-live-evidence.json`，1,069,226 bytes；schema `rpf60-cross-domain-selection-evidence-v1`，source_kind `REAL_EXPLORER_CONTROLLED_TARGETS`。

Raw SHA-256：`81422d26a6ea1406d66d73fecfe0a98a09310a81812faf84e95ed896679b8df9`。

源映射：16个新/修改文件+16个稳定依赖，digest `3402428d659a5140d8c90a108a59142b78b0beba2d6de7d2e4c9a3ce967e0ada`；G3、metadata、cold、live和交付源码一致。Verifier `rpf60-selection-verifier-v1`，SHA `8c6848643c6513807c731936d64e929aae8576b15c43eb0b518fe3db6e39a8a9`。

```powershell
python -B -m runtime.runproof_runtime.effectwitness.lab_cross_domain_verify spikes/rpf-60/cross-domain-live-evidence.json --sha256 81422d26a6ea1406d66d73fecfe0a98a09310a81812faf84e95ed896679b8df9
```

原始字节锚是外部完整性检查；本地源/Verifier身份校验不构成发行者签名、独立第三方真实性或独立复现。正式25类CLI语义篡改重hash仍exit3；额外假fault激活、缺Authority、cold PID拼接、外部endpoint亦拒绝。

## 浏览、恢复与清理

实际入口 `http://127.0.0.1:4185/effectwitness/cross-domain`，已审查页 `/reviewed`；本轮详情 `/effectwitness/cross-domain/sessions/rpf60-session-ff259b8d1bef494b?event=e20`。本机启动/权限/只读恢复按 README；本次额度已耗尽，不得清除标记重跑。

浏览器实测：先打开reviewed页、切换zh/en、校验原SHA、键盘深链；再确认并启动LIVE，观察RUNNING→COMPLETED、双域状态、故障未触发，校验SHA并下载。断开Gateway显示 `GATEWAY_UNAVAILABLE`，无历史成功回填。物理Gateway PID15640→30272重启后读取同一完成Session/同一Witness，remaining_sessions=0，无新增业务/Provider。

浏览器下载工具默认短暂写入本轮自有 `C:/Users/Yukis/Downloads/rpf60-session-ff259b8d1bef494b-witness.json`，自定义下载目录CDP方法不受支持；立即核对字节并仅移动这一确切自有文件至 `.local/rpf-60/downloads/browser-witness.json`，默认Downloads无本轮残留。没有触碰用户其他下载文件。

最终关闭Gateway/Vite；8765/4185及正式Java/Host11596–11599均关闭，cold/正式SDK/Java与拥有的服务进程均退出。SQLite/JAR、WAL、冷启动/运行回执、原下载、首轮失败和最终回归、浏览器截图等保留于ignored `.local/rpf-60`，便于审查且防止额度丢失；删除的仅本次已无用的临时生成脚本。没有安装、云操作、安全策略更改、PR/merge/main push或发布。

## 已证明边界

Claim：`REAL_EXPLORER_SHARED_SESSION_CONTROLLED_SELECTION_VERIFIED`。有效完整Witness1/1；正式2轮的领域证据均通过独立领域Oracle。所有合成负控明确测试来源，拒绝样本不算模型发现的违规。订单Target为 `DETERMINISTIC_ORDER_TARGET`，配置为 `FIXTURE_SCRIPTED`；只有Explorer是真实Provider。

没有证明两个真实LLM Target、真实配置故障触发、自主发现业务违规、反馈因果优势、统计优势、数据库外部Authority、Issuer签名、独立复现、H1/H3或WorkSwarm。未部署Hosted URL。Project State与阶段接受未自行推进。
