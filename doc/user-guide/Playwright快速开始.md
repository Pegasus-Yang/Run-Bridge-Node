# Node 受管理 Chromium：选择运行时并启动

[文档导航](../README.md) · [返回部署步骤](../deployment/部署与运行.md) · [配置参数](../reference/部署配置与凭据.md)

适用于 Node 0.5.0。每次会话创建新 Chromium 并在结束后回收；不复用日常浏览器的 Profile。开始前完成部署第 1～5 节，已安装本程序、收到登记文本并保存 `node.yaml`；不必事先执行登记命令。

## 1. 运行环境要求与管理边界

| 环境 | 本项目要求 | 安装与维护 |
| --- | --- | --- |
| Node.js | >=20，并使用官方仍支持的版本；常驻进程能找到 `node` 或配置实际路径 | [Node.js 官网](https://nodejs.org/en/download)、[支持周期](https://nodejs.org/en/about/previous-releases) |
| npm | 仅准备 npm Playwright 时需要；正常运行使用已准备的模块 | [npm 官方说明](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) |
| npm Playwright | 本版运行时要求 **1.63.0**，含 `node_modules/playwright` | [Playwright 官方安装](https://playwright.dev/docs/intro) |
| Chromium 和系统库 | 与该 Playwright 版本对应的浏览器、目标操作系统所需库；有窗口模式还需图形会话 | [Playwright 浏览器与系统依赖](https://playwright.dev/docs/browsers) |
| 字体 | 能覆盖实际页面语言，由浏览器所属用户使用 | 操作系统官方文档／设备管理员 |

Node.js 的 `node` 与本项目 Python 命令 `runbridge-node` 不同。上述基础环境由用户或管理员准备，本项目不负责安装、升级或配置它们。

启动前确认所选 Node.js 的 `--version` 能正常返回；命令路径存在不代表其动态库和运行环境完整。准备工具还要求所选环境中的 `npm --version` 正常。

**为什么受管理模式需要 npm Playwright？**它需要向远程调用方提供 Playwright 原生协议入口：Node.js 的公开 `chromium.launchServer()` 新建浏览器并返回 WebSocket 地址，RunBridge 通过 Hub 授权和转发连接，调用方直接使用官方 SDK 的 Browser／Context／Page 等对象。它与浏览器插件无关，也不会把任意已打开的 Chrome 转成这种服务。

**项目支持 Python Playwright。**Python 调用方通过 `chromium.connect()` 连接上述服务，Hub 的 MCP 工具内部也使用 Python SDK。这里需要 JavaScript 的是服务端 `launchServer()` API；Python 公开 API 的 `launch()` 只返回本次调用持有的 Browser，没有对应的公开 `launch_server()`，不能仅替换 Python 依赖就取得同一种远程入口。调用方与服务的 Playwright 主次版本须匹配，见[Python 官方连接说明](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect)和[Node.js 服务端说明](https://playwright.dev/docs/api/class-browsertype#browser-type-launch-server)。

如果目标是复用**已有 Chrome**，选[Chrome 复用模式](Chrome复用快速开始.md)：转发其现有 CDP 入口，Python 调用方使用 `connect_over_cdp()`。这条路线不使用 `launchServer()`，Node 设备也不需要 Node.js/npm Playwright；其能力覆盖与原生协议连接不同，见[官方 CDP 说明](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp)。

## 2. 运行时准备方式只选一种

### A. 已有运行时，或自行按官网准备

可以直接复用已有的 npm Playwright **1.63.0**。将其 npm 项目根目录填入下一节 `runtime_directory`：该目录中应有 `package.json` 和 `node_modules/playwright/`。这不是全局 `node` 可执行文件的位置，也不是 Python 的 site-packages。

浏览器按同版 [Playwright 官方浏览器说明](https://playwright.dev/docs/browsers)准备。采用其默认浏览器缓存时，将 `use_default_browser_cache` 设为 `true`；用户自己设置的 `PLAYWRIGHT_BROWSERS_PATH` 也会保留。安装浏览器和启动 Node 必须使用可访问同一缓存的系统用户和环境。已有兼容浏览器无需重复下载。

这条路线不要求执行 `prepare-playwright`，Node 启动时也不会执行 npm 安装、更新依赖或下载浏览器。若浏览器在自定义位置，还可使用配置参考中的 `launch_options.executablePath` 或 `channel`，兼容性由用户在目标环境核验。

### B. 选择项目提供的独立运行时准备工具

需要为这次部署建立独立 npm 项目和浏览器缓存时，可在部署目录执行：

```bash
cd ~/runbridge-node
.venv/bin/runbridge-node prepare-playwright --runtime-dir .runbridge/playwright --node-executable node
```

它按包内锁文件安装 npm Playwright 1.63.0，并调用官方安装器下载 Chromium 到该目录的 `browsers/`；不会安装 Node.js、系统库或字体。需要 npm、Node.js、网络及目录写权限。已存在不同依赖文件时拒绝覆盖，使用新目录。

这条命令的价值是固定已验证版本、隔离依赖与浏览器缓存、避免误改其他部署。**这是可选便利工具，不是原生协议的强制步骤。**已有或自行维护的符合要求的运行时同样可用。

## 3. 浏览器设置放进同一个 node.yaml

完成 B 时，在部署第 5 节的 `node.yaml` 中增加下面一段；已有 `chrome` 段时先移除它，不能同时选择两种浏览器：

```yaml
playwright:
  launch_options:
    headless: true
```

默认值已对应 B 的 `.runbridge/playwright`、`node` 命令、`chromium` 资源 ID 和独立 `browsers/` 缓存。不需要抄录浏览器版本、进程 ID、动态端口或另存 `playwright.json`。

完成 A、运行时位于 `/srv/browser-runtime` 并使用官方默认缓存时，改用下面的 `playwright` 段，不要把两段同时复制：

```yaml
playwright:
  runtime_directory: /srv/browser-runtime
  use_default_browser_cache: true
  launch_options:
    headless: true
```

`/srv/browser-runtime` 要改成你实际准备的 npm 项目目录。Node.js 不在服务 PATH 中时，在 `playwright` 内补 `node_executable: /实际路径/bin/node`。这些是本机运行位置，不是调用方的路径。

完整可复制文件见 [Node 启动 YAML](../reference/examples/Node启动配置.yaml)，所有字段、路径基准和旧 JSON 兼容方式见配置参考。

## 4. 用同一条命令登记并启动

```bash
cd ~/runbridge-node
.venv/bin/runbridge-node run --settings node.yaml
```

首次启动自动创建 0600 权限的身份文件，向配置中的 Hub 登记，然后连接和上报能力；正常应先见“节点登记完成”，再见“节点在线”。不要手写 Node ID 或身份令牌。

如果登记失败，保留生成的身份，修复错误后执行同一启动命令；会复用同一个 ID 和令牌重试，不会新建另一节点。保留登记文件配置时，每次进程启动都会做一次幂等登记，重连不重复登记。确认首次成功后，可以从 YAML 中移除 `enrollment_token_file`，之后仅凭原身份启动；环境中也不再提供登记令牌即可。

终端保持运行。浏览器实际探测失败时 Node 可能已在线，但资源不可用，要按官方要求核对运行时、浏览器缓存和系统环境；本程序不会在启动时自动修复或安装它们。

返回[部署指南第 7 节](../deployment/部署与运行.md#7-检查状态并向调用方交付访问文件)，在新终端签发许可，确认 ONLINE、READY/FREE，再交付调用方。结束时先释放会话再正常停止 Node。
