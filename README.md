# RunBridge Node

RunBridge Node 部署在浏览器所有者的设备，主动连接远程 Hub，提供所有者授权的浏览器资源、生命周期管理及可选画面上传。

当前版本 **0.5.0**，配套 Hub **0.5.1**。

## 部署 Node

先从 Hub 部署者取得可达的服务基址和登记文件，再按[部署与运行](doc/deployment/部署与运行.md)安装 Node wheel、登记身份并启用浏览器。文件格式、字段与全部 CLI 参数见[Node 配置与凭据](doc/reference/部署配置与凭据.md)。

- [首次接入与许可管理](doc/user-guide/快速开始.md)：使用已有远程 Hub 登记、查看状态、签发和撤销访问许可。
- [Chrome 复用](doc/user-guide/Chrome复用快速开始.md)：授权已有浏览器实例及其登录状态。
- [受管理 Chromium](doc/user-guide/Playwright快速开始.md)：由 Node 为每次会话新建和回收浏览器。
- [MCP 对接准备](doc/user-guide/MCP对接准备.md)：为 Agent 提供受管理资源和访问许可。
- [画面采集](doc/user-guide/浏览器画面采集.md)、[运行与排障](doc/deployment/运行与排障.md)。

Node 的本机 CDP 端点和身份秘密留在所有者设备；调用方取得的是独立访问许可。公开 HTTP／MCP 接口和 SDK 调用方集成说明由 RunBridge Hub 项目维护。

## 开发与维护

源码安装、构建、测试和开发联调见[本地开发与联调](doc/development/本地开发与联调.md)。完整架构、协议维护资料和历史验收见[文档导航](doc/README.md)。
