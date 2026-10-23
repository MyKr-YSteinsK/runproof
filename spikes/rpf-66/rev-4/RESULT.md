# TASK_RESULT｜RPF-66/rev-4

**Status: Blocked**

## 结论与停止依据

G0通过；P1发现一个未被Plan列出的第四处256硬上限。原受保护的 `runtime/runproof_runtime/effectwitness/config_live_runtime.py:579` 定义 `_validate_provider_response(data, *, fixture=False)`，在628–629行直接要求 `usage.completion_tokens <= LIMITS["max_output_tokens_per_request"]`，常量来自 `config_live_contracts.py:52`，值为256。函数没有请求上限参数。

本轮以原函数、未修改的响应、未修改的全局常量实际执行12个离线夹具：stop输出0/128/256接受，257/300/512/513全部 `PROVIDER_OUTPUT_TOKEN_LIMIT`；length输出128/256/512全部 `PROVIDER_CHOICE`；content_filter/aborted输出128均拒绝。每例输入与源文件前后相同，0 transport、0 Provider、0 Key访问。

Plan §4.1要求原严格解析器继续工作并禁止旁路；§5.2要求扩展cap内合法stop和known usage PASS。因此仅在六个允许文件里修改Host出站/Broker预约，无法让原解析器接收257–512的合法结果。只测试256以内或等待真实512请求恰好生成短响应，均不能证明扩展输出能力。按§0、§11停止P2/P3，不进行收费试验。

## 源码、身份及技术决定

- 仓库：public `MyKr-YSteinsK/runproof`；origin已核实。
- 唯一Base：`862e7ad4ee5597edc1b32d951aa57c48344393a9`；新分支：`codex/rpf-66-rev4-terminal-output-budget-contract`。
- G0核实六个旧文件tracked/无改动，九个新路径在磁盘、index、Base及GitHub均不存在，新分支本地/远端未占用；独立忽略根create-only，祖先无reparse点，磁盘空闲123.46GB，六个loopback socket同时可绑定后全部关闭。
- 父Python3.14.6 SHA与固定SDK child executable SHA符合Plan；Java17.0.12仅通过JDK release文件核实；原授权JAR为66,981,576B且SHA匹配，未复制。没有运行SDK metadata/cold，未宣称重新验证包RECORD。
- FROZEN保持：原解析器、SDK、全局LIMITS、六个既有R66源/测试全部未改。
- RECOMMENDED的局部completion复制未实施；没有引入复制债或魔术hook。
- DELEGATED调查发现接收端额外上限；拒绝吞掉输出错误、重写usage、全局常量切换或未经授权换解析器。
- v4 ABI/Source Map/Verifier未实施、未冻结；仍在Base实现身份上做只读调查，不把rev-3身份重标成v4。诊断源的raw SHA见verification，既有六文件及三受保护源的raw/LF SHA见preflight。

## 预算与运行范围

目标数组 `[3000,2400,2400,2400,2800,2000]` 每轮15,000，加Explorer每轮2,500，两轮合计35,000。normal终止stage4仅当input≤1888才容纳512；suppressed stage5例子2048+512=2560≤2800；stage6总cap下降到2000。数学成立，生产执行/回放尚未实施。

实际SDK inbound、parent outbound、Provider request/responseID/ToolCallID、usage及票据列表全部为空；metadata/cold/session/trial/JVM/SDK/Provider/业务HTTP/POST/health计数均0。本轮没有读取Key、没有预约tokens、没有账单查询；没有读取、返还或回填旧未决票据。官方价格尚未核实，paid admission阻断。SDK原始256与拟议parent512均未产生本轮实传输证明。

Oracle、Tool回注、故障四状态、第一反馈、第二轮、L2均NOT_RUN；没有完整双角色证据，`dual-agent-witness.json`必须不存在。未创建Session WAL、Context、Source Freeze、paid-gate或live-admission。无子进程与业务Key需清理，G0 socket全部关闭。

## Gate与验证

| Gate | 状态 | 范围 |
|---|---|---|
| G0 | PASS | 精确Base/remote/branch/path/ignore/pin/无push部署副作用 |
| R4-A01 | NOT_RUN | v4 Context/ABI/单WAL未实施 |
| R4-A02 | FAIL | 原解析器阻断扩展合法输出，512实传输证明未实施 |
| R4-A03 | NOT_RUN | 仅预算数学PASS，未完成生产预约/Verifier |
| R4-A04 | FAIL | 完整免费实施门禁未建立，不能进入P2 |
| R4-A05～A08 | NOT_RUN | 无Freeze/metadata/cold/paid/真实Witness |
| R4-A09 | PASS | Provider/Key/业务副作用0，旧根与用户目录保护 |
| R4-A10 | PASS | 首提交普通push及Git/GitHub API双读一致，最终receipt另报 |

离线诊断init exit0、verify exit0，admit按预期exit3且资源0。12例属于协议调查夹具，不是focused24、≥60重锚语义攻击或真实证书负控。focused/full/历史18/Reviewed/Public均NOT_RUN：在协议前置冲突明确后未运行不能解锁P2的昂贵门禁，未复用rev-3 full为本轮PASS。Windows3.12父全量NOT_ESTABLISHED；Ubuntu3.12 hosted CI NOT_RUN。

## 交付、保护与下一步

本轮只创建rev-4的8个白名单公开文件，条件Witness不创建；调查原件在本轮ignored根。`docs/reviews/`仅根级status标记，未进入/读取/列举/hash；所有旧ignored runtime根均未访问。Project State、旧证书/源码/Verifier、SDK/JAR源、Workflow均未改。main及旧分支不合并，不PR、不部署、不dispatch。

交付采取本分支focused commit与普通push，并以fresh ls-remote及GitHub API双读。最终SHA在聊天回执提供，本文不回填自身最终SHA。

下一版合同需明确授权一个请求级严格响应输出上限：可允许原验证器接收显式cap参数，或明确允许任务拥有的完整严格验证器承担cap相关验证并调整“必须原解析器”条款。仍须保留length拒绝、usage一致性、ID/Tool/字段校验、UNKNOWN停写及完整Source绑定。当前合同下不采用这些越界方案。

交付核实：首提交 8dae5d8a99f28aa4abedec8104e38d170a050e45 已普通push；fresh ls-remote与独立GitHub API均返回该SHA。main/旧rev-3远端SHA保持原值；本分支Actions runs=0。JSON解析5件通过、条件Witness不存在；metadata/cold/admit/live均实测exit3且未消费资源。staged及unstaged diff --check通过。后续仅提交本交付回执，最终远端SHA在聊天单独报告。
