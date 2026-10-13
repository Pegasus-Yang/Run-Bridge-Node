"""Node 侧资源检查、原生 Playwright 隧道和自建浏览器清理。"""

import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from runbridge_node.config import NodeConfig, write_private_json
from runbridge_node.protocol import BackendCapability, CapabilitySnapshot, ResourceCapability, SessionClosed, SessionConnect, SessionOpen, SessionPrepared, SessionStop
from runbridge_node.runtime import BrowserServer, PLAYWRIGHT_VERSION, PlaywrightConfig


logger = logging.getLogger(__name__)
NATIVE_MAX_BYTES = 16 * 1024 * 1024


def websocket_url(*, hub_url: str, path: str) -> str:
    """沿用 Hub 基址前缀，生成无秘密的 WebSocket 地址。

    :returns: WS/WSS 地址。
    """
    parsed = urlsplit(hub_url)
    return urlunsplit(("wss" if parsed.scheme == "https" else "ws", parsed.netloc, f"{parsed.path}{path}", "", ""))


async def pump(*, source, target) -> None:
    """逐消息保留文本或二进制类型，直接等待下游发送。

    :param source: 原生入口。
    :param target: 原生出口。
    """
    while True:
        await target.send(await source.recv())


@dataclass
class Execution:
    """一条本机资源位的当前会话。"""

    message: SessionOpen
    activated: asyncio.Event = field(default_factory=asyncio.Event)
    stopped: asyncio.Event = field(default_factory=asyncio.Event)
    headers: dict[str, str] = field(default_factory=dict)
    task: asyncio.Task | None = None
    finishing: bool = False
    interrupted: bool = False


