# Node 为 MCP 准备资源

[文档导航](../README.md) · [受管理 Chromium](Playwright快速开始.md) · [许可管理](快速开始.md)

本指南面向 Node 0.5.0 所有者。远程 Hub 的部署者须先提供已启用的 MCP 服务入口；本设备负责受管理浏览器资源和访问许可。

## 1. 核对资源

按[受管理指南](Playwright快速开始.md)完成 Node.js、npm Playwright 1.63.0、配置和启动。确认 Node ONLINE 且实际受管理资源 READY/FREE。

MCP 的浏览器启动选择 MANAGED_CHROMIUM。已有 Chrome 的实例授权不能自动代替受管理资源；是否显示窗口由所有者的 `launch_options.headless` 决定。

## 2. 给调用方签发许可

在 Node 部署目录的另一个终端：

```bash
.venv/bin/runbridge-node grant --config .runbridge/node.json --resource-id chromium --expires-in 3600 --output .runbridge/agent-access.json
```

资源自定义时使用实际 ID。交付访问文件及资源信息，说明期限和设备网络可达的业务地址。Agent／客户端的 MCP 配置、工具参数和恢复流程由 Hub 项目的 MCP 指南维护；本设备不安装 MCP 或 Agent SDK。

Node 启动探测会报告实际的受管理画面能力。持续画面由 Hub 持有的同一页面产生，此路线不需要 Node 的 visual extra。

## 3. 结束、撤销与异常

调用方正常结束应释放会话，并确认 cleanup=COMPLETE。仅断开 MCP HTTP 客户端不会立即释放浏览器，原租期和许可期限继续有效。

所有者按访问文件内的实际许可 ID 撤销：

```bash
.venv/bin/runbridge-node revoke grant_example --config .runbridge/node.json
```

撤销触发该许可活动会话关闭，并拒绝后续访问。清理为 PENDING／UNKNOWN 时按[Node 排障](../deployment/运行与排障.md)核查本机资源，不能按前端断开状态推断回收完成。签发新许可不接管旧会话。
