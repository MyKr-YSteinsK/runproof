# TASK_RESULT｜RPF-67/rev-3

Status: Partial

## 结论

- G0=PASS；R3-A01=PASS；R3-A02=PASS；R3-A03=PASS；R3-A04=PASS；R3-A05=PASS；R3-A06=FAIL；R3-A07=FAIL；R3-A08=NOT_RUN；R3-A09=PASS；R3-A10=NOT_RUN。
- Base=`7858badb829265b738fc7ccf2de31711df51d9c8`；branch=`codex/rpf-67-rev3-http-fixture-runtime-recovery`；ABI=`rpf67-order-real-target-v3`。
- Source digest=`02739974284fc41975a60b3160d41f938f080338a2e3e7517d2724c4a3fec001`；raw/LF Source Map 25项及冻结身份见 [preflight-diagnostic.json](preflight-diagnostic.json)。

## 旧 HTTP Fixture 修复与源演化

- 仅修改 ConfigTargetFixtureHost.start 内部的有界请求体消费/关闭路径，鉴权顺序、400/405 JSON和sticky首码不变；不解析未认证体、不进入业务路径。正常200仍用原ready/completion/tool处理。
- body上限65536 bytes，单次读取绝对deadline250ms；拒绝重复Length/Transfer-Encoding歧义。keep=False只消费字节；短体、停顿、巨大声明和客户端断开不能无限阻塞单线程Host。共享helper也限制正常路径读体，保证认证成功但短体的拒绝路径有界；正常合法消息语义保持。
- 未读请求体+连接关闭仍是源码支持的竞态假设，不声称唯一Windows内核原因。没有sleep、重试、吞客户端WinError、修改系统策略或削弱旧断言。
- 历史RPF52 bridge SHA=`6dd3fd4b49adb689b310557340e2bfc380cb10726e63db7519ecda6bd318e59d`；当前新SHA=`1224364c7b4db5585d3e24c1def79f09fb5c3f3ef96cc3d4ed35bd699c1820a0`，两者分开保留。旧证书/Verifier/Source Map未改，原证书重验不证明旧证书在本轮新源码执行。
- Baseline一次10旧测试，errors=5；最终联合focused=52，exit=0。20个fresh fixture×2次wrong bearer、错误Host/Origin/Content-Type/route/JSON/GET、异常长度/短体/停顿/abort和正常3回调，逐项见 [http-fixture-diagnostic.json](http-fixture-diagnostic.json)。
- 原脚本真实固定SDK P1免费验收：PASS，Python3.12.13/PydanticAI2.57.0/OpenAI3.35.1，4 fixture响应/3回调/Provider0/Java0，未修改旧脚本。
- 初步新增测试5项有1 error/1 failure：bytes-only parser调用和原INVALID_JSON期望写错；只修正新测试。20-fixture/有界体生产修复本身通过；原日志保留。

## 免费门禁与源冻结

- 单个完整Runtime：PID=22748，command=`python -X utf8 -B -m unittest discover -s runtime/tests -p test_*.py -v`；tests=479/errors=0/failures=0/skips=2/exit=0，734.186s；snapshot=`.local\rpf-67-rev-3\snapshots\full-7dda469d53`。
- 合成重锚 69 类；CLI0/2/3；19历史原件及Reviewed/Public共21个原入口，详细命令/外部raw SHA/exit见 [verification-diagnostic.json](verification-diagnostic.json)。历史原件保留原字节，不回填源身份。
- 固定真实订单SDK免费mixed-content回调/一次SQLite退款/一receipt/独立Reader：PASS；这是SYNTHETIC_TEST_ONLY，未升级为真实Provider。Driver、Child/guard及旧业务模块原字节不变。
- 新版Context/Port/Verifier绑定rev3 Source Map，额外负控覆盖历史hash冒充新源码、历史源改名和HTTP错误码翻转；mixed-content策略保持rev2受限版本。
- Source Freeze=FROZEN；formal metadata=PASS (1)；cold=PASS (1 child; Provider0/formal refund0)；paid admission=PASS。冻结后绑定源与private helper不得改字节。
- Hosted CI=NOT_RUN；Windows父Python3.12=NOT_ESTABLISHED；主父Python3.14；Docker两个原skip如实UNAVAILABLE。

## 唯一真实订单 Trial

- Session=1/Trial=1/Provider=3/Explorer0/Java0；永久预约tokens=8200；预约guard=¥0.0436635；已验证usage tokens=2686；known部分usage guard=¥0.0160695，非真实账单。
- Agent=READ_ONLY_RECONCILE_TOOL_EXECUTED_FINAL_CONFIRMATION_NOT_OBSERVED（未证明Agent失败）；Platform=ERROR_PRE_SEND_INPUT_BOUND；Oracle=CONTRACT_SATISFIED_IN_RUN；unknown=False；all_settled=False。
- 每张TARGET票的canonical request SHA/输入上界/output cap/原合法响应ID/usage/settlement，以及ToolCallID、ToolReturn、SQLite receipt/独立只读Authority、故障四态和cleanup见 [session-summary.json](session-summary.json)。
- Provider shape先于严格解析落盘，拒绝时只有枚举/有限结构/ID哈希和UNTRUSTED usage hint；HTTP/transport/decode未观察到shape则标NOT_OBSERVED。rev1 FINISH_SHAPE原arm仍不可追溯，rev1 UNKNOWN/旧账本不读改。
- 真实Witness：NOT_RUN，公开路径必须不存在。

