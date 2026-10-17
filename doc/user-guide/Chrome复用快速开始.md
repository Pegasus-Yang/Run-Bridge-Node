# Node 授权复用已有 Chrome

[文档导航](../README.md) · [Node 部署](../deployment/部署与运行.md) · [配置字段](../reference/部署配置与凭据.md) · [许可管理](快速开始.md)

适用于 Node 0.5.0。先在本设备完成 Node 安装和远程登记，再为所有者明确授权的本机 Chrome／Chromium 实例保存配置。以下命令在 Node 部署目录执行。

## 1. 准备所有者授权的浏览器

此模式复用整个实例可见的页面、上下文、Cookie 和 localStorage。授权范围为 `BROWSER_INSTANCE`；通过 URL 选页不构成单标签页授权。

已有明确授权的浏览器级 CDP 端点时直接进入下一步。需要新建专用实例时，由所有者选独立 Profile 启动。例如 macOS：

```bash
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir="$PWD/.runbridge/chrome-profile" --no-first-run
```

Linux 选择设备实际安装的命令：

```bash
google-chrome --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir="$PWD/.runbridge/chrome-profile" --no-first-run
```

这是浏览器启动，不是安装。无图形环境可由所有者选择 `--headless=new`；先补齐本机库。Chrome 136 起默认用户目录的远程调试有额外限制，专用 Profile 与日常窗口分开使用，见[Chrome 官方说明](https://developer.chrome.com/blog/remote-debugging-port)。已有浏览器和登录是否可用由所有者确认。

## 2. 保存本机授权配置

只查询已确认属于该实例的端口；不是 9222 时改为实际端口，不扫描其他浏览器：

```bash
.venv/bin/python - <<'PYCODE'
import json
import os
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

opener = build_opener(ProxyHandler(proxies={}))
with opener.open(fullurl="http://127.0.0.1:9222/json/version", timeout=5) as response:
    browser = json.load(response)
path = Path(".runbridge/chrome.json")
path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
values = {
    "resource_id": "chrome",
    "authorization_scope": "BROWSER_INSTANCE",
    "cdp_endpoint": browser["webSocketDebuggerUrl"],
}
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as output:
    json.dump(values, output, ensure_ascii=False, indent=2)
print("Chrome 授权配置已保存，未输出本机调试地址")
PYCODE
```

已有配置时不会覆盖。也可按 [JSON 示例](../reference/examples/Chrome节点配置.json)编写并设置 0600 权限。字段和限制见配置参考：固定资源 ID、整个实例授权、回环地址上的浏览器级 `ws://.../devtools/browser/ID`；不接受页面端点、HTTP 自动发现地址或远程浏览器地址。

## 3. 运行并核验

```bash
.venv/bin/runbridge-node run --config .runbridge/node.json --chrome-config .runbridge/chrome.json
```

Node 读取真实浏览器版本。浏览器不可达时控制连接仍可能在线，但资源为 UNAVAILABLE。

在另一个终端签发仅覆盖该资源的一小时许可并查询：

```bash
.venv/bin/runbridge-node grant --config .runbridge/node.json --resource-id chrome --expires-in 3600 --output .runbridge/chrome-access.json
.venv/bin/runbridge-node inspect node_example --access-file .runbridge/chrome-access.json
```

替换实际节点 ID。预期后端 `chrome-cdp`、资源类型 `BORROWED_CHROME_CDP`、`READY/FREE` 和 `BROWSER_INSTANCE`。资源 ID 自定义时，配置、签发和交付值一致。

## 4. 交付、采集与停止

将访问文件和资源信息交给调用方，SDK 使用方法由 Hub 项目维护。需要持续画面时按[Node 画面采集](浏览器画面采集.md)启用可选扩展。

Node 正常停止、许可撤销和会话释放只结束本次借用连接及采集，不退出 Chrome 或删除 Profile。实际页面动作仍会影响原实例，不因断开而回滚。

Chrome 重启后浏览器 ID 通常变化，由所有者重新确认端点并更新配置，再正常重启 Node；保留原 `node.json`。清理异常见[运行与排障](../deployment/运行与排障.md)。
