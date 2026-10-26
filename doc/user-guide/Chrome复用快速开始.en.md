# Reuse an existing Chrome instance

[简体中文](Chrome复用快速开始.md) · English

Run these steps on the Node device for a Chrome instance already prepared and authorized by its owner. Node does not start or restart that browser. The owner manages remote debugging, a dedicated profile, and browser requirements according to the [Chrome documentation](https://developer.chrome.com/blog/remote-debugging-port).

## Identify the authorized instance

Use a fixed local Browser WebSocket, such as `ws://127.0.0.1:9222/devtools/browser/ACTUAL_ID`. If the owner has enabled loopback debugging, they can obtain `webSocketDebuggerUrl` from that instance's `/json/version`. This is not a page `/devtools/page/ID` endpoint or an HTTP discovery URL. Keep the debug port local and do not hand it to clients.

Authorization is **BROWSER_INSTANCE**, covering every page and existing login in that instance. A single-page-only intent does not authorize this mode. Restarting Chrome changes its ID; the owner must reconfirm and update YAML.

Replace the tool section in deployment step 4:

```yaml
tools:
  playwright:
    resource_id: chrome  # Custom ID; omitted still defaults to chromium.
    mode: borrowed
    authorization_scope: BROWSER_INSTANCE
    cdp_endpoint: ws://127.0.0.1:9222/devtools/browser/ACTUAL_ID
```

Remove managed `launch_options` and `browser_cache_directory`. Install Node's `[playwright]` extra and start using the same `run --settings node.yaml` command. The worker uses `connect_over_cdp(no_defaults=True)` to enumerate original contexts/pages and reuse their cookies and localStorage. Clients choose pages from actual returned references and URLs.

## Ownership and page behavior

Session release disconnects RunBridge, preserving original Chrome, contexts, pages, and login state. Page interactions already performed remain. An explicit client `page.close` still closes its chosen page; closing an original borrowed context is rejected. A newly created context does not inherit the original login automatically.

Mouse, keyboard, and form input bring the explicitly selected Page to the foreground, avoiding waits caused by background animation-frame suspension. Read-only queries and streaming do not activate a page. Same-URL pages require content checks to choose a unique reference; do not silently select the first page.

Node cannot change startup arguments of a running Chrome or require keychain approval. See [credentials and test data](../deployment/浏览器凭据与测试数据.en.md) for dedicated test-browser storage.

For continuous frames, install the optional `[visual]` extra; ordinary actions do not require it. See [page capture](浏览器画面采集.en.md). MCP `browser_start` currently selects managed resources; borrowed uses Hub's HTTP interface.

Return to [deployment](../deployment/部署与运行.en.md) step 5. Hand off resource `chrome`, its mode, and the exact intended page URL. The client claims Node through Hub and checks readiness.
