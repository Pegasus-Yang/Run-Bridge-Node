# 已有 Chrome 复用

本页在 Node 设备操作，适用于已经由所有者准备、允许本机 CDP 连接的 Chrome 实例。Node 不启动或重启该浏览器；浏览器的远程调试启用方式、专用 Profile 和版本要求由 [Chrome 官方文档](https://developer.chrome.com/blog/remote-debugging-port)及设备管理员管理。

## 确定授权实例

需要本机固定 Browser WebSocket，例如 `ws://127.0.0.1:9222/devtools/browser/实际ID`。如果所有者已启用回环调试端口，可由所有者访问该实例的 `/json/version`，取 `webSocketDebuggerUrl`；不是页面的 `/devtools/page/ID`，也不是 HTTP 探测地址。不要向网络开放此调试端口，也不要将它交给调用方。

授权是 **BROWSER_INSTANCE**，覆盖该实例所有页面和原有登录。不能用只授权单页的意图配置这个模式。浏览器重启会改变 ID，需要所有者重新确认并更新 YAML。

在部署手册第 4 步，用下面片段替换 tools 段：

```yaml
tools:
  playwright:
    resource_id: chrome  # 自定义资源名；省略仍默认 chromium，grant 必须一致。
    mode: borrowed  # 必填以选择已有浏览器；默认是 managed。
    authorization_scope: BROWSER_INSTANCE  # 必填，明确授权整个实例。
    cdp_endpoint: ws://127.0.0.1:9222/devtools/browser/实际ID  # 本机固定实例，禁止查询参数或凭据。
```

不要同时配置 launch_options/browser_cache_directory。安装 Node 的 `[playwright]` extra 后，使用同一条 `run --settings node.yaml` 上线。Python worker 通过 `connect_over_cdp(no_defaults=True)` 连接原实例，枚举原 context/page，复用其中 Cookie 与 localStorage。多页时不猜目标；调用方通过返回的页面 URL/引用选择。

释放会话只关闭项目连接，不关闭原 Chrome/context/page，不清除登录；已经发生的点击或输入保留。调用方显式 page.close 仍会关闭它选中的页面，因此访问许可应交给获授权的调用方；原 context 的 context.close 被拒绝。调用方新建的独立 context 也不会自动冒充原登录上下文。

如需该模式的持续画面，安装 Node `[visual]` extra，见[画面采集](浏览器画面采集.md)。普通操作不要求它。MCP 的 browser_start 当前只使用 managed；borrowed 通过 Hub 的项目 HTTP 合同操作。

完成后回到[部署手册](../deployment/部署与运行.md)第 5 步，用资源 ID `chrome` 签发许可、检查 READY/FREE，并另外告诉调用方应操作页面的精确 URL。
