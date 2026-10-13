"""借用所有者明确授权的 Chrome；只管理连接，不管理浏览器进程。"""

import asyncio
import json
import logging
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.protocol import State

from runbridge_node.config import NodeConfig
from runbridge_node.executor import Execution, NATIVE_MAX_BYTES, pump, websocket_url
from runbridge_node.visual import VisualPublisher
from runbridge_node.visual_capture import probe_visual
from runbridge_node.visual_protocol import VISUAL_PROTOCOL
from runbridge_node.protocol import BackendCapability, CapabilitySnapshot, Identifier, Model, ResourceCapability, SessionClosed, SessionConnect, SessionOpen, SessionPrepared, SessionStop


logger = logging.getLogger(__name__)
FORBIDDEN_METHODS = {"Browser.close", "Browser.crash", "Target.sendMessageToTarget"}


class ChromeConfig(Model):
    """由本机所有者授予整个浏览器实例的控制范围。"""

    resource_id: Identifier = "chrome"
    authorization_scope: Literal["BROWSER_INSTANCE"]
    cdp_endpoint: SecretStr

    @field_validator("cdp_endpoint")
    @classmethod
    def endpoint(cls, value: SecretStr) -> SecretStr:
        """固定浏览器 ID 和本机地址，拒绝按端口自动寻找其他实例。

        :returns: 原端点，不在日志或视图中交付。
        """
        parsed = urlsplit(value.get_secret_value())
        if parsed.scheme != "ws" or parsed.hostname not in {"127.0.0.1", "::1"} or parsed.port is None or parsed.port == 0 or parsed.username or parsed.password or parsed.query or parsed.fragment or re.fullmatch(r"/devtools/browser/[A-Za-z0-9_-]+", parsed.path) is None:
            raise ValueError("需要本机明确的 Chrome 浏览器 WebSocket 端点")
        return value


async def browser_version(*, websocket) -> str:
    """只读探测 Google Chrome，不附加页面或改变上下文。

    :param websocket: 当前本机连接。
    :returns: 实际 Chrome 版本。
    """
    await websocket.send(json.dumps({"id": 1, "method": "Browser.getVersion"}))
    result = json.loads(await asyncio.wait_for(websocket.recv(), timeout=3))
    product = result.get("result", {}).get("product", "")
    match = re.fullmatch(r"(?:Headless)?Chrome/(\d+\.\d+\.\d+\.\d+)", product)
    if result.get("id") != 1 or match is None:
        raise ValueError("端点没有提供受支持的 Chrome 版本")
    return match.group(1)


async def forward_commands(*, tunnel, browser) -> None:
    """保留 CDP 原帧，仅拒绝退出浏览器及不透明旧协议封装。

    :param tunnel: 已授权调用连接。
    :param browser: 固定的本机浏览器连接。
    """
    while True:
        frame = await tunnel.recv()
        command = json.loads(frame)
        if not isinstance(command, dict) or not isinstance(command.get("id"), int) or not isinstance(command.get("method"), str):
            raise ValueError("CDP 请求格式无效")
        if command["method"] in FORBIDDEN_METHODS:
            response = {"id": command["id"], "error": {"code": -32000, "message": "RUNBRIDGE_BORROWED_BROWSER_COMMAND_FORBIDDEN"}}
            if "sessionId" in command:
                response["sessionId"] = command["sessionId"]
            await tunnel.send(json.dumps(response))
        else:
            await browser.send(frame)


