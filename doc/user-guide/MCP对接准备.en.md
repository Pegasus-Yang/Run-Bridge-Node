# Prepare Node for MCP clients

[简体中文](MCP对接准备.md) · English

The Node owner's role is to configure a managed resource using [deployment](../deployment/部署与运行.en.md), install this package's `[playwright]`, prepare compatible Chromium, and verify ONLINE, READY, and FREE. Node needs no MCP server package or Playwright WebSocket handoff.

Give clients the Node ID, resource ID, and mode. The Hub deployer supplies the claim credential and actual MCP endpoint. Clients claim Node through Hub; Node does not issue access files. Hub confirms whether MCP is enabled. The 27 Hub tools, including request-status queries, use this Node's Python worker where execution is needed.

Borrowed Chrome uses project HTTP; MCP `browser_start` does not select borrowed resources. To offer both modes, use [separate Node instances](../deployment/同机运行多个Node.en.md) with distinct identities and resource notes. Client-side configuration is documented by [Hub MCP integration](https://github.com/Pegasus-Yang/Run-Bridge-Hub/blob/main/doc/user-guide/MCP浏览器接入.en.md).
