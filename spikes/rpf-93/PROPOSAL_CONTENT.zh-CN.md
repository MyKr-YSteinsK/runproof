# 创意提案逐页内容

PPTX 为可编辑候选稿；官方模板符合性尚未核实。来源同时写入各页演讲者备注。

## 01 RunProof EffectWitness

让智能体行动的业务效果可核验

- 受控实验 · 证据反馈 · 离线 Witness
- 面向智能体研发与可靠性评审

来源：https://github.com/MyKr-YSteinsK/runproof/blob/0dee6283f9a1c3a54edd79f78aabee784d562648/spikes/rpf-92/RESULT.md

## 02 问题：工具成功，不等于业务完成

- 退款请求超时可能发生在提交之后。
- 配置更新返回成功，也需要核对版本与历史。
- 工程师需要区分执行记录、业务事实与未知结果。

来源：https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/RESULT.md

## 03 三份合同界定一次实验

- Execution：记录工具调用、执行身份与结果。
- Effect：约束业务前后状态及禁止结果。
- Experiment：冻结候选、故障计划、预算与环境。
- 模型不能改写业务真值、验证器或发布权限。

来源：https://github.com/MyKr-YSteinsK/runproof/blob/0dee6283f9a1c3a54edd79f78aabee784d562648/docs/project/PROJECT_BRIEF.md

## 04 从受限探索到可核验证据

- Explorer 选择冻结候选  →  受控 Target 执行
- 业务只读 Authority  →  确定性 Oracle
- 已验证反馈  →  下一轮选择
- 版本化 Witness  →  离线校验与人工审查

来源：https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/RESULT.md

## 05 订单场景：确认一次退款

- 历史 RPF-60：虚构订单，金额 2,500 分。
- fresh SQLite：PAID → REFUNDED；独立只读收据为一张。
- 订单 Target 为确定性执行，不是第二个真实 LLM Agent。

来源：https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/RESULT.md

## 06 配置场景：读回版本与历史

- 历史 RPF-60：Java/H2 配置从缺失更新至 v2。
- 同服务 GET 读回版本及历史 [2, 1]。
- 配置 Target 使用 SDK scripted Fixture；计划故障未触发。
- 同服务 GET 不是数据库外部独立审计。

来源：https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/RESULT.md

## 07 历史运行：来源与角色分开

- RPF-60：真实 Explorer；订单确定性 Target；配置 scripted Fixture。
- 两轮反馈链可追溯；一次会话不证明因果或统计优势。
- RPF-57 是另一独立配置会话，不与此会话拼接。

截图标识：RECORDED · rpf60-session-ff259b8d1bef494b；历史展示，不证明本轮 live。

来源：https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/RESULT.md；https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-57/RESULT.md

## 08 故障与未知结果

- 分别记录故障计划、触发、观测和 Agent 暴露。
- 未知结果时保留不确定性，按合同做只读对账。
- RPF-74 更强的零新 Provider 预约约束仍待修复验收。

来源：https://github.com/MyKr-YSteinsK/runproof/blob/0dee6283f9a1c3a54edd79f78aabee784d562648/spikes/rpf-92/RESULT.md

## 09 可审查的证据与当前限制

- Recorded 页面可查看历史材料；两份历史 Witness 可离线核验。
- 哈希确认内容一致；签发者真实性与独立复现尚未建立。
- 当前 Golden Demo 冷启动未完成；新订单与配置实验未运行。
- 最近 CI：676 PASS / 12 ERROR / 5 SKIP / 539 UNAVAILABLE。

来源：https://github.com/MyKr-YSteinsK/runproof/blob/0dee6283f9a1c3a54edd79f78aabee784d562648/spikes/rpf-92/RESULT.md；https://github.com/MyKr-YSteinsK/runproof/actions/runs/42375255570

## 10 下一步与公开材料

- 先完善 fresh-owner 启动、故障归因和演示可复核性。
- 再探索真实 Target 扩展与有界对照；不预设研究结论。
- 代码与固定证据：github.com/MyKr-YSteinsK/runproof
- 参赛提交、身份与协议由参赛者本人确认。

来源：https://github.com/MyKr-YSteinsK/runproof；https://github.com/MyKr-YSteinsK/runproof/blob/0dee6283f9a1c3a54edd79f78aabee784d562648/spikes/rpf-92/RESULT.md
