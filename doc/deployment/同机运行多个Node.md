# 同机运行多个 Node

简体中文 · [English](同机运行多个Node.en.md)

支持同一设备并行运行多个 Node，每个 Node 0.8.1 进程提供一个配置的 Playwright 资源。不同实例必须有独立的身份文件；复用同一身份会被 Hub 当作重连并替换旧连接。

最直接的方式为每个实例建立独立部署目录和 `.venv`，分别按[部署手册](部署与运行.md)安装相同版本，保存各自 `node.yaml`。也可以共享同一已安装环境，通过同一 CLI 绝对路径启动不同 YAML，但环境升级会影响全部实例，升级前均需停止。

```text
~/runbridge-node-a/node.yaml → .runbridge/node.json（身份 A）
~/runbridge-node-b/node.yaml → .runbridge/node.json（身份 B）
```

相对身份路径以各 YAML 目录为基准，因此上面两个路径实际上不同。名称分别设置 `office-a`/`office-b`；资源名均为 chromium 也可以，因为资源由 node_id+resource_id 唯一确定。

```bash
# 分别在两个终端前台运行；每个目录已经按部署手册准备完毕。
cd ~/runbridge-node-a
.venv/bin/runbridge-node run --settings node.yaml
```

另一个终端使用 b 目录及其命令。交付两个不同node_id，调用方分别从Hub领取两个Node，再创建各自会话。可以共享只读浏览器安装缓存，每个 managed 会话有独立 worker、短临时目录和 Profile；不共享身份、活动记录或浏览器对象。

borrowed 实例应分别授权不同 Chrome/Profile。两个 Node 同时指向同一 Chrome 会同时修改同一组页面，本项目无法提供跨实例的页面独占保障，部署时不要把这种配置当作两个隔离资源。

只正常停止目标实例，不使用按进程名批量杀浏览器的命令。当前同一个 Node 资源只接受一个活动会话；需要同机并行任务时使用上述独立实例。
