# Node 文档导航

简体中文 · [English](README.en.md)

当前用户手册适用于 **Node 0.8.2 / Hub 0.9.3**。源码体验从[项目首页](../README.md#快速开始)开始，已有 wheel 的独立目录部署从[快速开始](user-guide/快速开始.md)开始。

## 按任务开始

| 任务 | 推荐阅读路线 |
| --- | --- |
| 第一次提供浏览器设备 | 快速开始 → 部署与运行 → 参数与凭据 → 上线与交付 |
| 复用已有登录 | Chrome 复用 → 凭据与测试数据 → 页面选择与交付 |
| 同机并行任务 | 同机多个 Node → 独立身份 → 每个 Node 单独领取 |
| 接入 Agent 或观察页面 | MCP 对接准备 → 画面采集 → Hub 调用手册 |

## 使用、部署与配置

| 阅读目的 | 文档 |
| --- | --- |
| 快速安装、登记和可选诊断 | [快速开始](user-guide/快速开始.md) |
| 从零部署、交付和长期运行 | [部署与运行](deployment/部署与运行.md) |
| 查询 CLI、默认值和浏览器选项 | [参数详解](reference/参数详解.md)、[带注释 YAML](reference/examples/Node启动配置.yaml) |
| 区分启动配置、身份与访问文件 | [配置与凭据](reference/部署配置与凭据.md)、[配置示例](reference/examples/README.md) |
| 每次新建浏览器 | [受管理 Chromium](user-guide/Playwright快速开始.md) |
| 复用原有页面和登录 | [已有 Chrome](user-guide/Chrome复用快速开始.md) |
| 一台设备提供多个资源 | [同机多个 Node](deployment/同机运行多个Node.md) |
| 准备页面画面或 MCP 资源 | [画面采集](user-guide/浏览器画面采集.md)、[MCP 对接准备](user-guide/MCP对接准备.md) |
| 处理凭据提示与私有测试数据 | [浏览器凭据与测试数据](deployment/浏览器凭据与测试数据.md) |
| 处理故障、升级和清理未知 | [运行与排障](deployment/运行与排障.md) |
| 了解实际依赖与支持边界 | [当前依赖与实现边界](reference/当前依赖与实现边界.md) |

上述用户文档均提供对应英文版，可从每页顶部切换；[英文导航](README.en.md)直接连接英文手册。部分 CLI 与示例提示仍为中文。

## Hub 调用方文档

设备维护者交付 Node ID、资源 ID 与模式；调用方从 Hub 领取使用权。HTTP/MCP、租约和画面协议统一在 [Hub 文档](https://github.com/Pegasus-Yang/Run-Bridge-Hub/blob/main/doc/README.md)维护，Node 用户无需在本机部署 Hub。

## 开发、协作与历史资料

| 阅读目的 | 文档 |
| --- | --- |
| 准备 PyPI 分发 | [PyPI 发布准备](development/PyPI发布准备.md) |
| 参与贡献与授权 | [贡献指南](../CONTRIBUTING.md)、[MIT License](../LICENSE) |
| 开发与本地验证 | [本地开发与联调](development/本地开发与联调.md)、[工具适配方案](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/design/Python%E5%B7%A5%E5%85%B7%E6%89%A7%E8%A1%8C%E6%94%B9%E9%80%A0%E6%96%B9%E6%A1%88.md) |
| 当前架构与源码 | [代码结构](architecture/代码结构与执行流程.md)、[Python worker](architecture/Playwright执行与会话管理.md)、[已有 Chrome 清理](architecture/Chrome复用与授权清理.md) |
| 版本、打包与 GitHub 展示 | [版本发布记录](project/版本发布记录.md)、[版本发布与本地打包](development/版本发布与本地打包.md)、[GitHub 展示配置](project/GitHub展示配置.md) |
| 已有验证记录 | [租约迁移验收](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/project/Node%E4%BD%BF%E7%94%A8%E6%9D%83%E8%BF%81%E7%A7%BB%E9%AA%8C%E6%94%B6.md)、[快速上手验收](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/project/%E5%BF%AB%E9%80%9F%E4%B8%8A%E6%89%8B%E6%96%87%E6%A1%A3%E9%AA%8C%E6%94%B6.md)、[发布隔离验收](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/project/Python%E5%B7%A5%E5%85%B7%E6%89%A7%E8%A1%8C%E9%AA%8C%E6%94%B6%E8%AE%B0%E5%BD%95.md)、[日常环境验收](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/project/%E6%97%A5%E5%B8%B8%E7%8E%AF%E5%A2%83%E5%8D%87%E7%BA%A7%E4%B8%8E%E5%8A%9F%E8%83%BD%E9%AA%8C%E6%94%B6.md) |

架构、设计、发布和历史验收资料保留中文。旧 npm BrowserServer、原生隧道和早期开发协议副本不代表当前行为。`design/` 与 `project/history/` 保留原日期和语境；历史记录不代表本次重新进行了运行验收。

源码包保留当前用户文档；未随包分发的历史方案、验收和原始核验材料通过 GitHub 链接查阅。
