# RPF-102 rev-4 验收结果

封存状态为 `PARTIAL`。本地和 Git HTTPS 远端的初始 `main` 均为 `647a1a4fcb7964ec70a8206e4f6923da4f4dca94`。该冻结提交在 Windows CPython 3.14.7 上通过两套离线测试，共 23 项，并通过文档检查。此前的自动 Ubuntu CI 只执行了 12 项。本次将自动工作流扩至完整两套，并纳入 capsule 源码和测试的路径触发。本地候选同样通过 23 项与文档检查。候选推送及新 hosted 回执为 `NOT_RUN_AT_SEAL`。[基线离线 CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42592963467)

物理 G0 的阻断来自 GitHub。按名称查询 `rpf-102-physical` 返回 HTTP 404，同一仓库的 Environment 列表成功返回 `total_count=0`。手动工作流已登记且显示 active，运行列表中没有手动 dispatch。该环境的必需审阅者和禁止自批准无法成立，故物理 G0 未通过。rev-4 的允许操作未包含新建或变更审批保护。下一次准入须先由仓库管理员建立并确认该环境、指定独立审阅者并禁止自批准，然后在同一 SHA 及同一次 Run 上核对批准变量。

静态核对了本地子进程的 `-I -S -B` 与显式 site 路径、循环地址和禁用重试的客户端配置。固定上游源码确认 OpenAI 3.35.1 接受 `httpx2.AsyncClient`，PydanticAI 2.57.0 的 Chat 模型根据 profile 选择 token 字段，并以原工具调用 ID 生成字符串回注。SDK 真实请求、审计钩子与 hosted 运行行为仍待实测，首次旧运行根因保持 `UNDETERMINED`。[Python 3.12 命令行](https://docs.python.org/3.12/using/cmdline.html) · [OpenAI 3.35.1 客户端源码](https://github.com/openai/openai-python/blob/v3.35.1/src/openai/_client.py) · [PydanticAI 2.57.0 Chat 模型源码](https://github.com/pydantic/pydantic-ai/blob/v2.57.0/pydantic_ai_slim/pydantic_ai/models/openai.py)

本轮正式 dispatch 用量为 0/4，NORMAL、UNKNOWN 和实测 Oracle 均为 `NOT_RUN`。SDK 安装、子进程、物理发送、外部 Provider 调用和实际业务写入均为 0。不存在本轮实测 SDK、票据或接收字节，回执字段使用 `null`。旧 Run 已消耗的额度和失败结果单独保留。[旧正式 Run](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42580171633)

Canonical 门禁沿用原有覆盖要求。基线 Run 的两道门禁分别缺 534 和 516 项。新提交的实际 CI 结果由交付回执补充。[基线 Canonical CI](https://github.com/MyKr-YSteinsK/runproof/actions/runs/42592963453)
