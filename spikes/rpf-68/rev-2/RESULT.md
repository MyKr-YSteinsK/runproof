# TASK_RESULT — RPF-68 / rev-2

Status: BLOCKED

Base `b68c6a4452a8d98d78d2ac0e1d4433bcfa4d7165`；branch `codex/rpf-68-rev2-slot-budget-shared-session`。源码commit `dfc159ce2bb2981cb393bbf3c93060bbd540233c` 已普通push，Git与GitHub API双读一致。`EVIDENCE_ACCEPTED/STAGE_ADVANCED=ARCHITECT_REVIEW_REQUIRED`。

## 结果

已按授权修改7个RPF68源/测试，新增独立rev2入口和报告；配置4/5为4600/4300，34100可达/35000总池/11请求，900余量不能另用。Context、Driver票据、replay、Verifier与Admission源码门禁共用版本表及scope哈希。Source LF `f98569823a6608314d8c001e9d3e311091c283e721052605adf0eea6c7825593`；Verifier v2；raw/LF/mtime与helper SHA见preflight。**尚未执行正式Source Freeze。**

### 免费正控

- 普通双域四候选配对：真实固定SDK、Java/H2与SQLite、同Context/单WAL、独立Oracle、完整回注与反馈通过。
- 旧反例配置4 `2706<=4600`；配置5 `2105<=4300`；订单3局部正控 `2301<=2600`；订单4完整receipt加mixed512 `2888<=4200`。Explorer原ToolCall ID160及完整反馈注入通过。
- 最终源码 **12 focused / 498 full**，0 errors/0 failures，full仅原2项Docker unavailable skip；完整进程1次（限2）。Windows父Python 3.14.6，fixed child3.12.13 / PydanticAI2.57.0 / OpenAI3.35.1。
- **140**种synthetic重锚拒绝（保留118、增加22预算/阶段/跨域控制），逐件CLI exit3；合法0、无锚2、错锚3。19历史原证书+Reviewed/Public入口及额外RPF67真实原件原SHA全部exit0。

### 合法输入反例：P1 FAIL

| 案例 | 槽 | 不等式 | 结果 |
|---|---|---|---|
| max ID160 + refund mixed512 + 完整UNKNOWN ToolReturn | order3 | `460+1327+512+512=2811>2600` | pre-send拒绝 |
| first fixture prompt达到首请求允许上界1516 | config2 | `1516+1033+512+256=3317>2400` | pre-send拒绝 |
| 8192byte合法JSON参数，仅尾部空白、语义不变，SDK原样回注 | config2 | `430+8425+512+256=9623>2400` | pre-send拒绝 |

所有usage都是**合成fixture严格解析值，不是真实Provider token测量或账单**。高prompt案例证明当前验证器接受范围下的反例，不证明真实tokenizer必然可达1516。参数8192和ID/content组合均由实际固定SDK执行产生后续请求；没有降低guard/output、去空白、截断消息或改候选偷过门禁。局部终止正控与旧2706通过都不等于最大输入充分。

## 业务、费用与清理

真实Provider **0**，Provider Key未读，正式预约/已知真实usage为0，模型费用0；invoice `NOT_QUERIED`、官方本次核价 `NOT_RUN`。单独预算组件试验的11张synthetic票只验证34100算式，无网络、不是正式票/会话/Witness。

订单反例已在受控新SQLite提交一次2500 minor虚拟退款；独立mode=ro Reader成功读回唯一receipt，但SDK未final stop、第二域未DomainVerified，不算共享Session成功。早期配置反例0POST、目标v2未建立，只有只读核对观测。Agent真实判定`NOT_RUN`；fixture未完成；Platform=`PLATFORM_PRE_SEND_BUDGET`；Oracle按上述案例分列。

拒绝receipt/WAL/DB/未结SDK/Host/Trial/Session票原位保留；无Provider UNKNOWN（没有网络发送），不回收或伪结票。SDK/JVM有原清理OS端口bind、thread/key释放及晚次PID读回；详见cleanup记录。失败free context未保存SDK Host端口坐标，不能声称所有历史端口另有晚次外部连接试验；初次max CLI父PID未保留，wrapper exit1/FAIL原样记录。没有为补证据重跑正式根。

正式Context/WAL、Source Freeze、metadata/cold/admit/live、真实Witness与≥30真实负控均**NOT_RUN**，公开Witness路径不存在。Windows父3.12 `NOT_ESTABLISHED`，Hosted Ubuntu3.12/CI、main merge、deploy/release、赛事提交 `NOT_RUN`。

## Gates

| Gate | 状态 | 范围 |
|---|---|---|
| G0 | PASS | 精确Base/remote/新根/10路径/SDK/JAR/权限 |
| R2-A01 | PASS | P0/synthetic新owner/ABI/单WAL/双Port；正式Context未建 |
| R2-A02 | PASS | v2逐槽表/34100/35000/slot proof/组件重放一致；正式Admission未跑 |
| R2-A03 | FAIL | 局部最大正控通过；仍有三类合法协议组合反例 |
| R2-A04 | PASS | 最终源12 focused/完整Runtime/140负控/历史锚 |
| R2-A05—A08 | NOT_RUN | P1失败，不冻结、不付费、不生成真Witness |
| R2-A09 | PASS | 安全停、无网络/Key、资源清理、历史/private保护；观测限制单列 |
| R2-A10 | PASS | 报告/决策完成；源码push双读一致，最终回执SHA在对话交付 |

