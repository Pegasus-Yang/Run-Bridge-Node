# Node 配置与 CLI 输出示例

[文档导航](../../README.md) · [Node 部署](../../deployment/部署与运行.md) · [字段与凭据](../部署配置与凭据.md)

本目录面向 Node 所有者，提供本机资源配置和 Node CLI 可观察的基础输出结构。

| 文件 | 用途 |
| --- | --- |
| [Chrome节点配置.json](Chrome节点配置.json) | 保存明确授权的本机固定浏览器实例，实际端点须由所有者填入 |
| [Playwright节点配置.json](Playwright节点配置.json) | 受管理 Chromium 的私有运行时和启动设置 |
| [节点查询示例.json](节点查询示例.json) | inspect 可观察的节点基础字段，实际输出还可包含 visual |
| [会话状态示例.json](会话状态示例.json) | session 命令的基础状态结构 |
| [连接错误示例.json](连接错误示例.json) | Node 控制连接公开错误结构 |

身份文件由 register 生成，访问 JSON 由 grant 生成；演示值不能替代实际身份或许可。完整字段、默认值与权限见配置参考。

维护者的 SDK、画面和客户端回归样例位于[开发联调区](../../development/调用方联调.md)。用户公开接口集成由 Hub 项目文档维护。
