# RPF-89 / rev-3

按已测热点将同一次 RPF88 source closure 的逐文件 Git 调用合并为一个 HEAD 批量核验和一个 cat-file --batch；每次都重新核对64份源，未缓存跨调用结果。原 RPF87/88、Router、Handoff 不变。workflow baseline 更新至 RPF90；local synthetic owner 仅限 rev3 新独占根。

测试保留原35 IDs及全部断言调用，新增3项批量协议/漂移/HEAD边界控制。正式38项只执行一次；原断言、物理SQLite、journal、Guard、时钟、copy/reparse负控均保留。完整证据见 RESULT 和 JSON。

本地测试须显式 RPF89_OWNER，且该 owner 已保存本任务冻结 candidate-workflow.yml；不会自行创建或读取旧 owner。不要在无新合同情况下重跑旧全套。Hosted 输入只取当前Run：原 Router/Handoff、RPF86/87/88与本轮postcheck。先postcheck、后RPF88、再assess；原Barrier及新Barrier均保留always，均拒绝发布。

本地711/5/516仅合成控制。只有真实同Run hosted证据读回后才可结算18项。仍NO_RELEASE/NO_DEPLOY，不代表独立Issuer或Kernel sandbox。
