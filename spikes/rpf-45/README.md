# RPF-45｜受限实验 Gateway 与真实 Web Lab

本机浏览器在 `/effectwitness` 发起虚构订单全额退款或运维配置变更，Gateway 复用共享 Budget/Orchestrator、独立 SQLite Authority Reader、领域 oracle 与 Witness verifier。原 Java `/api` 和 canonical Web 调查入口保持只读。本轮 **DETERMINISTIC_TARGET / Provider=0 / Explorer NOT_IMPLEMENTED**。

## 本机启动与停止

从已核实的 `D:\CS\runproof` 根目录执行；需要已有 Python 3.14.6 / Node / `node_modules`，不自动安装或下载。

```powershell
powershell -NoProfile -File spikes/rpf-45/local-lab.ps1 -Action Start
# 打开 http://127.0.0.1:4185/effectwitness
powershell -NoProfile -File spikes/rpf-45/local-lab.ps1 -Action Stop
```

启动器为本次进程生成随机 secret，仅通过环境交给 Gateway 与 Vite，恢复启动器自身环境，不写 secret 文件、不输出 secret。只绑定 `127.0.0.1`：Web 4185、Gateway 8765；端口占用即拒绝。4173 的 origin 在现场曾呈现别的项目页面，因此 Lab 使用独立 origin，不清理用户已有浏览器缓存。普通未启用 Lab 的 Vite 仍使用 4173。

Vite 只有 `RPF_EW_LAB_ENABLED=1` 且 server-only `RPF_EW_LAB_GATEWAY_TOKEN` 合法时代理 `/effectwitness-api`，授权头在服务器侧注入；不是 `VITE_*`。Gateway 还必须显式传 `--enable-local-simulation`。Host/Origin、Content-Type、请求大小、exact route/schema 在服务器检查；没有 CORS 放行。Vite watcher 排除 `.local/**` 与 `docs/reviews/**`，避免运行产物引发重载，也保护用户目录。

Stop 按保存的 PID、进程启动时间及 executable 身份检查，仅停止本次进程及明确的 Gateway/esbuild 子进程；忙时拒绝正常 Stop。账本与 Witness 保留。若进程非正常结束，重启也不自动重放未决操作。启动器路径检查为本次 Windows 工作区固定，迁移到其他机器须重新审核路径与端口。

## 操作链与事实边界

1. Task Setup 选择 `order` 或 `ops`。服务端固定 `LOCAL_CONTROLLED_CAPTURE / response-lost`，浏览器不能选择预算、金额、release 值、路径、owner、脚本或 Authority。
2. POST 先原子持久预留额度、Session/Run/Operation/合同，再开执行线程。最多 3 次预留，1 running / 0 queued，失败或排队前取消也消耗预留。
3. Timeline 事件来自共享执行器回调；事务提交后响应丢失，UNKNOWN 必须独立 receipt reconcile。冻结 authority before/after 后 reset/readback/remove。
4. Session 的 bookkeeping 状态与 Run outcome / Effect / Fault / Attribution / Reproduction 分开。状态 Diff 来自 oracle，完整 feedback/合同/权威事实可展开。
5. 浏览器先取回实际下载 bytes、复算 SHA-256，成功后给下载链接。服务端每次读回和导出也复验原 bytes；读取失败会清除有效结果，禁止 fixture fallback。

`LIVE_LOCAL_SIMULATION` 是本次 Gateway Session 的来源标签；Witness 保留兼容的 `CONTROLLED_ORDER_LOCAL_SIMULATION` / `CONTROLLED_OPS_LOCAL_SIMULATION`。既有交叉域合同仍是 `rpf-cross-*-v1/owner=rpf-44`，存储所有权明确为 `rpf-45`，不改旧合同身份。新增的 `storage_task` 与事件/隔离回调是服务端注入参数，不在 HTTP 请求中开放。

页面只宣称 **CONTENT_CHECKED_LOCAL / ISSUER_AUTHENTICITY_NOT_ESTABLISHED**。本 Gateway 给出的 SHA 是局部内容一致性参考，不是独立 trusted external anchor；四轴保守为 `CORRELATIONAL_ONLY / NOT_TESTED`。未展示实时 LLM Explorer，也未拼接 RPF-42 历史会话；历史研究如后续接入，须单独标 `RESEARCH_RPF42_REPORTED`。

## 冻结 HTTP DTO｜`rpf-lab-v1`

所有路由都以 `/effectwitness-api` 开头；原 `/api/v1` 不变。GET 幂等，POST 创建用显式幂等键。

