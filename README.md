# RunBridge Node

**把本机浏览器作为可授权的远程执行资源。**

RunBridge Node 部署在浏览器设备上，主动连接已部署的 Hub，在本机 Python worker 中通过 Playwright 执行动作，再把结果和画面交给 Hub。浏览器地址和实际对象留在本机，调用方通过 Hub 使用资源。

[快速开始](doc/user-guide/快速开始.md) · [部署手册](doc/deployment/部署与运行.md) · [参数详解](doc/reference/参数详解.md) · [完整文档](doc/README.md)

## 能做什么

- **新建浏览器**：managed 模式为每次会话创建 Chromium，结束后回收本次进程和临时 Profile，适合独立任务及 MCP。
- **复用已有 Chrome**：borrowed 模式连接所有者明确授权的本机实例，释放会话时断开连接，保留原浏览器、页面与登录状态。
- **一份配置启动**：YAML 管理 Hub 地址、身份路径和浏览器选项，首次启动自动登记并探测浏览器。
- **按调用方授权**：签发独立访问文件，指定资源、到期时间，并可撤销许可与相关会话。
- **多个独立实例**：同机可用不同配置和身份运行多个 Node；每个实例管理自己的执行资源。
- **实际画面与清理状态**：支持受管理页面画面，borrowed 画面可选安装扩展；清理未确认时保留隔离状态。

当前版本 **0.7.0**，与 Hub **0.7.0** 配套。需要 Python **3.14.x**；不需要单独安装 Node.js/npm，也无需启动或记录 Playwright BrowserServer。

## 快速部署

以下操作全部在 **Node 设备**执行。先准备 Python 3.14.x 和全局 [uv](https://docs.astral.sh/uv/getting-started/installation/)，并取得：

- Hub 部署者交付的可达基址及真实 `enrollment.token` 文件。
- 发布负责人交付的 `runbridge_node-0.7.0-py3-none-any.whl`。

将两个文件保存到 `~/Downloads/`，创建独立部署目录：

```bash
mkdir -p ~/runbridge-node
cd ~/runbridge-node
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python "$HOME/Downloads/runbridge_node-0.7.0-py3-none-any.whl[playwright]" -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
umask 077
mkdir -p .runbridge
cp -n ~/Downloads/enrollment.token .runbridge/enrollment.token
chmod 600 .runbridge/enrollment.token
```

`[playwright]` 同时安装匹配的 Python Playwright。启动前，按 [Playwright 官方说明](https://playwright.dev/python/docs/browsers)为此环境准备 Chromium 及系统依赖；已有匹配浏览器可复用。基础工具和浏览器安装由环境管理员管理。

创建 `node.yaml`，**把示例 Hub 地址换成收到的真实基址**：

```yaml
hub_url: http://192.168.50.10:8787
enrollment_token_file: .runbridge/enrollment.token
tools:
  playwright: {}
```

这会采用默认的 managed Chromium、无头运行和身份路径。启动并保留终端：

```bash
.venv/bin/runbridge-node run --settings node.yaml
```

首次自动登记、探测浏览器并上线。已有身份会复用，无需先执行 `register`。路径相对于 YAML 所在目录；完整默认值和其他浏览器选择见[参数详解](doc/reference/参数详解.md)。

## 验证与交付

另开终端回到部署目录，签发一小时访问许可并查询节点：

```bash
cd ~/runbridge-node
.venv/bin/runbridge-node grant --expires-in 3600 --output .runbridge/access.json
rb_node_id=$(.venv/bin/python -c 'import json; from pathlib import Path; print(json.loads(Path(".runbridge/node.json").read_text())["node_id"])')
.venv/bin/runbridge-node inspect "$rb_node_id" --access-file .runbridge/access.json
```

确认 `connection_status=ONLINE`、`capabilities_stale=false`，资源 `chromium` 为 `READY/FREE`。随后按[快速开始的会话示例](doc/user-guide/快速开始.md#验证一次真实浏览器会话)验证浏览器创建与释放，确认 `cleanup=COMPLETE`。

将生成的 **access.json** 和资源 ID **chromium** 私密交给调用方。访问文件由程序生成，不要手写令牌；`node.json` 和登记文件继续由所有者保管。调用方按 Hub 项目的 HTTP/MCP 手册操作。

## 使用与维护

| 要做的事 | 阅读文档 |
| --- | --- |
| 从安装到真实会话验证、解决常见错误 | [快速开始](doc/user-guide/快速开始.md) |
| 完整部署、权限和交付步骤 | [部署与运行](doc/deployment/部署与运行.md) |
| 查询 CLI、YAML、浏览器参数和场景 | [参数详解](doc/reference/参数详解.md)、[带注释 YAML](doc/reference/examples/Node启动配置.yaml) |
| 选择新浏览器或已有登录环境 | [受管理 Chromium](doc/user-guide/Playwright快速开始.md)、[Chrome 复用](doc/user-guide/Chrome复用快速开始.md) |
| 同机多个 Node | [多实例部署](doc/deployment/同机运行多个Node.md) |
| 画面、钥匙链提示和私有测试数据 | [画面采集](doc/user-guide/浏览器画面采集.md)、[浏览器凭据与测试数据](doc/deployment/浏览器凭据与测试数据.md) |
| 故障、升级与许可管理 | [运行与排障](doc/deployment/运行与排障.md)、[快速开始](doc/user-guide/快速开始.md#日常许可管理) |

## 开发

源码位于 `src/runbridge_node/`，开发与测试使用项目根目录 `.venv`。依赖同步、pytest、wheel 构建和隔离浏览器测试见[本地开发与联调](doc/development/本地开发与联调.md)。

[Python worker 架构](doc/architecture/Playwright执行与会话管理.md)说明执行与清理流程，[完整导航](doc/README.md)汇总架构、开发资料和验收记录。报告问题时提供版本、已隐藏秘密的 YAML、错误码和复现步骤；不要提交身份令牌、访问令牌或真实浏览器 Profile。
