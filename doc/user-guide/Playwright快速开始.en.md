# Managed Chromium

[简体中文](Playwright快速开始.md) · English

Node uses Python Playwright `chromium.launch()` to create a browser for each session, an initial context with viewport `1280×720` and locale `zh-CN`, and an `about:blank` page. This suits independent tasks and MCP; login state is not retained from previous sessions.

Follow [deployment](../deployment/部署与运行.en.md) and configure `tools.playwright.mode: managed` (the default). Installing `[playwright]` places Python Playwright in the same environment; no separate npm installation is needed.

Prepare a matching browser and system libraries using the [Playwright guide](https://playwright.dev/python/docs/browsers). Reuse a matching installation when available. Keep cache configuration consistent during installation and execution; YAML `browser_cache_directory` can override the default. Node does not download browsers or alter system libraries.

`run --settings node.yaml` enrolls, probes, and connects. Probing creates and closes a dedicated browser before any task session. Client session creation then starts an independent worker. Close, expiry, or revocation cleans up this session's Chromium and temporary profile; unconfirmed cleanup reports UNKNOWN and quarantines the resource.

Continue with deployment step 5 to verify and hand off identifiers; a second Node process is unnecessary. Defaults are documented in the [annotated YAML](../reference/examples/Node启动配置.en.yaml).
