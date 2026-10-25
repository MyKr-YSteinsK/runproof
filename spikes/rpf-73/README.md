# RPF-73 / rev-1

Status: Partial。Source `523f6bcaf5487016ac6d3429d294bb850c33ae6a`；identity `e4ea3cc40987e1c90aa683ec324aa33a2d9d97e1e2d713fb84fb75bc039a3db1`。[唯一 TASK_RESULT](RESULT.md)。

`LaunchRequest → LaunchFactory.launch(request, DomainAdapter) → 原固定SDK child` 是两域共用的显式组件接口。新路径不调用旧 Driver，不依赖 frame/profile。原 Guard 保持；返回值全部 SIMULATED_ONLY，真实业务/Explorer/Provider/故障反馈均未运行。

离线 CLI：`python spikes/rpf-73/probe.py verify --manifest <当前任务私有原件> --sha <原始rawSHA256>`；有效0、无anchor2、错anchor3。完整 env/cfg token只留当前私有根；公开诊断只含摘要，无法独立重建历史环境，公开摘要级 env 结论为 INCONCLUSIVE。

6次 Factory child额度已用完，禁止重跑 run case。正常新实验需下一份授权。详[实际双域对照](launch-parity-matrix.json)、[负控](launch-negative-controls.json)、[Runtime](runtime-diagnostic.json)、[工程判断](architecture-decision.json)。
