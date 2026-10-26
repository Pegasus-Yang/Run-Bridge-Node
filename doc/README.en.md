# Node documentation

[简体中文](README.md) · English

Current user guides cover **Node 0.8.1 / Hub 0.9.2**. Start with the [README](../README.en.md#quick-start) for source installation or the [quick-start guide](user-guide/快速开始.en.md) for an existing wheel in a separate deployment directory.

## Choose your reading path

| Task | Path |
| --- | --- |
| Provide a browser device for the first time | Quick start → deployment → parameters/credentials → connection and handoff |
| Reuse existing login state | Existing Chrome → credentials/test data → explicit page choice and handoff |
| Run concurrent tasks on one device | Multiple Nodes → independent identities → separate claims |
| Prepare an agent resource or observe pages | MCP preparation → capture → Hub client guide |

## User guides, deployment, and settings

| Goal | English guide |
| --- | --- |
| Install, enroll, and run optional diagnostics | [Quick start](user-guide/快速开始.en.md) |
| Deploy, hand off, and run long term | [Deployment](deployment/部署与运行.en.md) |
| Look up CLI, defaults, and browser options | [Parameters](reference/参数详解.en.md), [annotated YAML](reference/examples/Node启动配置.en.yaml) |
| Distinguish startup, identity, and access files | [Credentials](reference/部署配置与凭据.en.md), [configuration examples](reference/examples/README.en.md) |
| Start a new browser per session | [Managed Chromium](user-guide/Playwright快速开始.en.md) |
| Reuse original pages and login | [Existing Chrome](user-guide/Chrome复用快速开始.en.md) |
| Provide multiple resources from one device | [Multiple Nodes](deployment/同机运行多个Node.en.md) |
| Prepare streaming or MCP resources | [Page capture](user-guide/浏览器画面采集.en.md), [MCP preparation](user-guide/MCP对接准备.en.md) |
| Handle credential prompts/private test data | [Browser credentials and test data](deployment/浏览器凭据与测试数据.en.md) |
| Diagnose, upgrade, and review unknown cleanup | [Operations](deployment/运行与排障.en.md) |
| Check runtime requirements and supported scope | [Dependencies and scope](reference/当前依赖与实现边界.en.md) |

Each guide links to its Chinese counterpart. Some CLI/example messages and Hub dashboard labels remain Chinese. English documentation does not change browser locale or runtime behavior.

## Hub client documentation

The device maintainer hands off Node ID, resource ID, and mode; clients claim ownership through Hub. HTTP/MCP, leases, and visual protocols are maintained in [Hub's English documentation](https://github.com/Pegasus-Yang/Run-Bridge-Hub/blob/main/doc/README.en.md). A Node user need not deploy Hub on the same device.

## Development and historical material

| Goal | Resource |
| --- | --- |
| Contribute and understand licensing | [Contributing](../CONTRIBUTING.en.md), [MIT License](../LICENSE) |
| Develop and validate | [Local development (Chinese)](development/本地开发与联调.md), [tool adapter design (Chinese)](design/Python工具执行改造方案.md) |
| Inspect implementation | [Code structure (Chinese)](architecture/代码结构与执行流程.md), [Python worker (Chinese)](architecture/Playwright执行与会话管理.md), [borrowed cleanup (Chinese)](architecture/Chrome复用与授权清理.md) |
| Read releases/builds or manage GitHub presentation | [Release record (Chinese)](project/版本发布记录.md), [packaging (Chinese)](development/版本发布与本地打包.md), [GitHub settings (Chinese)](project/GitHub展示配置.md) |
| Inspect recorded acceptance | [Lease migration (Chinese)](project/Node使用权迁移验收.md), [quick start (Chinese)](project/快速上手文档验收.md), [isolated release (Chinese)](project/Python工具执行验收记录.md), [daily environment (Chinese)](project/日常环境升级与功能验收.md) |

Architecture, design, release, and historical records remain Chinese. Old npm BrowserServer, native tunnels, and early protocol copies do not describe current behavior. `design/` and `project/history/` preserve their original dates and context; records do not constitute a new live acceptance run.