class PlaywrightExecutor:
    """单个受管理 Chromium 实例独占资源位。"""

    def __init__(self, *, identity: NodeConfig, config: PlaywrightConfig):
        self.identity = identity
        self.config = config
        self.active: Execution | None = None
        self.ready = False
        self.quarantined = False
        self.node_version = None
        self.managed_visual = False
        self.quarantine_file = config.runtime_directory / f"cleanup-unknown-{identity.node_id}.json"

    async def probe(self) -> None:
        """实际启动并关闭一个浏览器，区分安装和就绪。"""
        if self.quarantine_file.exists():
            self.quarantined = True
        if self.quarantined:
            self.ready = False
            return
        server = BrowserServer(config=self.config)
        try:
            metadata = await server.start()
            self.node_version = metadata["node_version"]
            self.managed_visual = metadata.get("managed_visual") is True
            self.ready = True
        except (OSError, ValueError, TimeoutError):
            self.ready = False
        finally:
            if await server.close() != "COMPLETE":
                self.quarantined = True
                self.ready = False
                self._record_unknown(server=server, session_id="probe")

    def _record_unknown(self, *, server: BrowserServer, session_id: str) -> None:
        """保留未确认清理的资源标记，重启不能绕过隔离。

        :param server: 本次自建进程。
        :param session_id: 会话或探测标识。
        """
        if not self.quarantine_file.exists():
            write_private_json(path=self.quarantine_file, values={"node_id": self.identity.node_id, "session_id": session_id, "cleanup": "UNKNOWN", "helper_pid": server.process.pid if server.process is not None else None, "browser_pid": server.metadata.get("browser_pid") if server.metadata is not None else None, "temporary_directory": str(server.temporary_directory) if server.temporary_directory is not None else None})

    def snapshot(self, *, base: CapabilitySnapshot) -> CapabilitySnapshot:
        """将真实启动结果与当前占用合入能力视图。

        :returns: 新能力快照。
        """
        view = base.model_copy(deep=True)
        installed = (self.config.runtime_directory / "node_modules/playwright/package.json").is_file()
        backend = BackendCapability(name="playwright", installed=installed, runtime_version=PLAYWRIGHT_VERSION if self.ready else None, version_status="DETECTED" if self.ready else ("NOT_PROBED" if installed else "NOT_INSTALLED"), declared_protocols=["playwright"], coverage_status="SUPPORTED" if self.ready else "REQUIRES_VERIFICATION")
        view.backends = [item for item in view.backends if item.name != "playwright"] + [backend]
        view.resources.append(ResourceCapability(resource_id=self.config.resource_id, backend="playwright", kind="MANAGED_CHROMIUM", readiness="READY" if self.ready and not self.quarantined else "UNAVAILABLE", occupancy="UNKNOWN" if self.quarantined else ("BUSY" if self.active is not None else "FREE")))
        if self.node_version is not None:
            view.host["playwright_node_version"] = self.node_version
        if self.ready and self.managed_visual:
            view.host["managed_visual"] = "cdp-png"
        return view

    async def start(self, *, message: SessionOpen, send, publish) -> None:
        """再次核验本机资源，接受后异步启动以免阻塞心跳。

        :param message: 已认证的会话准备命令。
        :param send: 控制消息发送函数。
        :param publish: 能力刷新函数。
        """
        if message.resource_id != self.config.resource_id or not self.ready or self.quarantined or self.active is not None:
            await send(message=SessionPrepared(connection_generation=message.connection_generation, session_id=message.session_id, error_code="NODE_RESOURCE_UNAVAILABLE"))
            await send(message=SessionClosed(connection_generation=message.connection_generation, session_id=message.session_id, cleanup="COMPLETE"))
            return
        execution = Execution(message=message)
        self.active = execution
        execution.task = asyncio.create_task(self._serve(execution=execution, send=send, publish=publish))

    def activate(self, *, message: SessionConnect) -> None:
        """原样交付官方 SDK 的工具请求头，不交付调用方 Bearer。

        :param message: 当前会话连接参数。
        """
        if self.active is not None and self.active.message.session_id == message.session_id:
            self.active.headers = message.headers
            self.active.activated.set()

    def stop(self, *, message: SessionStop) -> None:
        """停止本次会话，不操作用户既有浏览器。

        :param message: 当前会话停止命令。
        """
        if self.active is not None and self.active.message.session_id == message.session_id and not self.active.stopped.is_set() and not self.active.finishing:
            self.active.stopped.set()
            self.active.task.cancel()

    async def _serve(self, *, execution: Execution, send, publish) -> None:
        """启动、准备隧道、接入 SDK，然后确认资源清理。

        :param execution: 本次会话。
        :param send: 控制发送函数。
        :param publish: 能力刷新函数。
        """
        message = execution.message
        server = BrowserServer(config=self.config)
        tasks = []
        error_code = None
        prepared = False
        try:
            await publish()
            metadata = await server.start()
            url = websocket_url(hub_url=self.identity.hub_url, path=f"/v1/nodes/{self.identity.node_id}/sessions/{message.session_id}/tunnel")
            async with connect(uri=url, additional_headers={"Authorization": f"Bearer {self.identity.node_token.get_secret_value()}", "x-runbridge-generation": str(message.connection_generation)}, max_size=NATIVE_MAX_BYTES, max_queue=4, close_timeout=2, open_timeout=10) as tunnel:
                await send(message=SessionPrepared(connection_generation=message.connection_generation, session_id=message.session_id, runtime_version=metadata["version"]))
                prepared = True
                tasks = [asyncio.create_task(execution.activated.wait()), asyncio.create_task(execution.stopped.wait()), asyncio.create_task(server.process.wait()), asyncio.create_task(tunnel.wait_closed())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
                if not execution.activated.is_set() or execution.stopped.is_set() or server.process.returncode is not None:
                    return
                async with connect(uri=metadata["endpoint"], additional_headers=execution.headers, user_agent_header=None, proxy=None, max_size=NATIVE_MAX_BYTES, max_queue=4, close_timeout=2, open_timeout=10) as native:
                    tasks = [asyncio.create_task(pump(source=tunnel, target=native)), asyncio.create_task(pump(source=native, target=tunnel)), asyncio.create_task(execution.stopped.wait()), asyncio.create_task(server.process.wait())]
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
        except asyncio.CancelledError:
            pass
        except ConnectionClosed as error:
            if error.rcvd is None or error.rcvd.code not in {1000, 1001}:
                error_code = "NATIVE_CONNECTION_LOST"
        except (OSError, ValueError, TimeoutError, InvalidStatus):
            error_code = "PLAYWRIGHT_START_FAILED" if not prepared else "NATIVE_CONNECTION_FAILED"
        finally:
            execution.finishing = True
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            cleanup = await server.close()
            if execution.interrupted:
                error_code = "NODE_CONTROL_DISCONNECTED"
            if cleanup != "COMPLETE":
                self.quarantined = True
                self.ready = False
                self._record_unknown(server=server, session_id=message.session_id)
            if self.active is execution:
                self.active = None
            try:
                if not prepared:
                    await send(message=SessionPrepared(connection_generation=message.connection_generation, session_id=message.session_id, error_code=error_code or "PLAYWRIGHT_START_FAILED"))
                await send(message=SessionClosed(connection_generation=message.connection_generation, session_id=message.session_id, cleanup=cleanup, error_code=error_code))
                await publish()
            except (OSError, ConnectionClosed, TimeoutError):
                pass
            logger.info("浏览器会话结束 session_id=%s cleanup=%s", message.session_id, cleanup)

    async def shutdown(self) -> None:
        """控制连接失效时停止执行，重连不恢复原生对象。"""
        if self.active is not None:
            task = self.active.task
            self.active.interrupted = True
            if not self.active.stopped.is_set() and not self.active.finishing:
                self.active.stopped.set()
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
