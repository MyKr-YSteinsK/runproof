# RPF-100/rev-1

本机切片通过，封存时 Git 与 hosted CI 为 NOT_RUN_AT_SEAL。基线为 6fb42bae36af308ff2a2857e2d980be8f04252df。

采用独立 SQLite 产品层，共享冻结合同、持久会话账本和策略门禁，分别使用 OrderPort 和 OpsPort。旧 Oracle 作为纯函数复用。两域的业务写入各为一次独立事务，Authority 通过各自的新 query-only 连接读回。预算限两次 live 会话，每域一次写入。中断后保留写入意图并停止重放。

最终源码的 Edge 会话 `83e957b81d12461b90e3c15859d75e32` 实测订单退款、提交后 UNKNOWN、唯一收据只读确认、反馈驱动 SELECT_OPS，再提交并读回配置更新。两个业务合同均为 CONTRACT_SATISFIED_IN_RUN。轮一反馈 SHA-256 为 `2336ada130502efb222e31497d8991e7cac7d95e22945ee718780545e1410392`，所选配置合同 SHA-256 为 `49a5cf1d5a6c9b87250be1a72f481dc506be9e846900c2cdf2391b354715f67d`。数据库保留供只读核查，Provider 预约为 0。

浏览器下载 Witness，SHA-256 为 `19fe0ecaf8bfb97a33e7d2e4bc7c1a0d5d7a0399386b355b53dd926ee9518952`。独立 CLI 用该传输哈希比对后返回 VERIFIED_ANCHORED，Issuer 为 NOT_ESTABLISHED。哈希来自同一下载会话，证据范围是内容核验与传输比对。

六组后端测试通过。真实身份不匹配负控在订单提交后进入 RECONCILE_REQUIRED，保留一张订单收据且 Ops DB 不存在。并发幂等、进程中断、持久检查点失败、篡改和 HTTP 准入均验证。Edge 在 1440、1024、768 验证布局和会话事件，服务停止后显示 UNAVAILABLE 并禁用写入，重启只读恢复且剩余预算保持为 0。71 项前端测试、类型检查、普通及 Recorded 静态构建和文档校验通过。旧静态 ZIP 原件保持封存，回归使用本任务隔离目录中的新构建。

规则策略演示覆盖两域本地闭环。真实 LLM、真实外部配置系统、独立第三方签发、统计因果优势和发布仍待各自验收。