## A. VERIFIED_FINDINGS

1. 预算升级不止CAP表：contracts派生34100、Context完整冻结表、replay拒绝旧30400、Driver及独立Verifier验证scope；组件11票无网络达到34100。证据：`budget-aggregate-result.json`摘要及slot-budget诊断。
2. 固定SDK局部终止最大正控通过，但order3/config2合法组合失败；三个不等式、实际请求SHA/receipt SHA及源码/退出码见slot-budget与verification诊断。
3. Driver.parse允许8192byte参数，SDK不会移除其合法空白；config2 suffix8425实测。来源：`pge_r68_driver.py:parse/Driver.completion`、argument-envelope记录。
4. 最终源focused/full/140synthetic/历史锚通过；四个禁止修改的R68模块、rev1公开结果与历史bridge保持原字节。当前与历史bridge SHA分列。
5. 真实共享会话是TARGET_INTENT，本轮未发生。所有事实分类、代码位置/函数、输出SHA及实际命令在architecture-decision的VERIFIED_FINDINGS中逐项列出。

## B. CODEX_ENGINEERING_JUDGMENT

1. **逐槽预算与协议长度未闭合（HIGH）**：晚期槽修好后早期/订单槽继续失败。支持为三个SDK反例；反证/缺口是真Provider可能只用短ID/content，尚无真实分布。最便宜下一检验是有限字段×阶段×可信usage范围的可达prefix不等式矩阵。
2. **语义安全与原字节容量是两条约束（HIGH）**：参数值完全相同，8192byte JSON空白仍膨胀回注。其他SDK可能规范化，但本固定版本实测保留。下一试验先审计合法编码上限，不在本轮擅自strip/压缩。
3. **负控全绿不能替代合法路径容量（HIGH）**：140攻击和普通四配对与max FAIL并存。未测完整状态空间/Provider性能；下一任务把两类覆盖单独验收。
4. **公共Core提取时机仍需决定（MEDIUM）**：7个文件延续两域，但guard213行及owner constructor注入债保留。若领域长期有限，task-owned可能更省；没有第三域/迁移成本实测。完整observation/root cause/evidence for/against/反例/impact/confidence/cheap test见结构化报告。

## C. ALTERNATIVE_PATHS_AND_TRADEOFFS

| 路线 | 益处/代码 | 复杂度 | 安全/历史成本与最坏失败 | 当前选择 |
|---|---|---|---|---|
| task-owned联合协议/预算验证 | 现contracts/driver/session/verify/test，先解决已复现约束 | MEDIUM | 新协议/预算需批准；只改部分CAP会再次失败 | 优先 |
| versioned Core | 集中owner/Source/Budget/Verifier/guard，减少重复 | HIGH | ABI/历史兼容、权限/crash回归；可能只搬走同一矛盾 | 可规划，暂不实施 |
| 外部Agent/MCP/Web/第三域 | 检验外部接口 | HIGH | 新凭据/网络/异步UNKNOWN/不可信工具；放大未校准预算 | 暂不实施 |

具体code touched、dependency、worst failure、why now/not now见architecture-decision；仅实现一个task-owned v2方案，没有并行择优或越权Core改造。

## D. NEXT_DECISION_RECOMMENDATION

最高价值下一目标：**先形成可满足的联合协议长度/逐槽预算合同，以0Provider固定SDK及约束矩阵验证，再另行准入真实共享会话**。8192参数、mixed/ID及可信usage是跨阶段约束，不能靠追加相似专属代码或单点加槽解决。反对路线是优先Core ABI/guard抽取；仅当Architect以补丁集中化为首要目标并批准迁移/兼容范围时转向，仍不得跳过容量门禁。

需要新增批准：任何接受协议/编码上限/序列化规则或CAP变更、新正式会话费用；若Core则新路径/迁移；外部域/网络/凭据/部署另批。没有创作或执行RPF-69。registry/instructions/Oracle/round只有当前两域，不能声称任意外部第三域通用。

## E. POTENTIAL_GENERALIZATION_DEBT

- VERIFIED_DEFECT：合法协议输入与冻结逐槽表不相容，三个实际SDK反例。
- TECHNICAL_DEBT：guard213行、owner constructor注入；旧/当前Source双轨；单WAL上仍固定两域、无并发/第三域证据。
- OBSERVABILITY_GAP：真实usage/价格/账单/终止率未测；失败Host端口晚次坐标与初次max父PID缺失；只有命令墙钟，未隔离阶段性能，不能当SLA。
- FUTURE_RESEARCH_QUESTION：外部不可信Agent/MCP、异步工具、独立Issuer与第三域Oracle能否保持同一身份和最小权限。

标准化明细与支持/限制见architecture-decision。rev1旧反例通过≠rev2最大证明，合成usage≠真实计费，两个受控域≠外部通用能力。最终接受/阶段推进由Architect独立审查。

## Git 交付回执

源码提交 `dfc159ce2bb2981cb393bbf3c93060bbd540233c` 已普通push；Git ls-remote和已连接GitHub REST API均读回该SHA。父分支 `b68c6a4452a8d98d78d2ac0e1d4433bcfa4d7165` 与main `bda0cd49e50e3181f604324e94877a24b9885334` 未变。最后仅提交本rev2公开回执，最终receipt SHA由对话在push及双读后报告，不做自引用amend。剩余工作树仅允许原 `?? docs/reviews/` 顶层标记，未进入其内容。没有PR、merge、CI dispatch、deploy/release或赛事提交。
