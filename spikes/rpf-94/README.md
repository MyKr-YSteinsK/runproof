# RPF-94 EffectWitness 工作台

Status: PARTIAL。工作台为已有来源的只读入口，不启动实验或调用模型。权限、额度和可用性请在旧页面确认；现有 Gateway 未被本任务启动。

在已安装项目依赖、Gateway 默认关闭的受控环境中，从仓库根运行 `npm run dev -- --host 127.0.0.1 --port 4173 --strictPort`，访问 `http://127.0.0.1:4173/effectwitness/workbench`。仅在有相应授权且确认环境变量和端口归属时运行。先选择订单/运维，查看预期、不变量、来源和模式，再从页面链接打开 Recorded、受控 Lab、Live Explorer 或跨域 Lab；这些入口不共享会话，Live 可能收费和写入。

订单投影引用已验证的 RPF-46 历史研究摘要，运维引用与其分离的 RPF-44 历史 Witness 样本。来源校验失败隐藏历史主张；不是新运行、外部签发或生产结论。UTC 标签不改变原始时间戳。键盘、窄屏和旧页面额外回归尚有限制，详见 [RESULT](RESULT.md)。

[上游接入合同](JIUWENSWARM_INTEGRATION_CONTRACT.md) 为设计提案，集成未执行。基线 `3f38cbe3bfa0b36447b08fad4477ab09fd3428d4`。
