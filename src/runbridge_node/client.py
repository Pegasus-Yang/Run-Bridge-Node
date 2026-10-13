"""HTTP 管理调用与可重连的节点控制通道。"""

import asyncio
import logging
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import ValidationError
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from runbridge_node.capabilities import probe_capabilities
from runbridge_node.chrome import ChromeExecutor
from runbridge_node.config import NodeConfig, validate_hub_url
from runbridge_node.visual_protocol import NodeQueryView
from runbridge_node.executor import PlaywrightExecutor
from runbridge_node.protocol import OutgoingAdapter, SessionOpen, SessionConnect, SessionStop, SessionPrepared, SessionClosed, Acknowledgement, CapabilityReport, CapabilitySnapshot, ControlError, GrantCreated, GrantRequest, Heartbeat, RegistrationResult, Welcome


logger = logging.getLogger(__name__)
CONTROL_MAX_BYTES = 65_536


class ClientError(Exception):
    """可向调用者展示的错误，不包含请求原文与凭据。"""


async def request_json(*, hub_url: str, method: str, path: str, token: str, body: dict | None = None, timeout: float = 10) -> dict:
    """调用受保护管理接口，不自动重放写请求。

    :param hub_url: Hub 基址。
    :param method: HTTP 方法。
    :param path: 管理路径。
    :param token: 认证凭据。
    :param body: 可选请求体。
    :param timeout: 管理请求超时秒数。
    :returns: JSON 响应或空对象。
    """
    url = f"{validate_hub_url(value=hub_url)}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method=method, url=url, headers={"Authorization": f"Bearer {token}"}, json=body)
    except httpx.HTTPError:
        raise ClientError("Hub 网络请求失败；写请求结果需确认，不自动重发") from None
    if response.is_error:
        raise ClientError(f"Hub 拒绝请求（HTTP {response.status_code}）")
    if response.status_code == 204:
        return {}
    try:
        return response.json()
    except ValueError:
        raise ClientError("Hub 响应不是有效 JSON") from None


