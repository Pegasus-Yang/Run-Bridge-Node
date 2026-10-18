# Node 受管理 Chromium：从运行时到启动

[文档导航](../README.md) · [返回部署步骤](../deployment/部署与运行.md) · [配置参数](../reference/部署配置与凭据.md)

适用于 Node 0.5.0。此模式为每次会话创建独立 Chromium，任务结束后回收，不使用你日常 Chrome 的 Profile 或登录状态。给 Agent 提供 MCP 浏览器资源也选此模式。

**开始前**：已完成部署指南第 1～5 节，本设备有 `~/runbridge-node/.venv/` 和登记成功的 `.runbridge/node.json`。没有完成时先返回部署指南，不要从这里直接开始安装两端。

## 1. 进入 Node 目录，检查 Node.js 和 npm

在 Node 设备终端：

```bash
cd ~/runbridge-node
node --version
npm --version
```

这里的 `node` 是 **Node.js**，用于运行浏览器服务；`runbridge-node` 是我们的 Python 程序，两者不是同一命令。需要 Node.js >=20，并且 Node.js、npm 两条命令都能正常返回版本。设备已有可用的受支持 LTS 版本时跳过安装。

使用 Homebrew 的 macOS／Linux，可安装 [node@22](https://formulae.brew.sh/formula/node@22)，并在本终端选择它：

```bash
brew install node@22
export PATH="$(brew --prefix node@22)/bin:$PATH"
node --version
npm --version
```

没有 Homebrew 时，打开 [Node.js 官方下载页](https://nodejs.org/en/download)，选择设备的操作系统、CPU 架构和受支持的 LTS 安装方式，按页面步骤安装后重新打开终端。RunBridge 的最低版本要求不是建议安装已结束支持的旧版本，支持状态以 [Node.js 发布表](https://nodejs.org/en/about/previous-releases)为准。

如果使用上面的 Homebrew 路径设置，每个新终端需重新设置，或让管理员在长期服务环境中固定对应路径。版本检查出错时先解决 Node.js 环境，不要继续准备浏览器。

## 2. 下载本 Node 专用的浏览器运行时

在同一终端执行：

```bash
.venv/bin/runbridge-node prepare-playwright --runtime-dir .runbridge/playwright --node-executable node
```

命令会使用 Node 安装包附带的锁文件，安装 npm Playwright **1.63.0** 和对应 Chromium。它与 Python 的 `.venv` 分开，下载过程需要网络，耗时取决于网络和缓存。

成功时最后输出类似：

```text
Playwright 1.63.0 运行时已准备：/你的主目录/runbridge-node/.runbridge/playwright
```

目录中应有：

```text
.runbridge/playwright/
├── package.json
├── package-lock.json
├── node_modules/playwright/       # npm 浏览器服务库
├── browsers/                     # 对应版本的 Chromium
└── npm-cache/                    # 本次安装缓存
```

这些文件由命令产生，不需要你从另一个项目复制，也不应自己编写 package-lock.json。

遇到“存在不同的依赖文件”时，说明目录已经属于另一套依赖。保留它，选择新的独立目录，例如 `.runbridge/playwright-1.63.0`；准备命令和下一节 JSON 的 `runtime_directory` 必须同时改成那个目录。

### Linux 首次运行还需要系统库

上面的命令下载浏览器，不负责安装 Linux 系统库。若目标系统尚未准备，由有管理员权限的人在本设备的 Node 部署目录执行：

```bash
node .runbridge/playwright/node_modules/playwright/cli.js install-deps chromium
```

该命令可能请求 sudo 并安装系统包；没有权限时交给设备管理员完成，不能靠修改 JSON 跳过缺失库。命令语义见 [Playwright 系统依赖说明](https://playwright.dev/docs/browsers#install-system-dependencies)。使用不同运行时目录时一并修改命令中的目录。macOS 不执行这条 Linux 准备步骤。

## 3. 生成 playwright.json

下面的配置使用默认资源 ID `chromium`，无窗口启动，适合第一次接入。复制**整段命令**到 Node 部署目录执行：

```bash
.venv/bin/python - <<'PYCODE'
import json
import os

values = {
    "runtime_directory": ".runbridge/playwright",
    "node_executable": "node",
    "resource_id": "chromium",
    "launch_options": {"headless": True},
}
descriptor = os.open(".runbridge/playwright.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as output:
    json.dump(values, output, ensure_ascii=False, indent=2)
    output.write("\n")
print("已保存 .runbridge/playwright.json")
PYCODE
```

成功会保存 JSON。已有文件时拒绝覆盖；需要修改时用编辑器打开原文件，保留正确的运行时目录。

| 字段 | 本例值从哪里来／为什么这样填 |
| --- | --- |
| `runtime_directory` | 第 2 节实际准备的目录；相对 Node 工作目录解析，不是相对 JSON 所在目录 |
| `node_executable` | 第 1 节能正常运行的 Node.js 命令；服务环境也必须能找到它 |
| `resource_id` | 你给资源起的 ID，本教程用 `chromium`；后面签发许可使用相同值 |
| `launch_options.headless` | `true` 无窗口；改为 `false` 才显示窗口，Linux 还须有可用图形会话 |

生成脚本中的 `True` 是 Python 写法，保存后的 JSON 会自动变成 `true`。如果手工编辑 JSON，用双引号和小写 `true/false`，不要写注释、尾逗号、`~` 或 `$HOME`。

Node.js 不在服务 PATH 中时，先用 `command -v node` 取得实际绝对路径，再填入 `node_executable`。全部启动字段、目录、代理和单位见配置参考；第一次运行可以直接使用本例，不需要自行补其他字段。

## 4. 启动并保持 Node 运行

在同一 Node 终端：

```bash
.venv/bin/runbridge-node run --config .runbridge/node.json --playwright-config .runbridge/playwright.json
```

`--config` 读取登记身份，`--playwright-config` 读取刚生成的浏览器配置；不要同时添加 `--chrome-config`。

启动时会短暂启动并关闭一次探测浏览器，再上报能力。命令持续运行、没有新的输入提示符是正常现象。**保持这个终端打开**，不要再启动第二个相同身份的 Node。

现在返回[部署指南第 7 节](../deployment/部署与运行.md#7-检查状态并向调用方交付访问文件)，在**另一个终端**签发许可、查询 ONLINE／READY／FREE，并交付调用方。只完成本页并不代表调用方已经连过浏览器。

## 5. 后续操作

普通 SDK／HTTP 使用由 Hub 项目手册说明；Agent 接入补充阅读 [MCP 准备](MCP对接准备.md)。MCP 和受管理浏览器不要求 Node 安装 Browscreen；普通 SDK 受管理会话没有独立持续画面流。

停止时先释放会话，再在 Node 服务终端按 Ctrl+C，确认本次浏览器和 helper 已回收。访问业务网站、登录及业务断言由调用方完成；新会话不会继承上一会话登录。目录输出和清理含义见[运行与排障](../deployment/运行与排障.md)。
