# RPF-111 PPT 截图资产

三张均为 Microsoft Edge 157.0.4341.42 渲染的 1440 × 810 PNG。来源版本为 RPF-111 本轮 UI，封存基线 `49c4d29e4cedcf655aaa89a53053373537e38a63`。图像仅保存在本地任务 owner，不纳入 Git。

| 图 | Source kind | 路由 / 构建 | PPT 可用主张 |
|---|---|---|---|
| 01 工作台与证据链 | RECORDED | `/effectwitness/workbench?domain=order` · 录制版 `index-Ccsi8vJi.js` | 工作台区分只读记录、受控 Lab 和需授权的 Provider 入口。四段图展示核验方法。 |
| 02 时间线与反馈 | UI_CONCEPT / SYNTHETIC | `/effectwitness/live-local?session=ui-concept-session&event=4` · `index-WdiLy0v0.js` | 展示界面如何分开显示 UNKNOWN、Authority、反馈输入与确定性选择。 |
| 03 状态差异与 Witness | UI_CONCEPT / SYNTHETIC | 同一路由，定位业务状态与 Witness | 展示双域 before/after、故障四态及下载哈希校验的入口。 |

图 01 使用构建内嵌的 RPF-47 manifest、RPF-46 订单摘要和分离的 RPF-43/RPF-44 样本，经页面自身校验后截图。图 02、03 使用单个 localhost 预览的合成只读响应，带截图内水印。截图没有实际会话、Provider 或 SQLite 写入；示例数字和状态仅用于说明 UI。Edge 通过 DevTools pipe 截取当前页面，没有调用后台业务服务。

| 文件（相对仓库根） | SHA-256 |
|---|---|
| `.local/rpf-111/bcb66d8d0fcf4968962a0f08f05e27a0/01-workbench-recorded.png` | `313296712cc2bc5f3dbe9bc26e94adb55c5f6ef741217c343202d701ab93f8bb` |
| `.local/rpf-111/bcb66d8d0fcf4968962a0f08f05e27a0/02-timeline-feedback-concept.png` | `028d99ca76fa110c3c7901b8761dce133ac9912e00d0860d812282c27986ca38` |
| `.local/rpf-111/bcb66d8d0fcf4968962a0f08f05e27a0/03-state-diff-witness-concept.png` | `26cd26bfb8724e285dc29939a6bd289de8c5edf1bf7a8893d8a515ff8b678d86` |

生成脚本与浏览器核查记录位于同一 owner 的 `verify-preview.cjs` 和 `browser-verification.json`。
