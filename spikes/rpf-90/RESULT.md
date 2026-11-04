# RPF-90 / rev-1 — Router Failure Forensics

Status: PARTIAL（封存时 Git / hosted 尚未执行）；Path: A_CAPTURE_ACTIVE。

Base / branch：`6c1bfb1c51e7c9b2bd6027087fe2becc7190e81a` / `main`。本报告在唯一 focused commit 前封存，最终40位 SHA、Push、hosted 及 artifact 回执在最终聊天补足；不循环 amend。

## 实现与边界

精确差分1M+10A：仅修改 `.github/workflows/release-gate.yml`；新增独立诊断、15项测试与本目录8份源/报告。Router、Matrix、Handoff、Runtime、AGENTS、RPF89冻结源码全部未改。两个 always 留证步骤插入 Repository Checks 后；去掉这两个新增步骤，原 workflow 原始字节完全相同。YAML结构、所有run块 Bash -n、触发器、contents read、concurrency、35分钟、原step顺序及最终 RPF87 enforce 均保留。

G0完整通过：现场根目录/main/HEAD/upstream/HTTPS远端一致，tracked/index干净；7份源码pins、10个create-only空占/ignore/大小写/reparse、worktree、ACL真实exit0和push副作用均核实。最初用git hash-object过滤两份原为CRLF的Git blob导致检查失败；随后只读核验工作树与Base原字节完全相同，修正检查方法后才创建唯一owner。无伪追认。

诊断使用固定公共元数据生成ID/路由预期，不导入Router代码。当前Run ledger严格解析、聚合及进程收据检查允许真实FAIL。输出分列ERROR与FAIL；模块协议错误码可靠时只确认Router协议层，绝不据此声称方法异常根因。模块错误文本未知时仅固定REDACTED枚举，原因未决。坏/缺输入exit2，不输出PASS。目的路径验证失败时因无可信输出目标，仅stdout固定错误并exit2。

## 实际验证

冻结前两次必要聚焦控制分别4项、5项，均exit0。AST/显式owner cfile编译、严格JSON、YAML、Bash、git diff --check均PASS；冻结三份实现字节及两份全新合成输入。冻结后正式全套**仅一次**：15 tests，15 PASS，0 FAIL，0 SKIP，exit0，1.093秒，未超时；日志2630字节，SHA256 `41f6232b6a11b545b81229cb30dcd5cff68543a993448ceb44c10b4742b11a1d`。独立stdlib子进程重读新合成数据和冻结源hash，PASS。

负控覆盖676/12/5/539、688/5/539、timeout/truncated/nonzero exit/partial ERROR/模块INVALID/缺error，source drift、1232唯一ID、route/actual/executed、聚合假绿、duplicate JSON/nonfinite/非法Unicode、超限、路径别名/旧owner/覆盖、真实Windows junction与硬链接，以及敏感文本不进入投影。只启动纯诊断/独立读取与junction创建工具；没有Router/Runtime测试调用。

未向hosted focused safety追加本地合成测试：其明确owner和Base快照前提仅在本任务本地授权根内满足，避免扩大CI写入位置；同一冻结脚本已本地正式执行。既有hosted安全测试不变。

## Gate 与未完成事实

G0、A01–A07、A10：PASS（按实际本地控制范围）。A08、A09：NOT_RUN_AT_SEAL，Gate枚举NOT_RUN；最终Git与hosted实际回执由聊天补足。所有收据真实保存于本任务新owner，旧私有owner/WAL/证书与docs/reviews、docs/project、docs/history均未访问。

历史Run41806063467的12 ERROR具体方法/根因仍UNAVAILABLE；本轮不重试旧Run，不能靠合成12项追认旧根因。新的自然Push Run即便出现ERROR，原Handoff/Barrier继续真实FAILED；诊断上传成功只代表观测链完成。若新Run无ERROR，只能说本次未复现。

Provider、SDK、Key lookup、业务HTTP/写入、Java本地、新Docker本地、数据库连接、模型费用均0。一次普通Push自然触发既有canonical CI的原有依赖/实验边界不变；无额外dispatch/rerun/发布/部署。RPF74/81不恢复；RPF89正式35项不运行；不推广required ID，不推进阶段。TASK_COMPLETE/EVIDENCE_ACCEPTED/STAGE_ADVANCED由Architect裁定。
