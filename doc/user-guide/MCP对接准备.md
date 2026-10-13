# 为 Agent MCP 接入准备 Node

[文档导航](../README.md) · [受管理 Chromium](Playwright快速开始.md) · [首次登记](快速开始.md)

MCP 服务部署在 Hub。当前支持 26 个 MCP 工具，包括受管理 Chromium、原子交互、固定采集、页面/frame、弹窗、上传、截图、持续画面和释放。Node 0.5.0 沿用控制合同版本 1，不需要安装 MCP 或 Agent SDK。

## 1. 所有者准备资源

按受管理 Chromium 指南准备 Node.js 和 Playwright **1.63.0** 运行时、完成登记，配置 `runtime_directory`，然后启动：

```bash
uv run --locked --no-sync runbridge-node run --config .runbridge/node.json --playwright-config .runbridge/playwright.json
```

配置示例见 [Playwright 节点配置](../reference/examples/Playwright节点配置.json)。浏览器是否显示窗口由所有者本地 `launch_options.headless` 决定。Node 启动后会实际启动并关闭探测浏览器，再上报资源状态；`ONLINE` 且目标资源 `READY/FREE` 才可申请。

本期 Agent 的 `browser_start` 只选择 `MANAGED_CHROMIUM`，不复用已经打开的 Chrome 或登录状态。一次会话独占一个资源位。

## 2. 签发给 Agent 的许可

在 Node 根目录运行：

```bash
uv run --locked --no-sync runbridge-node grant --config .runbridge/node.json --resource-id chromium --expires-in 3600 --output .runbridge/agent-access.json
```

资源 ID 应与实际配置一致。私有文件含 Hub 地址、`node_id`、`grant_id`、`access_token`。MCP 客户端通过每次 HTTP 请求的 `Authorization: Bearer <access_token>` 认证，工具参数只传节点和会话 ID。不要交付 `node_token` 或登记凭据，不要把访问令牌贴到模型对话。

Hub 部署者须安装 `mcp` extra 并用 `--enable-mcp` 开启 `/mcp`。浏览器仍在 Node 运行。完整安装、26 个工具的参数和当前时序见 **Hub 项目** `doc/user-guide/MCP浏览器接入.md` 与 `doc/architecture/MCP授权与浏览器生命周期.md`。

## 3. 结束与撤销

正常结束时 Agent 调用 `browser_stop`。Node 关闭本次新建的浏览器，核验进程退出并清理专用临时目录，再上报 `cleanup=COMPLETE`；资源恢复 `READY/FREE`。Node 的长期控制连接继续在线，不需要结束整个 Node 进程。

MCP 客户端断开不立即释放浏览器，租期到期会触发清理。同一个许可可重连 Hub 查询活动 MCP 会话。另一个许可不能接管该会话。

所有者可随时撤销许可：

```bash
uv run --locked --no-sync runbridge-node revoke grant_实际ID --config .runbridge/node.json
```

Hub 拒绝后续 MCP 请求并关闭该许可的活动会话。`PENDING/UNKNOWN` 不代表清理成功；按现有 [运行排障](../deployment/Playwright运行与排障.md) 处理。

本期 MCP 实测为同机独立 Hub/Node 进程与真实 Chromium，已覆盖表单提交、两种 MCP 协议模式、截图、许可隔离、撤销打断、到期和释放。0.5.0 新增 Ubuntu ARM64 跨机器 MCP 与 DSH 0.2.1-alpha.1 对接验收，见[联调记录](../project/DSH与受管理画面联调.md)。

Node 启动时在专用探测页面验证 CDP PNG 后报告 host.managed_visual=cdp-png。持续画面由 Hub 的同一 MCP Page 采集，不需要给这条路线安装 Browscreen visual extra。临时目录使用短私有目录，长 runtime_directory 也不会使 Chromium SingletonSocket 路径超限。只在确认实际进程结束后清理。
