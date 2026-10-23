# Python worker 执行与清理

当前 Node 0.8.1：每个会话使用当前 Node `.venv` 的 Python 启动一个 `runbridge_node.worker` 进程。主进程管理控制心跳、资源占用、出站执行连接和清理；worker 持有 Playwright 及对象表，显式分派白名单动作。通用 worker 只处理工具错误、信封、队列和结果，不导入 Playwright。

managed 使用 Python chromium.launch，新建 context/page；borrowed 使用 Python connect_over_cdp(no_defaults=True)，枚举已有页面。无需 npm BrowserServer、launchServer 或导出的原生 wsEndpoint。内部 Python driver 的存在是 Playwright 包自己的实现，项目不要求单独的系统 Node.js。

managed 显式保留 `--password-store=basic` 与 `--use-mock-keychain`，专用测试浏览器不使用系统凭据库，详见[测试数据存储](../deployment/浏览器凭据与测试数据.md)。borrowed 的鼠标、键盘与表单输入先激活所指定 Page，避免后台页暂停动画帧而卡在 actionability 等待；只读操作不激活页面。

Node 与 worker 以 4 字节大端长度 + UTF-8 JSON 管道通信，单消息最大 16 MiB。Hub 到 Node 的执行 WS 也是项目 JSON，不是 SDK 对象协议。session_ready 的页面目录放在执行通道，确认后才通过小控制消息完成准备。

对象有当前会话的不可猜用途编号，目标类型/会话归属/关闭状态均在执行前验证；Locator 是有类型的步骤列表。工具适配器显式实现 33 项方法，不按远程属性路径反射，不执行传入 Python 或 evaluate 脚本。DOM 采集只运行项目固定脚本。

写调用进入 SDK 后超时仍可能已经发生副作用，返回 OUTCOME_UNKNOWN。SDK 自身支持的 timeout 用剩余预算，外部等待 shield 分离，不直接取消正在调用 Playwright 的协程。关闭会话先关闭受管理浏览器或借用连接，再结束动作消费者；主进程检查实际回收结果。

每个 worker 获得 `/tmp/rb-*` 短私有目录，规避长部署路径触发 Chromium UNIX socket 限制。活动记录和目录内 ownership marker 相互核对，记录 worker PID/创建时间/模式。managed 浏览器还需 Profile 位于专用 TMPDIR、进程创建时间匹配。清理只触及这些明确拥有的子进程和目录，先正常关闭，必要时终止/杀死已核验的本次进程。损坏记录或归属不明返回 UNKNOWN，资源隔离。

Node 意外重启后先恢复活动记录，核验清理再探测浏览器。worker SIGKILL 和 driver 异常均需实际检查本次浏览器退出；不会把 Python 已退出当作 COMPLETE。borrowed 原 Chrome 由所有者管理，永不当作本次自建进程回收。

扩展工具应在 tools 的显式创建器、版本化方法输入/输出合同和启动资源探测处登记本地实现。队列、请求去重及结果信封保持共用；当前没有实现额外工具或远程插件市场。
