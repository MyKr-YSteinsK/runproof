# SOURCE & RISK LEDGER｜固定SHA与限制

> 版本 **MIGRATION-2026-10-29-RPF79-rev1**；2026-10-29分支迁移资料，非canonical Project State、非main合并。CURRENT STATE按固定SHA和报告核验；TARGET INTENT保留批准需求；PLANNING CONTEXT不构成执行许可。
>
> 最高明确已接受离线阶段：**RPF-77**（75～77的接受来源为RPF-79正式Plan带入的上一Architect结论，不是本轮重新裁定）。**RPF-78：PARTIAL / PENDING_ARCHITECT_REVIEW**；**RPF-74/rev-4：PAUSED**。先审78再决定修订或下一方向。main=`bda0cd49e50e3181f604324e94877a24b9885334`，迁移Base=`240dbae75cc70f142c7c37a2a3994085063d7ccc`；最新未审查78=`d86528e9927ea2cd7a401da4865829c5a14bfcd2`。证据与验收分开，细节见10/14及SOURCE_EVIDENCE_INDEX.json。

## 固定远端报告索引

|RPF|远端报告与实现导航|审查/证据边界|
|---|---|---|
|40|[RPF-40 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/1556ab535d48661faa2c596c5bfea136c2404c68/spikes/rpf-40/RESULT.md) — 仓库/工具Spike；首轮rev1阻断与rev2分开|已读固定报告；本轮不重跑、不新授阶段接受|
|41|[RPF-41 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/ec490719176fe0e5504902671d62e1e06361d510/spikes/rpf-41/RESULT.md) — 订单SQLite效果/只读Authority|已读固定报告；本轮不重跑、不新授阶段接受|
|42|[RPF-42 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/6370775dda3be24ac45bb2a7cd00c9f401028247/spikes/rpf-42/RESULT.md) — 真实Explorer反馈与有限B0；观察性非因果|已读固定报告；本轮不重跑、不新授阶段接受|
|43|[RPF-43 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/238037a0b7499800325a91f3beeacf9161fc4d01/spikes/rpf-43/RESULT.md) — 结构化Witness/离线篡改拒绝|已读固定报告；本轮不重跑、不新授阶段接受|
|44|[RPF-44 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/1d2095bc26177b165f299e9ac1ec5edfab860983/spikes/rpf-44/RESULT.md) — 订单与运维共享Witness核心|已读固定报告；本轮不重跑、不新授阶段接受|
|45|[RPF-45 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/4bebed83abde36feb129a737335fb1d37cf13b1a/spikes/rpf-45/RESULT.md) — 受限Gateway与Web Lab|已读固定报告；本轮不重跑、不新授阶段接受|
|46|[RPF-46 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/69dfe3079f5778cf6e569e82cf8382e4e3ec04a8/spikes/rpf-46/RESULT.md) — 真实Explorer Web证据反馈|已读固定报告；本轮不重跑、不新授阶段接受|
|47|[RPF-47 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/ec325ee9dd80e6663beb74d32d129a34fb4df40f/spikes/rpf-47/RESULT.md) — 演示/材料审计，原PARTIAL保留|已读固定报告；本轮不重跑、不新授阶段接受|
|48|[RPF-48 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/8241ebb1a96be54ec56ce384b63b4789efc4dac9/spikes/rpf-48/RESULT.md) — 真实订单SDK Target；非任意框架兼容|已读固定报告；本轮不重跑、不新授阶段接受|
|49|[RPF-49 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/166707838969ba907baacff501d4459497bec8e4/spikes/rpf-49/RESULT.md) — 订单响应丢失后的自主对账|已读固定报告；本轮不重跑、不新授阶段接受|
|50|[RPF-50 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/b3271eaaf408dffa1ecd6f26f1b47fab5cede289/spikes/rpf-50/RESULT.md) — 确定性受控业务违规Witness|已读固定报告；本轮不重跑、不新授阶段接受|
|51|[RPF-51 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/151922a9b891ce9aa6f2d62639109e435f98c8ab/spikes/rpf-51/rev-4/RESULT.md) — rev4 direct JDK/readiness/真实HTTP，旧Partial保留|已读固定报告；本轮不重跑、不新授阶段接受|
|52|[RPF-52 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/3dfafb7fc286759f212166004e8558e02e0aba48/spikes/rpf-52/rev-3/RESULT.md) — rev3 SDK三工具协议恢复|已读固定报告；本轮不重跑、不新授阶段接受|
|53|[RPF-53 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/05b8c324fab376a23926b97a73e0fde6523ae373/spikes/rpf-53/rev-6/RESULT.md) — rev6真实Provider配置Target/Witness，旧修订不回填|已读固定报告；本轮不重跑、不新授阶段接受|
|54|[RPF-54 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/77cef321ab95383583b4a983d667d5e2c03722d0/spikes/rpf-54/RESULT.md) — 复用调查：只读投影与执行桥接分开|已读固定报告；本轮不重跑、不新授阶段接受|
|55|[RPF-55 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/227ffb020472633ce9b538ea33d5ad30a5e17bd7/spikes/rpf-55/rev-2/RESULT.md) — rev2受限配置实验三场景|已读固定报告；本轮不重跑、不新授阶段接受|
|56|[RPF-56 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/403ac5bf01c796602ef244cb3985043014de62eb/spikes/rpf-56/rev-4/RESULT.md) — rev4 Explorer/Target工具协议联合闭环|已读固定报告；本轮不重跑、不新授阶段接受|
|57|[RPF-57 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/e05aa7a5d9e902f2d64928ff61d3280c1cefdbd0/spikes/rpf-57/RESULT.md) — 配置双真实角色；观察性L2，不推因果|已读固定报告；本轮不重跑、不新授阶段接受|
|58|[RPF-58 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/03d13513ad958cf01455a39bede4f873ed474e21/spikes/rpf-58/rev-2/RESULT.md) — rev2跨域共享执行，Target受控|已读固定报告；本轮不重跑、不新授阶段接受|
|59|[RPF-59 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/c07236b72aea6690ba96d193178fc105f685ea50/spikes/rpf-59/RESULT.md) — 真实Explorer跨域选择；非双真实Target|已读固定报告；本轮不重跑、不新授阶段接受|
|60|[RPF-60 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/1125e4e6ddc0ec3a0e5820ce6095b663354a4ec8/spikes/rpf-60/RESULT.md) — 浏览器/Gateway/真实Explorer；受控Targets|已读固定报告；本轮不重跑、不新授阶段接受|
|61|[RPF-61 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/c5ebfb887336ca67b61270df9965f6b1ebbf2b9a/spikes/rpf-61/RESULT.md) — 申报文案/矩阵/分镜；无门户提交回执|已读固定报告；本轮不重跑、不新授阶段接受|
|62|[RPF-62 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/68572c05a52ff2258f50fb7c4488bff8e69ea61c/spikes/rpf-62/RESULT.md) — 真实配置Target UNKNOWN后只读inspect|已读固定报告；本轮不重跑、不新授阶段接受|
|63|[RPF-63 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/7896e9789015da946b5a057c620b2faa90b57318/spikes/rpf-63/RESULT.md) — 配置真实Explorer×Target两轮，L2=false；与64不同Session|已读固定报告；本轮不重跑、不新授阶段接受|
|64|[RPF-64 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/a4d956c0b69f7dacd34e842676d10c1898353cdf/spikes/rpf-64/RESULT.md) — 稳定TaskContext/DomainPort/SharedSession/WAL；订单SQLite+配置Java/H2 scripted SDK，Provider0|已读固定报告；本轮不重跑、不新授阶段接受|
|65|[RPF-65 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/4081b7b94484bac3c726e0bef22be273b7470839/spikes/rpf-65/rev-2/RESULT.md) — rev2真实ConfigPort装配/工厂修复及Target验证|已读固定报告；本轮不重跑、不新授阶段接受|
|66|[RPF-66 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/a8b1ca8bf895370c1d136c61301bb25f8e7a6c0d/spikes/rpf-66/rev-5/RESULT.md) — rev5严格响应协议，真实配置双角色2轮；L2=false|已读固定报告；本轮不重跑、不新授阶段接受|
|67|[RPF-67 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/87980e9c887a64fbb6bba486493655d0ec59cd94/spikes/rpf-67/rev-4/RESULT.md) — rev4真实订单Target接DomainPort，UNKNOWN后对账|已读固定报告；本轮不重跑、不新授阶段接受|
|68|[RPF-68 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/044588a575610ed68e86aa15f30da09e03f1eba5/spikes/rpf-68/rev-3/RESULT.md) — rev3逐槽/联合协议容量与宽裕预算，真实跨域共享会话|已读固定报告；本轮不重跑、不新授阶段接受|
|69|[RPF-69 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/86b033b94556c0931aa590c79e69fda672a4915e/spikes/rpf-69/RESULT.md) — 版本化公共ABI兼容/历史隔离；CORE_MIGRATED=NO|已读固定报告；本轮不重跑、不新授阶段接受|
|70|[RPF-70 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/ef95f0965ad8f2325892f6800a4528112f1a6e52/spikes/rpf-70/RESULT.md) — OwnerSource/Capability运行时接缝迁移，非整个Core泛化|已读固定报告；本轮不重跑、不新授阶段接受|
|71|[RPF-71 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/ed346dea7fc46fc289853ea673bfe100f8d0d8b7/spikes/rpf-71/RESULT.md) — BudgetPolicy与单原生WAL结算接缝|已读固定报告；本轮不重跑、不新授阶段接受|
|72|[RPF-72 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/a055bfa1844f1df7de459daf35107de7a3ae2d2c/spikes/rpf-72/rev-3/RESULT.md) — rev3父子SDK预算合同、LaunchSpec净化环境和Runtime恢复；旧失败保留|已读固定报告；本轮不重跑、不新授阶段接受|
|73|[RPF-73 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/22276cb6aa44eeaef46bcc576170eb317b73e7cf/spikes/rpf-73/rev-2/RESULT.md) — rev2版本化LaunchFactory/Runner环境合同，固定SDK scripted验证|已读固定报告；本轮不重跑、不新授阶段接受|
|74|[RPF-74 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/d5605c08af33c932f97529ae5b33228b56d8a113/spikes/rpf-74/rev-2/RESULT.md) — rev3报告PARTIAL（rev-2目录）；UNKNOWN后仍provider RESERVE；rev4现场PAUSED|rev3 PARTIAL；rev4 PAUSED（Plan+原工作树状态）|
|75|[RPF-75 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/163cdff3fdd96d6de87fa0fc31d19295994dc86a/spikes/rpf-75/RESULT.md) — 离线策略/反馈消融，OFFLINE_POLICY_SIMULATION_ONLY|上一Architect限定离线接受（Plan带入）；报告封存Partial不回填|
|76|[RPF-76 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/92a740504700b3ca1609f273039248ccecaffb84/spikes/rpf-76/RESULT.md) — 离线泛化/独立停止Oracle，128方法×2、78负控；holdout负结果|上一Architect限定离线接受（Plan带入）；报告封存Partial不回填|
|77|[RPF-77 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/240dbae75cc70f142c7c37a2a3994085063d7ccc/spikes/rpf-77/RESULT.md) — 离线效用/停止反例，121方法×2、78负控；不证明全面优势|上一Architect限定离线接受（Plan带入）；报告封存Partial不回填|
|78|[RPF-78 RESULT](https://github.com/MyKr-YSteinsK/runproof/blob/d86528e9927ea2cd7a401da4865829c5a14bfcd2/spikes/rpf-78/RESULT.md) — 离线fit-only校准/稳健拒绝；A08 FAIL，未审查PARTIAL|PENDING_ARCHITECT_REVIEW / PARTIAL|

完整branch、40位SHA、报告路径/URL、Git blob、内容SHA、读取类别和审查标签在SOURCE_EVIDENCE_INDEX.json；实现接口仅静态定位，禁止据此推断运行成功。引用原批准01/02/03以用户输入哈希为来源，不伪装为main已接受决定。

## 风险账本

74 UNKNOWN后模型预约与实体回执独立绑定未通过；78冻结负控fixture和完整测试失败，仍待审。75～77合成离线限定接受不推导真实双Agent/独立Issuer/因果优势。Source Hash非可信签名，same-service GET不等于独立第三方Authority，重验同证书非新环境复现。Owner/ABI/Budget/LaunchFactory虽逐步迁移仍含任务/SDK版本绑定，不称完整通用Core。

原RPF63格式FAIL和历史失败不修；旧Source/Witness不可拼接重签。Windows/净化环境/冷进程失败记录按revision分别保留。main旧状态不代表功能链不存在；Push非merge、部署、阶段接受或赛事上传。RPF61日期级记录不是本轮门户核验，精确时区/字段/提交回执未知。docs/reviews完全禁入，旧WAL/marker和74草稿保留。
