# RunBridge Node

RunBridge Node 部署在浏览器所有者的设备，主动连接远程 Hub，提供所有者授权的浏览器资源、生命周期管理及可选画面上传。

当前版本 **0.5.0**，配套 Hub **0.5.1**。

## 部署 Node

第一次接入从[部署与运行](doc/deployment/部署与运行.md)第 1 节开始。它先列明向谁取得什么：真实 Hub 地址、Hub 生成的单行 `enrollment.token`、Node 安装包和手册；再逐步说明文件保存、安装、统一 YAML、选择浏览器模式、启动时登记、查询状态和交付访问许可。

每一步都标出操作设备、目录、需要替换的值和预期结果。浏览器模式指南执行完后返回部署第 7 节，无需重新启动 Node；参数和字段需要时再查[Node 配置与凭据](doc/reference/部署配置与凭据.md)。

- [同机多个 Node](doc/deployment/同机运行多个Node.md)：每个实例一份 YAML 和独立身份。
- [状态检查与许可管理](doc/user-guide/快速开始.md)：部署后的日常查询、签发、交付、撤销和续期。
- [Chrome 复用](doc/user-guide/Chrome复用快速开始.md)：授权已有浏览器实例及其登录状态。
- [受管理 Chromium](doc/user-guide/Playwright快速开始.md)：由 Node 为每次会话新建和回收浏览器。
- [MCP 对接准备](doc/user-guide/MCP对接准备.md)：为 Agent 提供受管理资源和访问许可。
- [画面采集](doc/user-guide/浏览器画面采集.md)、[运行与排障](doc/deployment/运行与排障.md)。

Node 的本机 CDP 端点和身份秘密留在所有者设备；调用方取得的是独立访问许可。公开 HTTP／MCP 接口和 SDK 调用方集成说明由 RunBridge Hub 项目维护。

## 开发与维护

源码安装、构建、测试和开发联调见[本地开发与联调](doc/development/本地开发与联调.md)。完整架构、协议维护资料和历史验收见[文档导航](doc/README.md)。
