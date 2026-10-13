# RunBridge Node

RunBridge 的本机客户端：主动连接 Hub，提供所有者启用的浏览器资源；安装可选扩展后，在执行会话期间采集并上传画面。

当前版本 **0.4.0**。Hub、Node 和调用方可以位于不同机器；Node 主动建立出站连接，本机浏览器调试端口不暴露给调用方。

## 能做什么

| 场景 | 执行方式 | 画面 |
| --- | --- | --- |
| 新建受管理 Chromium | 官方 Playwright `chromium.connect()` | 当前不支持独立画面流 |
| 为 Agent MCP 提供新建 Chromium | Hub 安装并启用可选 MCP，Node 沿用原生协议 | MCP 单次 PNG 截图 |
| 复用已授权 Chrome 的页面和登录 | 官方 Playwright `chromium.connect_over_cdp()` | Node 安装 `visual` 扩展后支持 |
| 查询节点、资源和会话 | RunBridge HTTP JSON API | 查询一起返回画面状态与订阅路径 |

浏览器动作保持官方 SDK 用法；登记、许可、会话生命周期和画面订阅由 RunBridge 接口提供。Hub 只提供数据接口，画面由调用方展示。独立业务 HTTP 执行、Appium/ADB、单标签页授权与容量目标仍属后续计划。

## 怎么开始

首次接触时按以下顺序阅读，每篇说明命令在哪台机器运行、前置条件和成功判断：

1. [安装与运行](doc/deployment/安装与运行.md)：源码或 wheel 安装、Python 环境、三方依赖、参数和数据目录。
2. [首次登记与连通](doc/user-guide/快速开始.md)：启动 Hub、登记 Node、签发访问许可、查询在线状态。
3. 选择 [Chrome 复用](doc/user-guide/Chrome复用快速开始.md) 或 [受管理 Chromium](doc/user-guide/Playwright快速开始.md)，启用一种浏览器模式。
4. [调用方对接与使用](doc/user-guide/调用方对接与使用.md)：独立调用环境、官方 SDK、申请与释放会话、完整执行示例。

   Agent 通过 MCP 接入时，所有者阅读 [MCP 对接准备](doc/user-guide/MCP对接准备.md)；Node 不需要安装 MCP 包。

5. [浏览器画面流接入](doc/user-guide/浏览器画面流接入.md)：启用采集、查询入口、Python 订阅和浏览器展示。
6. 跨机器或虚拟机部署时补充阅读[网络与中文字体](doc/deployment/跨机器部署与中文字体.md)。

在本项目根目录安装源码依赖：

```bash
uv sync --locked --python 3.14 -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
```

完成上述准备后，在本项目根目录启动：

```bash
uv run --locked --no-sync runbridge-node run --config .runbridge/node.json --chrome-config .runbridge/chrome.json
```

上面的启动命令需要先完成登记，并准备 Chrome 本地授权文件。仅运行 run 而不提供浏览器配置时，节点只有控制连接，不开放浏览器资源。

## 查参数、排障与验证

- [完整文档导航](doc/README.md)：按安装者、节点所有者和调用方组织阅读路线。
- [对外接口总览](doc/reference/对外接口总览.md)、[会话接口](doc/reference/会话接口与原生连接.md)、[画面接口](doc/reference/浏览器画面流接口.md)。
- [运行与排障](doc/deployment/Playwright运行与排障.md)：网络、版本、资源占用、断线和清理问题。
- [画面流验收](doc/project/浏览器画面流验收记录.md)、[Ubuntu ARM64 虚拟机验收及中文字体](doc/project/虚拟机Node跨机器验收记录.md)：实际验证范围与证据。

源码开发环境的回归命令：

```bash
uv run --locked --no-sync pytest -q
```

源码位于 `src/runbridge_node/`。两端独立打包和部署，通过公开协议通信；查询客户端升级至 0.4.0 后支持新增 `visual` 字段。详细设计和历史验收保留在 `doc/design/`、`doc/project/`，其历史日期不代表当前重新验证。