## 本轮真实 Trial 停止诊断

- 唯一Trial实际Provider3：三次均为合法mixed content + 单工具，content长度46/133/130 UTF-8 bytes；Parser条件全true、原样SDK回注、usage已严格验证并分别settled。没有Provider-format拒绝，也没有第4次HTTPS发送。
- 模型自主inspect→refund→只读reconcile；reconcile的COMMITTED结果已返回SDK，但携带该ToolReturn的第4次请求未发给Provider，不能称模型已依据其完成确认。一次SQLite 2500 minor CNY退款、一receipt，fault四态均true，退款后没有新增写。Controller最后以FAILURE_READ_ONLY_RECONCILE独立读到REFUNDED/receipt，纯Oracle为CONTRACT_SATISFIED_IN_RUN。业务事实成立，SDK最终终止响应未取得，不能生成完整成功Witness。
- 外层SDK_PROCESS_REPORT的具体Host原因是预发送INPUT_BOUND；不是模型违规、Provider未知usage或未证明的网络失败。Agent只读工具选择/执行已观察，COMMITTED回注停在SDK，模型最终确认未观察；Platform ERROR。
- 第4槽CAP=2600，output=512，故input_upper必须<=2088。上一可信prompt=982、suffix margin=512，可容纳新suffix<=594 bytes；从失败分支只能推出input_upper>=2089、suffix>=595，具体数值未落盘，禁止精确回填。
- 已验证prompt2391 + completion295 = total2686 tokens；不可退预约8200 tokens、预约guard=¥0.0436635、known usage guard=¥0.0160695（非账单）。Provider三票均known/settled，provider UNKNOWN=false；session-1/trial-1/sdk-1/host-1四票仍未完成，保留而不伪结算。
- Metadata1/cold1/Host1/SDK1、authority4、sqlite_setup1/refund1；正式SDK PID30596、cold PID24040均已由OS确认退出，Host thread/port3821关闭、临时Key引用释放。DB/WAL/shape/SDK错误报告保留。
- Witness路径不存在，真实Witness CLI/重锚控制NOT_RUN；69类合成负控不冒充真实原件控制。Source Map25项及11个冻结helper raw bytes均保持，未改码或重发Trial。

## 交付、清理与边界

- 修改existing 7项；新增9项；精确路径、G0、source/helper冻结及所有尝试见machine diagnostics。
- task-owned PID/thread/loopback port/临时key引用按新WAL、SDK report和OS查询核对；新DB/WAL/receipt/source snapshots/失败和取消日志留ignored `.local/rpf-67-rev-3/`。旧runtime、SDK安装、用户保护目录不复制/清空；原固定SDK仅进行获准pin及只读执行。
- source commit=`NOT_RUN`；Git交付尚未完成。
- main与rev2父分支保持G0 SHA；无PR/merge/rebase/force/tag/release/deploy/CI dispatch/赛事提交。用户docs/reviews仅根级status marker，未进入/读取/列举/暂存。
- Explorer NOT_RUN；L2 NOT_TESTED；cross_domain_same_session NOT_PROVEN；web NOT_INTEGRATED；causality NOT_PROVEN；independent_reproduction NOT_TESTED；issuer NOT_ESTABLISHED；production_release NOT_AUTHORIZED。不拼接旧Config/Order证明共享会话，不声称第三方签名或生产事实。
- TASK_COMPLETE由Codex据Gate回传；EVIDENCE_ACCEPTED/STAGE_ADVANCED仍待Architect后审。

## 建议（不扩大本轮范围）

- 建议进行 Development Architect Checkpoint Review：多轮返工已涉及历史源码身份演化与完整回归成本，应审查其长期兼容策略。
- 在未来共享双域之前，明确区分“历史证书按原件校验”和“当前源码重新执行”的身份合同；保留本次Windows原始socket/短体/关闭测试为聚焦回归。
- 20个fixture是有界回归证据，不能当作长期故障率估计；后续实验额度和架构变动须由新编号Plan决定。

### 针对本次停止的后续建议

- 下一编号Plan在保持总15000 tokens、¥0.45守卫和不重试规则下，用真实prompt基数与完整只读receipt suffix安排各阶段CAP；先补可选reconcile后的临界预算免费SDK回归，再考虑新的独立Trial。
- 增加无原文的预发送拒绝收据，记录ordinal/stage/可信prompt/suffix bytes/output cap/slot cap；当前第4次精确上界缺失必须保留。不要缩短512保护、跳过终止响应或放宽Verifier来追求成功。
- 建议先完成同域终止与Witness缺口，再开展共享Explorer/双域抽取；上述均为后续建议，未在本轮执行。
