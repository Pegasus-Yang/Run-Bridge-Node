# 同一设备运行多个 Node

[文档导航](../README.md) · [首次部署](部署与运行.md) · [配置参考](../reference/部署配置与凭据.md)

支持同一设备同时运行多个 **不同身份**的 Node 进程。每个 Node 当前只有一个浏览器资源位；需要两个独立受管理会话并行时，可以运行两个 Node。它们可以连接同一个 Hub，也可以分别连接不同 Hub。

## 1. 每个实例必须独立的内容

| 内容 | 规则 |
| --- | --- |
| YAML | 每个进程一份，集中保存该实例的 Hub、身份和资源设置 |
| 身份文件 | 每个实例独立生成，不能复制一份 `node.json` 当作两个实例 |
| 访问许可 | 通过对应身份分别签发，只能操作对应节点及被授权资源 |
| 受管理浏览器 | 每个会话新建专用浏览器和临时目录；项目自动选择回环端口 |
| 已有 Chrome | 每个 Node 绑定不同实际实例；Profile 和调试端口由所有者分别准备 |

资源 ID 属于节点内部，两个不同 Node 都叫 `chromium` 没有冲突，调用方通过 `node_id + resource_id` 区分。设备 CPU、内存、显示环境和文件系统仍共享，不等于虚拟机级隔离。

**同一身份的第二个连接会替换旧连接，旧进程会退出；这不是扩容方式。**多个 Node 也不能重复发布同一 Chrome 实例：Hub 的资源占用按 Node 分别管理，不会跨身份判断两条资源是否指向同一个真实浏览器。

## 2. 示例：两个受管理 Node，共享已准备的运行时

先完成[首次部署](部署与运行.md)的安装和登记文本接收，并按受管理指南准备可用运行时。下面假定运行时为部署根目录的 `.runbridge/playwright`，登记文本为 `.runbridge/enrollment.token`。

```bash
cd ~/runbridge-node
mkdir -p instances/a instances/b
```

新建 `instances/a/node.yaml`：

```yaml
hub_url: http://192.168.50.10:8787
name: office-a
identity_file: .runbridge/node.json
enrollment_token_file: ../../.runbridge/enrollment.token
playwright:
  runtime_directory: ../../.runbridge/playwright
  resource_id: chromium
  launch_options:
    headless: true
```

新建 `instances/b/node.yaml`，内容相同但 `name` 改为 `office-b`。两份 `identity_file` 看起来相同，但分别相对各自 YAML 的目录解析，最终生成：

```text
instances/a/.runbridge/node.json
instances/b/.runbridge/node.json
```

将 Hub 地址改为实际值；不同 Hub 还须分别配置其真实登记文件。为两个 YAML 设置 0600 权限。

终端 A：

```bash
cd ~/runbridge-node
.venv/bin/runbridge-node run --settings instances/a/node.yaml
```

终端 B：

```bash
cd ~/runbridge-node
.venv/bin/runbridge-node run --settings instances/b/node.yaml
```

两个进程可以复用同一个安装好的 Python `.venv` 和稳定的 npm Playwright／浏览器缓存，无需为每个 Node 重新安装工具。运行期间不要对共享环境或运行时执行安装、升级、删除；需要独立升级、不同版本或权限隔离时，使用各自的虚拟环境和运行时目录。

## 3. 分别签发和交付

在第三个终端，选择对应的身份：

```bash
cd ~/runbridge-node
.venv/bin/runbridge-node grant --config instances/a/.runbridge/node.json --resource-id chromium --expires-in 3600 --output instances/a/.runbridge/access.json
.venv/bin/runbridge-node grant --config instances/b/.runbridge/node.json --resource-id chromium --expires-in 3600 --output instances/b/.runbridge/access.json
```

分别按[状态检查](../user-guide/快速开始.md)查询各自 Node ID，确认 ONLINE、READY/FREE，再将正确访问文件交给对应调用方。两份文件的 `node_id` 应不同；不能用 A 的许可访问 B，也不能用新许可接管旧许可的会话。

停止或重启时对每个进程单独操作。先释放该 Node 的会话，再向其终端发送 Ctrl+C／SIGTERM；保留其原身份。只停止 A 不需要停止 B。升级共享程序环境前，应先正常停止所有使用该环境的 Node。