class ChromeExecutor:
    """一条借用 Chrome 资源位，无启动、关闭进程或 Profile 清理代码。"""

    def __init__(self, *, identity: NodeConfig, config: ChromeConfig):
        self.identity = identity
        self.config = config
        self.active: Execution | None = None
        self.ready = False
        self.quarantined = False
        self.version: str | None = None
        self.visual_available = False
        self.visual_support_cache: dict[int, bool] = {}

    def _connect(self):
        """始终连接所有者授权的固定端点。

        :returns: 本机 WebSocket 异步上下文。
        """
        return connect(uri=self.config.cdp_endpoint.get_secret_value(), proxy=None, max_size=NATIVE_MAX_BYTES, max_queue=4, close_timeout=2, open_timeout=5)

    async def probe(self) -> None:
        """用只读请求验证本机端点；结束后只断开探测连接。"""
        if self.quarantined:
            return
        try:
            async with self._connect() as browser:
                self.version = await browser_version(websocket=browser)
            self.ready = True
            self.visual_available = await probe_visual()
        except (OSError, ValueError, TimeoutError, ConnectionClosed, InvalidStatus):
            self.ready = False

    def snapshot(self, *, base: CapabilitySnapshot) -> CapabilitySnapshot:
        """仅上报版本、实例授权和占用，不泄露端点或页面内容。

        :returns: 当前能力快照。
        """
        view = base.model_copy(deep=True)
        view.backends.append(BackendCapability(name="chrome-cdp", installed=True if self.ready else None, runtime_version=self.version, version_status="DETECTED" if self.version else "NOT_PROBED", declared_protocols=["cdp"] + ([VISUAL_PROTOCOL] if self.visual_available else []), coverage_status="SUPPORTED" if self.ready else "REQUIRES_VERIFICATION"))
        view.resources.append(ResourceCapability(resource_id=self.config.resource_id, backend="chrome-cdp", kind="BORROWED_CHROME_CDP", authorization_scope=self.config.authorization_scope, readiness="READY" if self.ready and not self.quarantined else "UNAVAILABLE", occupancy="UNKNOWN" if self.quarantined else ("BUSY" if self.active is not None else "FREE")))
        return view

    async def start(self, *, message: SessionOpen, send, publish) -> None:
        """核验本机资源独占；调用方不能提交或替换端点。

        :param message: 已认证准备命令。
        :param send: 控制发送函数。
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
        """激活本次路由，不将调用方请求头交付用户浏览器。

        :param message: 当前会话接入通知。
        """
        if self.active is not None and self.active.message.session_id == message.session_id:
            self.active.activated.set()

    def stop(self, *, message: SessionStop) -> None:
        """结束本次连接；不向 Chrome 发送关闭命令。

        :param message: 当前停止通知。
        """
        if self.active is not None and self.active.message.session_id == message.session_id and not self.active.stopped.is_set() and not self.active.finishing:
            self.active.stopped.set()
            self.active.task.cancel()

    async def _serve(self, *, execution: Execution, send, publish) -> None:
        """连接固定实例、建立隧道、转发并确认连接已断开。

        :param execution: 当前执行。
        :param send: 控制发送函数。
        :param publish: 能力刷新函数。
        """
        message = execution.message
        browser = None
        prepared = False
        tasks = []
        error_code = None
        cleanup = "COMPLETE"
        visual = None
        try:
            await publish()
            browser = await self._connect()
            version = await browser_version(websocket=browser)
            if version != self.version:
                raise ValueError("Chrome 版本已变化，需要重新探测")
            url = websocket_url(hub_url=self.identity.hub_url, path=f"/v1/nodes/{self.identity.node_id}/sessions/{message.session_id}/tunnel")
            async with connect(uri=url, additional_headers={"Authorization": f"Bearer {self.identity.node_token.get_secret_value()}", "x-runbridge-generation": str(message.connection_generation)}, max_size=NATIVE_MAX_BYTES, max_queue=4, close_timeout=2, open_timeout=10) as tunnel:
                await send(message=SessionPrepared(connection_generation=message.connection_generation, session_id=message.session_id, runtime_version=version))
                prepared = True
                tasks = [asyncio.create_task(execution.activated.wait()), asyncio.create_task(execution.stopped.wait()), asyncio.create_task(browser.wait_closed()), asyncio.create_task(tunnel.wait_closed())]
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
                if not execution.activated.is_set() or execution.stopped.is_set() or browser.state == State.CLOSED:
                    if browser.state == State.CLOSED:
                        error_code = "CHROME_CONNECTION_LOST"
                    return
                if self.visual_available:
                    visual = VisualPublisher(identity=self.identity, endpoint=self.config.cdp_endpoint.get_secret_value(),
                                             message=message, support_cache=self.visual_support_cache)
                    visual.start()
                tasks = [asyncio.create_task(forward_commands(tunnel=tunnel, browser=browser)), asyncio.create_task(pump(source=browser, target=tunnel)), asyncio.create_task(execution.stopped.wait())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        except asyncio.CancelledError:
            pass
        except ConnectionClosed:
            if browser is not None and browser.state == State.CLOSED:
                error_code = "CHROME_CONNECTION_LOST"
        except (OSError, ValueError, TimeoutError, InvalidStatus):
            error_code = "CHROME_CONNECT_FAILED" if not prepared else "CDP_CONNECTION_FAILED"
        finally:
            execution.finishing = True
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if visual is not None and await visual.close() != "COMPLETE":
                cleanup = "UNKNOWN"
                self.quarantined = True
                self.ready = False
            if browser is not None:
                try:
                    await browser.close()
                    await browser.wait_closed()
                except (OSError, TimeoutError):
                    cleanup = "UNKNOWN"
                    self.quarantined = True
                    self.ready = False
            if not prepared or error_code == "CHROME_CONNECTION_LOST":
                self.ready = False
            if execution.interrupted:
                error_code = "NODE_CONTROL_DISCONNECTED"
            if self.active is execution:
                self.active = None
            try:
                if not prepared:
                    await send(message=SessionPrepared(connection_generation=message.connection_generation, session_id=message.session_id, error_code=error_code or "CHROME_CONNECT_FAILED"))
                await send(message=SessionClosed(connection_generation=message.connection_generation, session_id=message.session_id, cleanup=cleanup, error_code=error_code))
                await publish()
            except (OSError, ConnectionClosed, TimeoutError):
                pass
            logger.info("Chrome 借用会话结束 session_id=%s cleanup=%s", message.session_id, cleanup)

    async def shutdown(self) -> None:
        """控制失联或停止 Node 时仅释放本次浏览器连接。"""
        if self.active is not None:
            execution = self.active
            execution.interrupted = True
            if not execution.stopped.is_set() and not execution.finishing:
                execution.stopped.set()
                execution.task.cancel()
            await asyncio.gather(execution.task, return_exceptions=True)