class NodeClient:
    """使用持久身份接入 Hub，网络失联后重新认证。"""

    def __init__(self, *, config: NodeConfig, capabilities: CapabilitySnapshot | None = None, executor: PlaywrightExecutor | ChromeExecutor | None = None):
        self.config = config
        self.capabilities = capabilities
        self.executor = executor

    async def register(self, *, enrollment_token: str) -> RegistrationResult:
        """首次登记或使用同一身份重试登记。

        :param enrollment_token: 部署方登记凭据。
        :returns: 无秘密的登记结果。
        """
        payload = {"node_id": self.config.node_id, "name": self.config.name, "node_token": self.config.node_token.get_secret_value()}
        result = await request_json(hub_url=self.config.hub_url, method="POST", path="/v1/nodes/register", token=enrollment_token, body=payload)
        return RegistrationResult.model_validate(result)

    async def create_grant(self, *, request: GrantRequest) -> GrantCreated:
        """创建独立对接许可。

        :param request: 许可范围与期限。
        :returns: 一次性交付的对接码。
        """
        result = await request_json(hub_url=self.config.hub_url, method="POST", path=f"/v1/nodes/{self.config.node_id}/grants", token=self.config.node_token.get_secret_value(), body=request.model_dump(mode="json"))
        return GrantCreated.model_validate(result)

    async def revoke(self, *, grant_id: str) -> None:
        """撤销对接许可，不更改节点身份。

        :param grant_id: 许可 ID。
        """
        await request_json(hub_url=self.config.hub_url, method="DELETE", path=f"/v1/nodes/{self.config.node_id}/grants/{grant_id}", token=self.config.node_token.get_secret_value())

    async def run(self, *, stop: asyncio.Event) -> None:
        """维持控制连接；认证错误与连接被替换时停止。

        :param stop: 停止信号。
        """
        delay = 0.5
        while not stop.is_set():
            try:
                await self._session(stop=stop)
                delay = 0.5
            except InvalidStatus as error:
                if error.response.status_code in {401, 403, 404}:
                    raise ClientError("控制连接身份被拒绝，请检查登记和节点配置") from None
                logger.warning("控制连接握手失败，将重试")
            except ConnectionClosed as error:
                if error.rcvd is not None and error.rcvd.code in {1008, 4001}:
                    raise ClientError("控制连接被拒绝或被同一身份的新连接替换") from None
                logger.warning("控制连接中断，将重新认证")
            except (OSError, TimeoutError):
                logger.warning("Hub 暂时不可达，将重试")
            if not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                except TimeoutError:
                    pass
                delay = min(10, delay * 2)

    async def _session(self, *, stop: asyncio.Event) -> None:
        """执行一次连接握手、能力上报与心跳会话。

        :param stop: 停止信号。
        """
        parsed = urlsplit(self.config.hub_url)
        url = urlunsplit(("wss" if parsed.scheme == "https" else "ws", parsed.netloc, f"{parsed.path}/v1/nodes/{self.config.node_id}/control", "", ""))
        send_lock = asyncio.Lock()
        async with connect(uri=url, additional_headers={"Authorization": f"Bearer {self.config.node_token.get_secret_value()}"}, max_size=CONTROL_MAX_BYTES, max_queue=16, open_timeout=10, close_timeout=2) as websocket:
            async def send(*, message):
                async with send_lock:
                    await websocket.send(message.model_dump_json())

            async def publish():
                value = self.executor.snapshot(base=snapshot) if self.executor is not None else snapshot
                await send(message=CapabilityReport(connection_generation=welcome.connection_generation, capabilities=value))

            try:
                welcome = Welcome.model_validate_json(await asyncio.wait_for(websocket.recv(), timeout=10))
                if welcome.node_id != self.config.node_id:
                    raise ClientError("Hub 返回的节点身份不匹配")
                snapshot = self.capabilities if self.capabilities is not None else await asyncio.to_thread(probe_capabilities)
                if self.executor is not None:
                    await self.executor.probe()
                await publish()
                acknowledgement = Acknowledgement.model_validate_json(await asyncio.wait_for(websocket.recv(), timeout=10))
                if acknowledgement.type != "capabilities_ack" or acknowledgement.connection_generation != welcome.connection_generation:
                    raise ClientError("Hub 能力确认与当前连接不匹配")
            except ValidationError:
                raise ClientError("Hub 控制合同不兼容") from None
            logger.info("节点在线 node_id=%s generation=%s", self.config.node_id, welcome.connection_generation)
            tasks = [asyncio.create_task(self._heartbeat(send=send, welcome=welcome, stop=stop)), asyncio.create_task(self._receive(websocket=websocket, generation=welcome.connection_generation, timeout=welcome.heartbeat_timeout_seconds, send=send, publish=publish))]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                if self.executor is not None:
                    await self.executor.shutdown()

    async def _heartbeat(self, *, send, welcome: Welcome, stop: asyncio.Event) -> None:
        """发送应用心跳，停止信号可立即结束等待。

        :param send: 串行控制发送函数。
        :param welcome: 协商参数。
        :param stop: 停止信号。
        """
        while not stop.is_set():
            await send(message=Heartbeat(connection_generation=welcome.connection_generation))
            try:
                await asyncio.wait_for(stop.wait(), timeout=welcome.heartbeat_interval_seconds)
            except TimeoutError:
                pass

    async def _receive(self, *, websocket, generation: int, timeout: float, send, publish) -> None:
        """校验 Hub 确认，发现协议错误后停止。

        :param websocket: 控制连接。
        :param generation: 当前连接代次。
        :param timeout: 应用确认的最长等待时间。
        """
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout)
            try:
                message = OutgoingAdapter.validate_json(raw)
                if isinstance(message, ControlError):
                    raise ClientError("Hub 拒绝控制消息")
                if message.connection_generation != generation:
                    raise ClientError("Hub 确认来自错误连接代次")
                if isinstance(message, SessionOpen):
                    if self.executor is not None:
                        await self.executor.start(message=message, send=send, publish=publish)
                    else:
                        await send(message=SessionPrepared(connection_generation=generation, session_id=message.session_id, error_code="BACKEND_UNAVAILABLE"))
                        await send(message=SessionClosed(connection_generation=generation, session_id=message.session_id, cleanup="COMPLETE"))
                elif isinstance(message, SessionConnect) and self.executor is not None:
                    self.executor.activate(message=message)
                elif isinstance(message, SessionStop) and self.executor is not None:
                    self.executor.stop(message=message)
            except (ValueError, ValidationError, AttributeError):
                raise ClientError("Hub 控制响应无效") from None


async def inspect_node(*, hub_url: str, node_id: str, token: str) -> NodeQueryView:
    """调用方不需要节点身份文件即可查询能力。

    :param hub_url: Hub 基址。
    :param node_id: 节点 ID。
    :param token: 对接凭据。
    :returns: 节点与能力视图。
    """
    result = await request_json(hub_url=hub_url, method="GET", path=f"/v1/nodes/{node_id}/capabilities", token=token)
    return NodeQueryView.model_validate(result)
