# RunBridge Node

RunBridge Node 部署在浏览器设备上，主动连接远程 Hub，并在本机 Python worker 中使用 Playwright 执行动作。支持每次会话新建 Chromium，以及连接所有者明确授权的已有 Chrome。浏览器地址与对象留在本机，Hub 只下发结构化工具指令。

当前版本 **0.6.0**，配套 Hub **0.6.0**。需要 Python 3.14.x；本项目不再需要单独安装 Node.js、npm 运行时或收集 Playwright 服务地址。

从[部署与运行](doc/deployment/部署与运行.md)开始：取得登记文件 → 安装 Node 包 → 准备浏览器 → 填写 YAML → 一条命令登记并上线 → 签发访问文件并交付。

- [日常状态与许可管理](doc/user-guide/快速开始.md)
- [受管理 Chromium](doc/user-guide/Playwright快速开始.md)、[已有 Chrome](doc/user-guide/Chrome复用快速开始.md)
- [同机多个 Node](doc/deployment/同机运行多个Node.md)
- [YAML 与凭据格式](doc/reference/部署配置与凭据.md)、[画面采集](doc/user-guide/浏览器画面采集.md)
- [排障与升级](doc/deployment/运行与排障.md)、[开发说明](doc/development/本地开发与联调.md)
- [浏览器凭据与测试数据](doc/deployment/浏览器凭据与测试数据.md)：系统钥匙链、本地私有账号文件与浏览器 Profile 的边界。

[完整文档导航](doc/README.md)。调用方 HTTP/MCP 接入规则在 Hub 项目中；本手册只说明 Node 所有者的设备操作。
