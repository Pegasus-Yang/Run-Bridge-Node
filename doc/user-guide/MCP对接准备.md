# Node 为 Agent 的 MCP 接入准备资源

[文档导航](../README.md) · [首次部署](../deployment/部署与运行.md) · [受管理 Chromium](Playwright快速开始.md) · [许可管理](快速开始.md)

本文面向 Node 所有者。你的工作是准备浏览器资源和访问许可，再把它们交给 Agent 使用者。远程 MCP 服务由 Hub 部署者提供，Node 本身不用安装 MCP 或 Agent SDK。

## 1. 确认前提已经完成

首次安装先按部署指南准备统一配置，再选择**受管理 Chromium**。只有已有 Chrome 的实例授权还不够，当前 MCP 浏览器工具不会自动复用那一实例。

向 Hub 部署者取得实际 MCP 地址，例如 `http://192.168.50.10:8787/mcp`；这是 Hub 基址后加 `/mcp` 的工具入口，必须确认对方已安装并启用相应功能。正常的健康响应不能证明 MCP 已开启。

Node 服务保持运行，且应查询到：

| 项目 | 要求 |
| --- | --- |
| 节点 | ONLINE，能力报告未过期 |
| 浏览器资源 | 默认 `resource_id=chromium`，`kind=MANAGED_CHROMIUM`，READY／FREE |
| 运行时 | 已有、自行维护或本包工具准备的 npm Playwright 1.63.0，与 Hub 的 SDK 主次版本匹配 |
| 业务地址 | Node 设备的浏览器能访问目标系统；仅 Agent 机器能访问还不够 |

查询方法见[状态检查](快速开始.md)。是否显示浏览器窗口由 Node 所有者的 `launch_options.headless` 决定。

## 2. 单独给 Agent 签发访问文件

在 Node 设备的新终端执行，保留原 Node 服务终端：

```bash
cd ~/runbridge-node
.venv/bin/runbridge-node grant --config .runbridge/node.json --resource-id chromium --expires-in 3600 --output .runbridge/agent-access.json
```

资源 ID 若自定义，使用自己的值。`agent-access.json` 由命令自动写入，含真实访问令牌和期限；已有同名文件时复用未过期许可或换一个新名字，不能覆盖原文件。

可以先用这份许可查询，避免把错误范围交给 Agent：

```bash
rb_node_id=$(.venv/bin/python -c 'import json; from pathlib import Path; print(json.loads(Path(".runbridge/node.json").read_text())["node_id"])')
.venv/bin/runbridge-node inspect "$rb_node_id" --access-file .runbridge/agent-access.json
```

## 3. 交接给 Agent 使用者

通过私密渠道交付实际 `agent-access.json`，并填写：

```text
访问附件：agent-access.json
MCP 地址：http://192.168.50.10:8787/mcp（填写 Hub 部署者确认的实际入口）
节点 ID：访问文件中的 node_id
资源 ID：chromium（填写本机实际资源 ID）
浏览器模式：受管理 Chromium
期限：访问文件中的 expires_at
可访问的业务页面：填写真实地址
接入步骤：RunBridge Hub 项目《MCP 浏览器接入》
```

文件名可不同，格式与 `access.json` 相同。资源 ID 不在访问文件中，需要另外交代。Agent 客户端用 `access_token` 作为每次请求的 Bearer 认证，不使用 `node_token` 或登记令牌；具体客户端配置和可运行样例由 Hub 手册说明。

受管理 MCP 画面由 Hub 持有的同一页面采集；Node 只负责相应运行时和能力探测，这条路线不用安装 `visual` 扩展。

## 4. 结束、撤销和异常

正常结束由调用方释放会话并确认 `cleanup=COMPLETE`。只断开 Agent 的 MCP HTTP 客户端不会立即释放浏览器，原租期和许可期限继续有效。

要收回 Agent 的权限时，从该文件读取许可 ID：

```bash
rb_grant_id=$(.venv/bin/python -c 'import json; from pathlib import Path; print(json.loads(Path(".runbridge/agent-access.json").read_text())["grant_id"])')
.venv/bin/runbridge-node revoke "$rb_grant_id" --config .runbridge/node.json
```

撤销后核查清理；PENDING／UNKNOWN 交由所有者按[Node 排障](../deployment/运行与排障.md)确认。续期重新签发，不改旧 JSON 时间，新许可不能接管旧会话。
