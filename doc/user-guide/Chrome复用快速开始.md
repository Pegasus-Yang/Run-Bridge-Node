# Node 复用 Chrome：从实例授权到启动

[文档导航](../README.md) · [返回部署步骤](../deployment/部署与运行.md) · [配置参数](../reference/部署配置与凭据.md)

适用于 Node 0.5.0。此模式连接所有者明确授权的本机 Chrome，使用其中已打开的页面、上下文和登录状态。授权范围为整个浏览器实例，不是单个标签页。

**开始前**：已完成部署指南第 1～5 节，本设备有 `~/runbridge-node/.venv/` 和登记成功的 `.runbridge/node.json`。本模式不需要 Node.js／npm；Chrome 本身必须已安装。

## 1. 准备允许调试的 Chrome 实例

在 Node 设备打开终端，进入部署目录：

```bash
cd ~/runbridge-node
```

要连接的 Chrome 必须由所有者以远程调试方式启动。普通已打开的浏览器窗口不一定提供这种端口，Node 不会扫描或自动附加日常浏览器。

**已有明确授权的浏览器调试端口**时，保留其运行，记下实际端口，直接进入第 2 节。

**需要新建专用实例**时，选择适合系统的一条命令。下面使用独立 Profile 目录和端口 9222：

macOS，已安装 Google Chrome：

```bash
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir="$PWD/.runbridge/chrome-profile" --no-first-run
```

Linux，已安装且命令名为 google-chrome：

```bash
google-chrome --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir="$PWD/.runbridge/chrome-profile" --no-first-run
```

如果设备安装的是 Chromium 且命令名为 `chromium`，改用下面这一条，不要把两个实例都启动：

```bash
chromium --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir="$PWD/.runbridge/chrome-profile" --no-first-run
```

不确定命令名时，可用 `command -v google-chrome` 或 `command -v chromium` 查看已安装命令的路径；没有输出表示该名字未在 PATH 中。先由设备所有者安装或确认浏览器，再继续，不要把浏览器未安装当成 Node 登记问题。

| 参数 | 含义 |
| --- | --- |
| `--remote-debugging-address=127.0.0.1` | 只允许本设备连接调试入口 |
| `--remote-debugging-port=9222` | 本实例的调试端口；端口冲突时自行选择空闲端口，后面的查询也改用同一端口 |
| `--user-data-dir=...` | 本实例专用的 Profile；`$PWD` 是当前部署目录，shell 会替换成真实路径 |

专用 Profile 首次是新的，**不会自动带入日常 Chrome 的登录**。在出现的专用窗口手动打开并登录允许调用方操作的业务页面，保持该页打开。之后继续使用同一 Profile，可保留该实例的状态。

Chrome 136 起默认用户目录的调试开关有额外限制，参见 [Chrome 官方说明](https://developer.chrome.com/blog/remote-debugging-port)。不要通过复制日常 Profile 来猜测登录迁移。这里复用的是你明确准备并授权的实例。

浏览器可能占用此终端；保留它和浏览器窗口，再开**另一个 Node 终端**执行以下步骤，并先运行 `cd ~/runbridge-node`。无图形环境选择 `--headless=new` 属于另一种运行方式，无法依靠屏幕手工登录；首次需要人工登录时使用可用的图形会话。

## 2. 从本机实例取得端点，生成 chrome.json

下面整段命令会向**你刚确认的本机端口**查询 `/json/version`，读取其中的 `webSocketDebuggerUrl` 并保存配置。浏览器 ID 来自 Chrome，不是自己编造的 UUID。

端口不是 9222 时，修改下面 URL 的端口。只查询所有者已经确认的实例，不扫描其他端口。

```bash
cd ~/runbridge-node
.venv/bin/python - <<'PYCODE'
import json
import os
from urllib.request import ProxyHandler, build_opener

opener = build_opener(ProxyHandler(proxies={}))
with opener.open(fullurl="http://127.0.0.1:9222/json/version", timeout=5) as response:
    browser = json.load(response)
values = {
    "resource_id": "chrome",
    "authorization_scope": "BROWSER_INSTANCE",
    "cdp_endpoint": browser["webSocketDebuggerUrl"],
}
descriptor = os.open(".runbridge/chrome.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as output:
    json.dump(values, output, ensure_ascii=False, indent=2)
    output.write("\n")
print("已保存 .runbridge/chrome.json，未输出本机调试地址")
PYCODE
```

成功后文件格式类似这样，端点为演示值：

```json
{
  "resource_id": "chrome",
  "authorization_scope": "BROWSER_INSTANCE",
  "cdp_endpoint": "ws://127.0.0.1:9222/devtools/browser/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
}
```

| 字段 | 来源和含义 |
| --- | --- |
| `resource_id` | 你给这个资源起的 ID，本教程为 `chrome`；签发许可和调用方申请使用相同值 |
| `authorization_scope` | 固定为 `BROWSER_INSTANCE`，明确授权整个实例 |
| `cdp_endpoint` | 上述接口返回的真实浏览器级 WebSocket 端点，保存在设备上，不交给 Hub 用户或调用方 |

文件已存在会拒绝覆盖。Chrome 重启后浏览器 ID 通常改变；由所有者重新确认端点，编辑原配置或备份旧配置后重新生成，再重启 Node。不能继续使用本页示例 ID。

如果查询连接拒绝，先检查浏览器是否仍运行、启动时是否开启了调试端口、查询端口是否一致。`cdp_endpoint` 只接受固定的 `ws://127.0.0.1:端口/devtools/browser/ID` 或 IPv6 回环形式，不接受 `localhost`、远程 IP、HTTP 查询地址或页面级端点。完整规则见配置参考。

## 3. 启动并保持 Node 运行

在当前 Node 终端：

```bash
.venv/bin/runbridge-node run --config .runbridge/node.json --chrome-config .runbridge/chrome.json
```

保留浏览器和这个 Node 服务终端，不要同时运行另一份相同身份的 Node。Node 读取实际浏览器版本并探测资源；浏览器不可达时控制连接仍可能在线，但资源会不可用。

返回[部署指南第 7 节](../deployment/部署与运行.md#7-检查状态并向调用方交付访问文件)，在**新的终端**签发 `chrome` 资源的许可、查询状态并交付。

交接时还要向调用方说明：应该操作的已打开页面的**精确 URL**。调用示例会在已有页面中按此匹配，不会替你打开新页面或恢复登录；URL 选页也不会把整个实例授权缩小成单页授权。

## 4. 持续画面和正常停止

需要已有 Chrome 持续 PNG 时，按[画面采集](浏览器画面采集.md)在 Node 环境补装可选扩展，再正常重启 Node。

结束任务时调用方先释放会话。停止 Node 使用其终端的 Ctrl+C／SIGTERM；这只释放借用连接和采集，不关闭原 Chrome、不删除 Profile，也不回滚页面上已经发生的业务操作。浏览器关闭与 Profile 管理由所有者负责。

资源不可用、端点变化或清理未确认时，按[Node 排障](../deployment/运行与排障.md)处理。
