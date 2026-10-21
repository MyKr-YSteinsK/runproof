# RPF-60 · 本机跨域 Lab

此版本在原 Desktop Web 新增 `/effectwitness/cross-domain`，通过原 `/effectwitness-api` 开发代理访问受限 Gateway。未部署公开服务。

## 使用与权限

- `/effectwitness/cross-domain/reviewed`：RPF-59 已审查证据，固定 raw SHA `0bb359ca78c7c0415afef30ff959d41112da3f5155e5ae18e68be28735f9996a`；服务端用原独立 Verifier 验证后投影。它始终是 REVIEWED。
- `/effectwitness/cross-domain`：先读取服务端能力；明确确认费用、模拟副作用和权限，才能创建一次新的 LIVE Session。
- `/effectwitness/cross-domain/sessions/:id`：同一 Session 的状态、Run、选择、反馈、Timeline 深链、State Diff、故障状态、实际用量与不可返还预留。刷新与只读 request_id 找回不会重跑。
- 订单 Target 为确定性 SQLite 受控业务；配置 Target 为真实固定 SDK 的 scripted Fixture + Java17/H2；只有 Explorer 调用真实 DeepSeek。
- 最多两次 Explorer POST、6,000 tokens、保守 ¥0.15、一个 Session / 两次 Trial；重复候选合法。配置候选预注册故障被禁用，实际 `NOT_TRIGGERED`。

## 本机启动

在仓库根目录使用现有依赖；不安装额外包。服务端环境设置一个至少 32 字符的随机 `RPF_EW_LAB_GATEWAY_TOKEN`，供 Gateway 与 Vite 共用，禁止使用 `VITE_` 前缀或放入前端源码。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -X utf8 -B -m runtime.runproof_runtime.effectwitness.lab_gateway --enable-local-simulation --enable-paid-cross-domain-pge
```

另一个终端使用同一服务端 token：

```powershell
$env:RPF_EW_LAB_ENABLED='1'
$env:RPF_EW_LAB_TASK_OUTPUT='1'
$env:RPF_EW_LAB_TASK_ID='rpf-60'
node node_modules/vite/bin/vite.js --host 127.0.0.1 --configLoader runner
```

Gateway 绑定 `127.0.0.1:8765`；浏览器入口 `http://127.0.0.1:4185/effectwitness/cross-domain`。Bearer 仅由 Vite 服务端注入；保留 Host/Origin/Sec-Fetch-Site、JSON 类型、body 上限与静态路由限制。直接浏览器连接后端不会得到 token。

此命令显式选择跨域模式；该进程中的旧免费 Lab 只读，避免旁路消耗本轮未授权业务资源。默认不加跨域 flag 的原 Gateway/订单/ops/PGE 启动行为保持原样；不允许在同一进程同时开启两种付费模式。RPF-46 Recorded 原页面保持独立。

新 checkout 缺少当前任务的固定 SDK/JDK/源包/冷启动与冻结 Gate 时，付费功能不可用；已有 REVIEWED 页面仍可读取。**此任务的一次额度已使用，重启、刷新、更改 request_id 或根目录均不能增加额度。** 不删除 `.local/rpf-60` 的 owner、预约标记、TaskGuard 或 WAL。未来新的付费实验需要新的明确授权与受控身份设计。不要运行旧 `spikes/rpf-59/probe.py live`。

免费身份与冷启动入口为 `python -X utf8 -B -m runtime.runproof_runtime.effectwitness.lab_cross_domain_projection metadata` / `cold`；它们是有额度、源身份和前置 Gate 约束的执行步骤，不是要求读者重跑的安装命令。不要重复运行已经完成的冷启动。

## API

所有路径位于 `/effectwitness-api/cross-domain`：

| 方法 / 路径 | 语义 |
|---|---|
| GET `/capabilities` | opt-in / preflight / key / quota；启动 nonce |
| GET `/reviewed/rpf-59`、`/reviewed/rpf-59/witness` | 固定锚的已审查投影、原始字节 |
| POST `/sessions` | 固定模式、request_id、nonce、费用/模拟确认；先持久预约再执行 |
| GET `/requests/:request_id` | 创建返回未知时，只读找回原任务 |
| GET `/sessions/:id` | 服务端实际状态；无定时伪事件 |
| POST `/sessions/:id/cancel` | 请求取消，在 Provider/Trial 之间的安全边界停止 |
| GET `/sessions/:id/witness` | 完整执行、Oracle、离线 Verifier 通过后才返回原字节 |

取消不会撤销已经提交的模拟业务。未知 Provider usage 或业务 mutation 保留上界与原资源，停止后续 I/O；未决状态为 `RECONCILE_REQUIRED`，不签完整成功证书。进程重启只读恢复，绝不续跑；永久预约与 OS 独占 lease 分开。普通关闭先等待执行到安全边界并释放拥有的资源。

## 校验证书

网页分别显示离线 Verifier 结果与浏览器 `RAW_SHA256_CHECKED`；浏览器核对同一 Session 原始字节后才提供下载链接。将下载字节和界面给出的外部 SHA 带入：

```powershell
python -B -m runtime.runproof_runtime.effectwitness.lab_cross_domain_verify <downloaded-witness.json> --sha256 <external-raw-sha256>
```

正确 / 缺失 / 错误外部锚退出码分别为 0 / 2 / 3。原 RPF-59 用原 `pge_select_verify`。内容锚与本地源校验不证明签发者真实性、数据库外部 Authority、独立复现、两个真实模型 Target 或反馈因果优势。

本轮事实、源码/证据身份、验收与交付见 [RESULT.md](RESULT.md)；不要把启动说明当作已经执行的证据。
