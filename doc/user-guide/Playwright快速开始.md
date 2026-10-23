# 受管理 Chromium

此模式由 Node 的 Python Playwright `chromium.launch()` 为每个会话新建浏览器，初始 context 的 viewport=1280×720、locale=zh-CN，并创建 about:blank 页面。适合新任务和 MCP，不保留上次会话登录。

首次部署按[完整手册](../deployment/部署与运行.md)执行，在 YAML 配置 `tools.playwright.mode: managed`。使用 `[playwright]` 安装本项目时已经在同一环境安装 Python Playwright，无需单独的 npm 安装命令。

浏览器及系统依赖按 [Playwright 官方说明](https://playwright.dev/python/docs/browsers)准备；已安装匹配版本的浏览器可以复用。缓存目录在安装与运行时保持一致，可用 YAML browser_cache_directory 指定。已有同环境的匹配 Python 库无需重复安装。项目不会下载浏览器或自动修改系统依赖。

`run --settings node.yaml` 一次完成登记、实际能力探测和上线。探测会创建并关闭一个专用浏览器；此时没有任务会话。随后由调用方创建会话，Node 为该会话启动独立 worker。关闭、到期、撤销会回收本次 Chromium 与临时 Profile；无法确认时报告 UNKNOWN 并隔离资源。

继续部署手册第 5 步上线检查与设备标识交付，无需再启动一个 Node。配置默认值见[带注释样例](../reference/examples/Node启动配置.yaml)。
