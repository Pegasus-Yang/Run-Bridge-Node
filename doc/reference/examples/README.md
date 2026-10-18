# Node 配置与查询输出示例

[文档导航](../../README.md) · [首次部署](../../deployment/部署与运行.md) · [字段与凭据](../部署配置与凭据.md)

本目录提供 Node 所有者会遇到的文件格式。**首次安装按部署教程操作**：它说明真实登记文件如何接收、身份由哪条命令生成、浏览器配置怎样保存。不要按本目录文件顺序直接执行。

## 推荐的统一启动文件

[Node启动配置.yaml](Node启动配置.yaml) 逐字段注释了含义、默认值、首次启动要求、路径规则，并提供互斥的 Chrome 模式写法。替换真实地址与路径、保存为 `node.yaml` 后，在其所在部署目录运行 `runbridge-node run --settings node.yaml`；首次自动登记并上线。身份仍由程序保存为 JSON，不需要手工从 YAML 抄出字段。

本地相对路径以 YAML 所在目录为基准。已有 npm Playwright 可直接指定其项目根目录；使用官方浏览器缓存时设置 `use_default_browser_cache: true`。Chrome 模式按[Chrome 指南](../../user-guide/Chrome复用快速开始.md)把实际授权端点写入同一文件。

## 旧方式的独立浏览器 JSON

以下 JSON 接口继续兼容，供已有部署使用；首次使用优先统一 YAML，不需要同时维护两套浏览器配置。

| 文件 | 实际数据从哪里来 | 使用位置 |
| --- | --- | --- |
| [Chrome节点配置.json](Chrome节点配置.json) | 资源名由所有者确定；真实端点来自已授权 Chrome 的 /json/version | [Chrome 指南](../../user-guide/Chrome复用快速开始.md)说明对应授权字段 |
| [Playwright节点配置.json](Playwright节点配置.json) | 运行时目录来自已有、自行准备或可选 prepare-playwright；Node.js 命令来自本机环境 | [受管理指南](../../user-guide/Playwright快速开始.md)说明对应运行时字段 |

Chrome 文件里的浏览器 ID 是演示值，不能直接连接；模式指南会读取真实端点并更新 YAML。Playwright 示例的相对目录以 Node 部署工作目录为准。

登记文本从 Hub 部署者取得；`node.json` 由统一启动或 register 生成，`access.json` 由 grant 生成。它们的秘密不能用本文示例字符串替代，也不用自己手写一份设备身份。

## 查询和消息输出

| 文件 | 含义 |
| --- | --- |
| [节点查询示例.json](节点查询示例.json) | inspect 的实际 JSON 结构，演示受管理资源 ONLINE、READY／FREE |
| [会话状态示例.json](会话状态示例.json) | session get 的实际 JSON 结构，演示 ACTIVE 会话、尚未释放 |
| [连接错误示例.json](连接错误示例.json) | Node 控制连接收到的 error 消息，不是任意网络错误的统一结构 |

输出示例中的 ID、时间、机器和版本信息是说明性数据，不代表当前设备在线。状态处于不同阶段，不能把三个文件当作一次任务的连续日志；这些输出也不是可以传给 `run --config` 的身份配置。

面向维护者的客户端回归脚本在[开发联调区](../../development/调用方联调.md)。公开 HTTP／MCP／SDK 的调用步骤由 Hub 项目手册维护。
