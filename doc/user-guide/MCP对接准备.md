# 为 MCP 调用方准备 Node

本页只说明 Node 所有者的准备：按[部署手册](../deployment/部署与运行.md)配置 managed 资源，在当前环境安装本包 `[playwright]`，按官方指导准备兼容 Chromium，并检查 ONLINE、READY、FREE。Node 无需安装 MCP 服务端或收集 Playwright WebSocket。

向调用方交付node_id、资源ID和模式，由Hub部署者提供申请凭据及实际MCP入口。调用方从Hub领取Node，Node不签发访问文件。MCP 入口是否启用由 Hub 部署者确认；原有 26 项工具及新增请求查询在 Hub 适配后由本机 Python worker 执行。

borrowed Chrome 当前通过项目 HTTP 使用，MCP browser_start 不选择 borrowed 资源。需要同时提供两种模式时按[同机多个 Node](../deployment/同机运行多个Node.md)分别部署并交付不同身份和资源说明。