| 路由 | 请求 / 返回 | 事实来源 |
| --- | --- | --- |
| GET `/capabilities` | domains、固定 mode/fault、limits、remaining_reservations、busy/enabled、explorer、issuer 限制 | 服务端政策 / 账本派生 |
| POST `/sessions` | exact `{domain: order\|ops, mode: LOCAL_CONTROLLED_CAPTURE, request_id: [A-Za-z0-9_-]{8,80}}` → 202 + SessionSnapshot | 先持久预留；相同键+相同身份返回同一 Session；冲突 409 |
| GET `/sessions/{session_id}` | SessionSnapshot：schema/session/request/domain/run/source/status/times、contracts、events、result、usage、witness、error_code、cancel_requested、storage_owner；失败时可有 quarantine_status | bookkeeping 与已捕获业务事实分列 |
| GET `/sessions/{session_id}/witness` | 真实 canonical JSON bytes；attachment；no-store；只提供已校验的 COMPLETED 证书 | 重新读回 / SHA / verifier / Session identity |
| POST `/sessions/{session_id}/cancel` | exact `{}` → 状态快照 | ACCEPTED 可 CANCELLED；RUNNING 为 CANCEL_REQUESTED，仍需 reconcile，不声称已停 |
| Error | `{schema_version,error_code}`，400/401/403/404/409/413/415/429/503 | 无堆栈、secret、数据库路径或绝对用户目录 |

SessionSnapshot 的 `result` 是真实 v2 bundle（contracts/capture/observation/events/claims/digests/limitations），`usage` 为共享预算实际计数；未形成有效证据时 result/witness 为 null。事件 facts 属于 OBSERVED_FACT；oracle 与 claims 属于 VERIFIED_RESULT；界面选中项、剩余额度是派生视图，不生成 AI reasoning。

## 持久化、崩溃与取消

`.local/rpf-45/sessions/owner.lock` 持有 OS 级单写者锁，ledger 为 canonical JSON，写临时文件→flush/fsync→atomic replace；线程内 RLock 串行化预留及状态转换。两个服务实例不能同时持有同一 store。`ledger.json` 保存最多三个完整 Session；证书为 `sessions/<id>/witness.json`。没有 TTL/自动过期或自动 GC。

重启时 ACCEPTED/RUNNING/CANCEL_REQUESTED 一律进入 `RECONCILE_REQUIRED`，拒绝后续新 Session，不自动 retry。仅对独立 reader 能确认 owner/run/environment/generation 且目录只含预期 SQLite 文件的 task sandbox 做移动；无法确认则原地保留并报状态。运行异常由共享执行器或 Session store 保留到 `.local/quarantine/rpf-45/<session-id>`。没有管理员自动恢复、自动 reset 或开放 reconcile API；需后续明确审查。COMPLETED 的重启查询/同键 POST 仅读回同一证书，不创建新业务操作。

HTTP header 先限定大小与 transport 轮廓；为防 Windows unread POST bytes 引起连接重置，提前拒绝时最多排空 4096 transport bytes，JSON 接受上限仍 1024 bytes。排空不解析合同、不预留 Session；认证/Origin 通过后才解释 JSON。

## 测试与复核

```powershell
New-Item -ItemType Directory -Force .local/rpf-45/tmp
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=(Resolve-Path .local/rpf-45/tmp).Path
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
python -m unittest discover -s runtime/tests -t . -p 'test_*.py' -v
npm test -- --cache=false
$env:RPF_EW_LAB_TASK_OUTPUT='1'
npm run build
```

`build` 已执行 typecheck；task 输出在 `.local/rpf-45/web-build`，Vite cache 在同任务目录。旧 EffectWitness 测试仅重定向夹具根，禁止消费旧 `.local/rpf-40..44`。`test_effectwitness_lab` 含真实两域 HTTP/独立离线子进程、并发同键/忙时、取消、持久锁/重启、坏证据与提交后未决隔离；Web 测试含独立 DTO、失败/Hash、默认禁用代理、Host/Origin 和旧只读 proxy 回归。真实浏览器 Gate 的身份、结果与限制见 [RESULT.md](RESULT.md)。

离线核验当前导出时，不应把同 Gateway 返回的 SHA 冒充外部锚：

```powershell
python -m runtime.runproof_runtime.effectwitness.witness_verify .local/rpf-45/sessions/<session-id>/witness.json
# 合法但无独立锚：UNANCHORED_INCONCLUSIVE，exit 2；issuer_authenticity NOT_ESTABLISHED。
```

原 RPF-43/44 样本保持字节不变，使用其已审 Git SHA anchor 仍可分别得到 anchored exit 0。没有本轮公开重签的 sample 文件。

本服务仅为显式启用的本地开发演示，未提供公网、多租户、正式 Worker/Control Plane Job、LLM Explorer、PKI、Docker 正式对接或部署授权。不要直接对外暴露，也不要删除账本来恢复额度。
