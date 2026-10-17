# Node 受管理 Chromium

[文档导航](../README.md) · [Node 部署](../deployment/部署与运行.md) · [配置字段](../reference/部署配置与凭据.md) · [许可管理](快速开始.md)

适用于 Node 0.5.0。Node 为每个会话启动独立 Chromium，并在释放时确认自建进程退出。先安装本项目 wheel、完成远程身份登记，后续在 Node 部署目录操作。

## 1. 准备 Node.js 和 npm

```bash
node --version
npm --version
```

需要 Node.js >=20 和 PATH 中的 npm。它们用于私有 npm Playwright 服务，与 Python 的 runbridge-node 角色不同。Node 不需要调用方的 Python Playwright SDK。

## 2. 安装私有运行时

```bash
.venv/bin/runbridge-node prepare-playwright --runtime-dir .runbridge/playwright --node-executable node
```

命令使用包内锁文件安装 Playwright **1.63.0** 和 Chromium，在所选目录保存 `node_modules/`、`browsers/`、`npm-cache/`。浏览器本机库仍由设备环境准备；该命令不自动执行管理员级系统安装。

已有不同依赖文件时会拒绝覆盖，使用新的独立运行时目录。不要把其他项目的缓存目录当成本项目运行时，也不要手改包内锁文件来绕过版本检查。

## 3. 编写本地启动配置

保存为 `.runbridge/playwright.json`：

```json
{
  "runtime_directory": ".runbridge/playwright",
  "node_executable": "node",
  "resource_id": "chromium",
  "launch_options": {
    "headless": true
  }
}
```

```bash
chmod 600 .runbridge/playwright.json
```

配置示例也见 [Playwright 节点配置](../reference/examples/Playwright节点配置.json)。路径相对 Node 服务工作目录；使用 Node.js 绝对路径时，准备命令和 JSON 应选同一套运行时。全部字段、启动选项、代理和毫秒单位见[配置参考](../reference/部署配置与凭据.md)。

## 4. 启动资源并交付许可

```bash
.venv/bin/runbridge-node run --config .runbridge/node.json --playwright-config .runbridge/playwright.json
```

启动时 Node 会真实启动并关闭探测浏览器，再上报资源。保持服务终端，在另一个终端：

```bash
.venv/bin/runbridge-node grant --config .runbridge/node.json --resource-id chromium --expires-in 3600 --output .runbridge/playwright-access.json
.venv/bin/runbridge-node inspect node_example --access-file .runbridge/playwright-access.json
```

替换实际节点 ID。预期后端 `playwright`、资源类型 `MANAGED_CHROMIUM`、`READY/FREE`。返回版本是 npm Playwright 的版本，不是 Chromium 产品版本。

把访问文件和资源 ID 交给调用方。普通 SDK／HTTP 调用由 Hub 项目文档维护；给 Agent 准备资源见[MCP 对接](MCP对接准备.md)。调用方自己的 SDK 主次版本须与服务匹配，已验收版本为 1.63.0。

## 5. 生命周期与输出

每个资源同一时刻供一个会话使用；调用方申请会话后 Node 新建独立浏览器，不复用已有 Profile。普通 SDK 受管理会话没有独立画面流；MCP 持有的页面可由服务端提供同页画面，Node 无需 Browscreen。

Node 本地启动选项中的目录属于本设备；调用方截图、下载保存和 tracing 输出按远程 SDK 语义保存在调用方。正常释放还包含 helper／browser 退出及本次临时目录清理。cleanup 未确认时按[排障](../deployment/运行与排障.md)核对，不删除身份或共享运行时。
