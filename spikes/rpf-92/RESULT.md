# RPF-92/rev-1 主结果

Status: PARTIAL；Path: RECORDED_VERIFIED / GOLDEN_AND_LAB_NOT_RUN。封存时Git/CI尚未验证。

Base `d9e985d41249a72be06167dccd19bccb8d17892f`；main。现场GitHub仓库实际为public，Plan的Private描述与事实不符；未更改仓库权限。G0完成源码pin和路径检查，资源所有权/端口检查因未启动Golden Demo而NOT_RUN。

Recorded：本轮实际桌面浏览器访问并从导航进入实验室、跨域页；Recorded以TRACKED SOURCES展示历史证据、明确无Provider/写入，CLI `verify_evidence` exit0。RPF43/44真实历史样本各自离线VERIFIED_ANCHORED，签发者身份NOT_ESTABLISHED；篡改副本以FILE_SHA256_MISMATCH exit3拒绝。不是新复现。

Gateway不可达时免费Lab显示UNAVAILABLE并禁用启动；跨域页显示不可用，明确订单确定性Target与配置scripted fixture。未启动任何Gateway：现有默认owner指向历史rpf45/rpf60，未验证可安全组装fresh公开副本。无订单/运维新试验，无Provider调用。

Golden Demo：Docker CLI存在但Linux引擎不可达；没有创建、接管或删除容器/卷，也没有探测他人端口。原start-demo另会执行Maven构建，task-only输出与离线依赖尚未证明，禁止借此扩权。竞争演示smoke/stop脚本未创建，冷启动/停止验收NOT_RUN。

真实问题：Recorded页面把+00:00时间显示在“北京时间”标题下；该文件为本Plan只读，未修改。页上原始时区仍可见。

Router取证：同Run脱敏Artifact hash核验，12个ERROR、6模块，执行子进程exit1且未超时/截断；十二个对应方法AST均直接调用TemporaryDirectory，但原异常未保存，根因UNAVAILABLE。Router输出owner合同不接受本任务根，未绕过或执行聚焦原测试。新增只读诊断脚本，真实输入exit0、错误路径exit2。

Web原源码未变：实际npm test 16文件/64测试PASS，typecheck PASS，build PASS；任务配置重定向缓存/构建到新owner。Web在执行前单独冻结，取证Python之后才创建，因此这些结果只适用于未变Web，不冒称所有任务源码的统一冻结后完整验收。桌面浏览器观察不等于真实移动设备验证。

A02/A04/A05/A07 PARTIAL，A03 PASS；A06 NOT_RUN_AT_SEAL，最终Git/CI回执另行报告。无比赛资料制作、平台提交、Release或Deploy；11月10日创意阶段截止需用户自行核对并提交。
