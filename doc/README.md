# Node 文档导航

当前操作手册适用于 Node/Hub **0.6.0**。

| 阅读目的 | 文档 |
| --- | --- |
| 从零部署并交付资源 | [部署与运行](deployment/部署与运行.md) |
| 快速安装、浏览器验证、日常许可 | [快速开始](user-guide/快速开始.md) |
| 每次新建浏览器 | [受管理 Chromium](user-guide/Playwright快速开始.md) |
| 复用原有页面和登录 | [已有 Chrome](user-guide/Chrome复用快速开始.md) |
| 一台机器提供多个资源 | [同机多个 Node](deployment/同机运行多个Node.md) |
| 查询配置格式与默认值 | [参数详解](reference/参数详解.md)、[配置与凭据](reference/部署配置与凭据.md)、[带注释 YAML](reference/examples/Node启动配置.yaml) |
| 画面与 MCP 准备 | [画面采集](user-guide/浏览器画面采集.md)、[MCP 对接准备](user-guide/MCP对接准备.md) |
| 当前执行与清理机制 | [Python worker](architecture/Playwright执行与会话管理.md)、[已有 Chrome 清理](architecture/Chrome复用与授权清理.md) |
| 源码模块与依赖边界 | [代码结构](architecture/代码结构与执行流程.md)、[当前依赖](reference/当前依赖与实现边界.md) |
| 钥匙链提示、测试账号保存 | [浏览器凭据与测试数据](deployment/浏览器凭据与测试数据.md) |
| 故障与升级 | [运行与排障](deployment/运行与排障.md) |
| 开发者 | [本地开发与联调](development/本地开发与联调.md)、[工具适配方案](design/Python工具执行改造方案.md) |

旧版本的 npm BrowserServer、原生协议隧道、开发协议副本和旧验收记录是历史资料，不代表 0.6.0 行为。Node 用户的操作路线不包含 Hub 部署或同机双端联调。

验证记录：[快速上手文档验收](project/快速上手文档验收.md)、[发布隔离验收](project/Python工具执行验收记录.md)、[日常环境升级与功能验收](project/日常环境升级与功能验收.md)。

`design/` 是评审记录，旧阶段验收、候选元数据 JSON 和 `project/history/` 保留原日期与语境；正文中当时的“当前”不代表现行部署要求。Node 用户按上表当前手册操作。
