# Node 使用权迁移验收

日期：2026-10-23。Node 0.8.0配套Hub 0.9.0；本地验证和提交，不推送，不升级日常或远程部署。

Node已删除grant/revoke CLI和设备客户端发证/撤销方法。node_token只认证设备控制、执行与画面上传；注册、实际能力探测、worker执行及清理合同保持。inspect/session保留为使用Hub现有租约的可选诊断，不作为上线授权步骤。

AccessConfig保持hub_url、node_id、grant_id、access_token、expires_at五字段，诊断CLI读取JSON或YAML；未知字段拒绝，Hub申请文件不能冒充执行访问文件。调用方通过Hub统一领取、续租、释放整个Node，不新增用户或设备侧租约配置。

## 验证

- 项目根.venv完整pytest：75 passed，含71项普通检查和4项真实浏览器/worker检查。覆盖新CLI边界、JSON/YAML访问文件，以及原有managed/borrowed进程清理和资源保留。
- 根dist/runbridge_node-0.8.0-py3-none-any.whl在独立全新.venv安装，安装元数据、包内版本均为0.8.0，导入路径为site-packages；帮助只含register/run/inspect/session，设备发证方法不存在。
- 用新Hub 0.9.0与Node 0.8.0安装包完成11项真实MCP/Chromium联调，包含原令牌释放、清理确认、同Node新租约启动、旧令牌不能影响新持有者，以及文档调用示例。源码Hub完整188项通过。

跨端详细场景记录在runbridge-hub仓库doc/project/Node使用权租约改造验收.md。两端用新临时身份、令牌与数据，未复用用户登录Profile；实际浏览器清理及临时目录消失均已检查。DSH插件测试单独记录，不计入上述数字。

标准发行包为本仓库dist/runbridge_node-0.8.0-py3-none-any.whl及dist/runbridge_node-0.8.0.tar.gz。最终构建提交和SHA256由发行方记录，不以旧环境的源码版本代替安装包验收。旧身份及YAML格式保持，旧调用方许可按Hub 0.9.0迁移规则失效并重新领取；见[升级](../deployment/运行与排障.md)。
