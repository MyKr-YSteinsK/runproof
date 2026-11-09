# RPF-102/rev-1

封存时本地交付为 PARTIAL，真实 SDK 结果与远端 CI 为 NOT_RUN_AT_SEAL。基线为 `1478ff962c123641a52314bede8351b58a71e6d0`。

新增独立的 SDK 请求合同、单写者 WAL、只允许任务本地地址的 SDK 子进程、带 nonce 的独立 Receiver，以及不导入 SDK 或 Host 的离线 Oracle。Host 在真实转发前记录票据和 SEND_BEGIN。UNKNOWN 在工具返回前持久锁存，后续 completion 的拒绝独立于 SDK 的终止状态。

本机 CPython 3.14.7 预检未找到合格 SDK。本地 5 个测试通过，覆盖真实文件 WAL、正常与 UNKNOWN 的恢复、独占锁、竞争顺序、注入 write/flush、断裂 WAL、冒领票、工具回注和接收身份交叉嫁接。内存证据重锚后仍拒绝 UNKNOWN 后的预约与发送。此处的内存证据仅用于反例，不是实测 SDK transcript。

正式 NORMAL/UNKNOWN 保留给已授权的 Ubuntu 隔离 venv。封存时本机 SDK 调用、物理转发和外部 Provider 请求均为 0。实际 SDK 和物理结果须从相同提交的 CI 日志读取。外部 Issuer、正式发布、历史 RPF-74 修复及 RPF-100 接入仍属于独立验收。
