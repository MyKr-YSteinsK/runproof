# RPF-91/rev-2 主结果

Status: PARTIAL；Path: B_UNACTIVATED。报告在Git与CI前封存，A08/A09=NOT_RUN_AT_SEAL。

Base：`3fb0294c5087eee8fa0d0196fe610048bc023585`，main。G0通过：100项来源身份、实际远端、精确路径、忽略和ACL已检查；补充授权的候选 `runtime/runproof_runtime/effectwitness.py` 工作树与Base均不存在，只做元数据检查，未读内容。source-map闭包84个已授权文件，无新增存在依赖。

静态A01：R71/R72R2/R72R3原方法总数19/29/35，指定每代18项均存在且路由DEDICATED_RUNNER；54个精确ID见cohort-inventory.json。实际运行0/54，Guard、SQLite、独立验证均NOT_RUN。

现有RPF89 `workflow_source()` 已真实执行：当前workflow可接受，将本Plan要求的RPF91 Pilot和上传两步骤插在其assess之后则拒绝 `WORKFLOW_UNAUTHORIZED_DELTA`。RPF89的源码不在本Plan可修改范围；更改其白名单或伪装步骤将违背合同。只读取证控制1项PASS，exit0，见counterexamples.json；因此选择B，保留当前workflow原字节，未启动正式Pilot。

G0/A01/A10 PASS；A02–A05 NOT_RUN；A06 NOT_APPLICABLE；A07–A09 NOT_RUN_AT_SEAL。原覆盖711/5/516没有新增准入；旧534和新516 Barrier不变。无Provider、SDK、密钥查询、业务HTTP/写入、Java、Docker或生产DB。原source-map仅检查公开白名单及获授权不存在候选，未访问旧owner/WAL或用户受保护目录。

建议Architect在后续授权中协调RPF89严格workflow delta与RPF91两个新步骤的版本化合同，再重新评估Pilot；不可将此静态取证误记为54个原生PASS。NO_RELEASE/NO_DEPLOY。
