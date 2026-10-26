# GitHub 展示配置

本仓库对应 [Pegasus-Yang/Run-Bridge-Node](https://github.com/Pegasus-Yang/Run-Bridge-Node)，网关端为 [Run-Bridge-Hub](https://github.com/Pegasus-Yang/Run-Bridge-Hub)。

## About 信息

在仓库首页 About 的设置中使用以下文案：

| 字段 | 内容 |
| --- | --- |
| Description | 连接 RunBridge Hub 的浏览器执行节点：受管理 Chromium、已有 Chrome 复用、Python Playwright 执行与页面画面采集。 |
| Website | `https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/README.md` |
| Topics | `runbridge` `browser-automation` `remote-browser` `playwright` `chromium` `cdp` `python` `self-hosted` |

README、LICENSE 与包元数据随代码推送；Description、Website 和 Topics 是独立的 GitHub 仓库设置，需要另行保存。

## 展示内容维护

- 主页提供中英文 README，中文为默认入口，包含项目介绍、Python 与许可证徽章、worker 架构图、两种浏览器模式对比和源码安装步骤。
- Node 的 HTTP/MCP 入口由 Hub 提供。更新说明时保留 managed 与 borrowed 的调用、画面和清理差异。
- 更新版本时同步主页中的两端版本关系、安装命令与 `pyproject.toml`，按[发布规范](../development/版本发布与本地打包.md)完成构建与检查。
- 许可证正文位于根目录 `LICENSE`，包中的许可证清单由 `pyproject.toml` 的 `license-files` 定义；第三方依赖保留各自授权。
- 贡献入口为根目录 [CONTRIBUTING.md](../../CONTRIBUTING.md)，运行与使用资料由[文档导航](../README.md)汇总。

中英文用户文档分别由 `doc/README.md` 与 `doc/README.en.md` 导航；修改功能说明、命令或参数时同步两种语言。架构、设计及历史验收资料保留中文，并在英文导航中注明。
