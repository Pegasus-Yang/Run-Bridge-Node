# RunBridge Node 文档导航

[项目首页](../README.md)

本导航对应 Node **0.5.0**。用户文档面向 Node 所有者：前提是远程 Hub 已由服务端部署者准备。

## 部署与日常使用

1. **首次操作从[部署与运行](deployment/部署与运行.md)第 1～5 节开始**：接收 Hub 地址和真实登记文件、安装 Node、自动生成并登记身份。
2. 按部署第 6 节选择[Chrome 复用](user-guide/Chrome复用快速开始.md)或[受管理 Chromium](user-guide/Playwright快速开始.md)，在所选指南完成配置和一次启动。
3. 按指南返回部署第 7 节，在新终端核对状态、生成访问 JSON 并交给调用方；保持原 Node 服务运行，不重复启动。

部署完成后再按需阅读：

- [状态检查与许可管理](user-guide/快速开始.md)：日常查询、单独签发、交付、撤销和续期。
- [MCP 对接准备](user-guide/MCP对接准备.md)：向 Agent 使用者交付受管理资源和 MCP 信息。
- [画面采集](user-guide/浏览器画面采集.md)：已有 Chrome 的可选扩展与实际画面检查。
- [运行与排障](deployment/运行与排障.md)、[配置文件示例](reference/examples/README.md)。

[Node 配置与凭据](reference/部署配置与凭据.md)供查字段、默认值与参数，不是首次操作的必读前置步骤。正文已包含配置生成命令和文件内容说明。

Hub 的 HTTP／MCP、SDK 调用和画面订阅接口由 Hub 项目的用户指南及接口参考维护。Node 所有者向调用方交付访问文件和资源信息即可。

## 开发者与维护者

- [本地开发与联调](development/本地开发与联调.md)：源码依赖、构建、回归与开发环境。
- [调用方联调](development/调用方联调.md)：用于 Node 回归的独立客户端样例。
- [Node 协议维护参考](development/protocol/对外接口总览.md)、[控制协议](development/protocol/R1接口与控制协议.md)、[执行隧道](development/protocol/会话接口与原生连接.md)、[画面上传](development/protocol/浏览器画面流接口.md)。
- [基础实现](architecture/R0与R1实现.md)、[会话管理](architecture/Playwright执行与会话管理.md)、[Chrome 授权与清理](architecture/Chrome复用与授权清理.md)、[画面采集与分发](architecture/浏览器画面采集与分发.md)。
- [项目概况](project/项目概况.md)、[方案总览](project/方案总览.md)、[范围调整](project/范围调整记录.md)。
- 设计阅读：[范围与架构](design/节点服务范围与架构.md)、[技术栈](design/Python3.14技术栈可行性.md)、[存储](design/管理网关与存储选型.md)、[原生契约](design/节点接入与原生执行契约.md)、[执行工具](design/客户端与执行工具接入.md)、[验证计划](design/最小实现与验证计划.md)、[画面扩展方案](design/Browscreen可选扩展与浏览器画面流方案.md)、[公开依据](reference/公开依据与研究边界.md)。

## 历史验收资料

[DSH 修复](project/DSH扩展修复验收.md)、[DSH 联调](project/DSH与受管理画面联调.md)、[画面流](project/浏览器画面流验收记录.md)、[虚拟机跨机器与字体](project/虚拟机Node跨机器验收记录.md)、[Chrome](project/R4Chrome复用验收记录.md)、[Playwright](project/Playwright阶段验收记录.md)、[R0/R1](project/R0与R1验收记录.md)。

历史数据只代表当次验收；早期完整归档位于 `project/history/`。当前机器的跨项目私有调试记录集中于 Hub 工作区的 Git 忽略 `local/`，不参与用户部署。
