# Node documentation

[简体中文](README.md) · English

Current user guides cover **Node 0.8.2 / Hub 0.9.3**. Start with the [README](../README.en.md#quick-start) for source installation or the [quick-start guide](user-guide/快速开始.en.md) for an existing wheel in a separate deployment directory.

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
| Follow the complete publishing workflow and pitfalls | [Release workflow](development/发布流程与注意事项.en.md) |
| Validate and publish GitHub Releases | [GitHub Actions](development/GitHubActions与Release.en.md) |
| Prepare a PyPI distribution | [PyPI release preparation](development/PyPI发布准备.en.md) |
| Contribute and understand licensing | [Contributing](../CONTRIBUTING.en.md), [MIT License](../LICENSE) |
| Develop and validate | [Local development (Chinese)](development/本地开发与联调.md), [tool adapter design (Chinese)](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/design/Python%E5%B7%A5%E5%85%B7%E6%89%A7%E8%A1%8C%E6%94%B9%E9%80%A0%E6%96%B9%E6%A1%88.md) |
| Inspect implementation | [Code structure (Chinese)](architecture/代码结构与执行流程.md), [Python worker (Chinese)](architecture/Playwright执行与会话管理.md), [borrowed cleanup (Chinese)](architecture/Chrome复用与授权清理.md) |
| Read releases/builds or manage GitHub presentation | [Release record (Chinese)](project/版本发布记录.md), [packaging (Chinese)](development/版本发布与本地打包.md), [GitHub settings (Chinese)](project/GitHub展示配置.md) |
| Inspect recorded acceptance | [Lease migration (Chinese)](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/project/Node%E4%BD%BF%E7%94%A8%E6%9D%83%E8%BF%81%E7%A7%BB%E9%AA%8C%E6%94%B6.md), [quick start (Chinese)](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/project/%E5%BF%AB%E9%80%9F%E4%B8%8A%E6%89%8B%E6%96%87%E6%A1%A3%E9%AA%8C%E6%94%B6.md), [isolated release (Chinese)](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/project/Python%E5%B7%A5%E5%85%B7%E6%89%A7%E8%A1%8C%E9%AA%8C%E6%94%B6%E8%AE%B0%E5%BD%95.md), [daily environment (Chinese)](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/project/%E6%97%A5%E5%B8%B8%E7%8E%AF%E5%A2%83%E5%8D%87%E7%BA%A7%E4%B8%8E%E5%8A%9F%E8%83%BD%E9%AA%8C%E6%94%B6.md) |

Architecture, design, release, and historical records remain Chinese. Old npm BrowserServer, native tunnels, and early protocol copies do not describe current behavior. `design/` and `project/history/` preserve their original dates and context; records do not constitute a new live acceptance run.

The source distribution includes current user documentation. Historical designs, acceptance records, and raw audit material omitted from it are linked on GitHub.
