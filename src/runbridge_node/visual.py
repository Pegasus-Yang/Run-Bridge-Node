"""授权会话的画面发布，采集和网络发送各自有界运行。"""

import asyncio
import json
import logging
from time import monotonic
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus, WebSocketException

from runbridge_node.capabilities import package_version
from runbridge_node.config import NodeConfig
from runbridge_node.executor import websocket_url
from runbridge_node.protocol import SessionOpen
from runbridge_node.visual_capture import CaptureProcess
from runbridge_node.visual_protocol import VisualFrame, VisualHello, VisualSelect, VisualSourceState, VisualTarget, VisualTargets
from runbridge_node.visual_wire import PNG_MAX_BYTES, STATE_MAX_BYTES, VISUAL_MAX_BYTES, pack_frame


logger = logging.getLogger(__name__)


class VisualPublisher:
    """只观察固定实例；失败不会向执行通道抛出异常。"""

    def __init__(self, *, identity: NodeConfig, endpoint: str, message: SessionOpen, support_cache: dict[int, bool]):
        self.identity = identity
        self.endpoint = endpoint
        self.message = message
        self.support_cache = support_cache
        self.targets: list[VisualTarget] = []
        self.state = VisualSourceState(state="WAITING", reason_code="WAITING_FOR_BROWSER")
        self.changed = asyncio.Event()
        self.changed.set()
        self.request: VisualSelect | None = None
        self.selected: str | None = None
        self.chosen = False
        self.capture: CaptureProcess | None = None
        self.latest: tuple[bytes, float, VisualFrame] | None = None
        self.source_key = None
        self.cleanup = "COMPLETE"
        self.task: asyncio.Task | None = None

    def start(self) -> None:
        """启动独立任务，执行连接无需等待首帧。"""
        self.task = asyncio.create_task(coro=self.run(), name=f"visual-{self.message.session_id}")

    def set_state(self, *, state: str, reason: str | None = None, request_id: str | None = None,
                  stream_id: str | None = None, target_id: str | None = None) -> None:
        """状态改变时丢弃待上传旧图；相同错误不重复发送。"""
        value = VisualSourceState(state=state, reason_code=reason, request_id=request_id,
                                  stream_id=stream_id, target_id=target_id)
        if value != self.state:
            self.state = value
            self.latest = None
            self.changed.set()

    async def stop_capture(self) -> bool:
        """清理只能作用于本实例创建的采集进程。"""
        if self.capture is not None:
            self.cleanup = await self.capture.close()
            if self.cleanup != "COMPLETE":
                return False
            self.capture = None
        self.latest = None
        return True

    async def choose(self, *, target_id: str, request_id: str | None = None) -> None:
        """先停旧源再创建新源，目标来自已验证的实例目录。"""
        if not await self.stop_capture():
            self.set_state(state="ERROR", reason="VISUAL_CLEANUP_UNKNOWN", request_id=request_id)
            return
        self.selected = target_id
        self.chosen = True
        self.source_key = None
        self.capture = CaptureProcess()
        parsed = urlsplit(self.endpoint)
        endpoint = urlunsplit((parsed.scheme, parsed.netloc, f"/devtools/page/{target_id}", "", ""))
        try:
            await self.capture.start(endpoint=endpoint)
        except (OSError, ValueError, TimeoutError):
            await self.stop_capture()
            self.set_state(state="ERROR", reason="VISUAL_WORKER_FAILED", request_id=request_id)
            return
        self.set_state(state="WAITING", reason="SCREENSHOT_NOT_READY", request_id=request_id,
                       stream_id=f"stream_{uuid4().hex}", target_id=target_id)

    async def monitor(self) -> None:
        """通过独立浏览器连接读目标，绝不读取执行连接的消息。"""
        async with connect(uri=self.endpoint, proxy=None, max_size=1024 * 1024, max_queue=1, close_timeout=1, open_timeout=5) as browser:
            command_id = 0
            while True:
                command_id += 1
                async with asyncio.timeout(delay=5):
                    await browser.send(message=json.dumps({"id": command_id, "method": "Target.getTargets"}))
                    while True:
                        response = json.loads(await browser.recv())
                        if response.get("id") == command_id:
                            break
                if "error" in response:
                    raise ValueError("浏览器观察请求失败")
                pages = sorted((item for item in response["result"]["targetInfos"] if item.get("type") == "page"),
                               key=lambda item: item["targetId"])
                values = [VisualTarget(target_id=item["targetId"], label=f"页面 {index + 1}") for index, item in enumerate(pages)]
                if len(values) > 256:
                    raise ValueError("浏览器页面超过合同上限")
                if values != self.targets:
                    self.targets = values
                    self.changed.set()
                ids = {item.target_id for item in values}
                if self.selected is not None and self.selected not in ids:
                    await self.stop_capture()
                    self.selected = None
                    self.set_state(state="WAITING_TARGET", reason="TARGET_CLOSED")
                request = self.request
                self.request = None
                if request is not None:
                    if request.target_id in ids:
                        await self.choose(target_id=request.target_id, request_id=request.request_id)
                    else:
                        self.set_state(state="ERROR", reason="VISUAL_TARGET_NOT_FOUND", request_id=request.request_id)
                elif not self.chosen:
                    if len(values) == 1:
                        await self.choose(target_id=values[0].target_id)
                    elif values:
                        self.set_state(state="WAITING_TARGET", reason="TARGET_SELECTION_REQUIRED")
                    else:
                        self.set_state(state="WAITING", reason="NO_PAGE")
                await asyncio.sleep(delay=0.3)

    async def poll(self, *, client: httpx.AsyncClient) -> None:
        """本机图片读取不等待 Hub 发送，旧响应不混入新目标。"""
        errors = {"waiting_for_browser": ("WAITING", "WAITING_FOR_BROWSER"),
                  "screenshot_not_ready": ("WAITING", "SCREENSHOT_NOT_READY"),
                  "browser_wait_timeout": ("ERROR", "BROWSER_WAIT_TIMEOUT"),
                  "capture_failed": ("ERROR", "CAPTURE_FAILED")}
        while True:
            capture, source = self.capture, self.state
            if capture is not None and capture.url is not None and source.stream_id is not None:
                try:
                    async with client.stream(method="GET", url=f"{capture.url}/api/screenshot", timeout=2) as response:
                        if capture is not self.capture or source.stream_id != self.state.stream_id:
                            continue
                        if response.status_code == 503:
                            body = json.loads(await response.aread())
                            state, reason = errors.get(body.get("code"), ("ERROR", "CAPTURE_FAILED"))
                            self.set_state(state=state, reason=reason, stream_id=source.stream_id,
                                           target_id=source.target_id, request_id=source.request_id)
                        else:
                            response.raise_for_status()
                            parts, size = [], 0
                            async for part in response.aiter_bytes():
                                size += len(part)
                                if size > PNG_MAX_BYTES:
                                    raise ValueError("FRAME_TOO_LARGE")
                                parts.append(part)
                            metadata = VisualFrame(connection_generation=self.message.connection_generation,
                                session_id=self.message.session_id, resource_id=self.message.resource_id,
                                stream_id=source.stream_id, target_id=source.target_id,
                                frame_id=response.headers["X-Frame-Id"], capture_started_at=response.headers["X-Capture-Started-At"])
                            key = (metadata.stream_id, metadata.frame_id, metadata.capture_started_at)
                            if capture is self.capture and source.stream_id == self.state.stream_id and key != self.source_key:
                                # 出图后恢复等待基线，后续相同源错误仍须通知并撤下旧图。
                                self.set_state(state="WAITING", reason="SCREENSHOT_NOT_READY", stream_id=source.stream_id,
                                               target_id=source.target_id, request_id=source.request_id)
                                self.latest = (pack_frame(metadata=metadata, png=b"".join(parts)), monotonic(), metadata)
                                self.source_key = key
                                self.changed.set()
                except (httpx.HTTPError, OSError, ValueError, KeyError) as error:
                    if capture is self.capture and source.stream_id == self.state.stream_id:
                        reason = "FRAME_TOO_LARGE" if str(error) == "FRAME_TOO_LARGE" else "CAPTURE_SERVICE_UNAVAILABLE"
                        self.set_state(state="ERROR", reason=reason, stream_id=source.stream_id,
                                       target_id=source.target_id, request_id=source.request_id)
            await asyncio.sleep(delay=0.3)

    async def send(self, *, websocket) -> None:
        """控制快照与最新帧各保留一个，阻塞发送不会阻塞采集。"""
        last_targets, last_state, last_key = None, None, None
        self.changed.set()
        while True:
            await self.changed.wait()
            self.changed.clear()
            targets, state, latest = self.targets, self.state, self.latest
            async with asyncio.timeout(delay=2):
                if targets != last_targets:
                    await websocket.send(message=VisualTargets(targets=targets).model_dump_json())
                    last_targets = targets
                if state != last_state:
                    await websocket.send(message=state.model_dump_json())
                    last_state = state
                if latest is not None:
                    data, queued_at, metadata = latest
                    key = (metadata.stream_id, metadata.frame_id)
                    if (key != last_key and monotonic() - queued_at <= 5 and
                            (metadata.stream_id, metadata.target_id) == (state.stream_id, state.target_id)):
                        await websocket.send(message=data)
                        last_key = key

    async def receive(self, *, websocket) -> None:
        """只接收源选择，不接受任意浏览器命令。"""
        while True:
            raw = await websocket.recv()
            if not isinstance(raw, str) or len(raw.encode()) > STATE_MAX_BYTES:
                raise ValueError("画面源请求无效")
            self.request = VisualSelect.model_validate_json(raw)

    async def upload(self) -> None:
        """同一代次恢复上传，禁止恢复已终止执行会话。"""
        delay = 0.5
        url = websocket_url(hub_url=self.identity.hub_url,
            path=f"/v1/nodes/{self.identity.node_id}/sessions/{self.message.session_id}/visual/upload")
        while True:
            tasks = []
            try:
                async with connect(uri=url, additional_headers={"Authorization": f"Bearer {self.identity.node_token.get_secret_value()}",
                    "x-runbridge-generation": str(self.message.connection_generation)}, max_size=VISUAL_MAX_BYTES,
                    max_queue=1, close_timeout=1, open_timeout=5) as websocket:
                    self.latest = None
                    await websocket.send(message=VisualHello(browscreen_version=package_version(name="browscreen")).model_dump_json())
                    tasks = [asyncio.create_task(coro=self.send(websocket=websocket)), asyncio.create_task(coro=self.receive(websocket=websocket))]
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
            except InvalidStatus as error:
                if error.response.status_code in {401, 403, 404, 410}:
                    return
            except (WebSocketException, OSError, TimeoutError, ValueError):
                pass
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(delay=delay)
            delay = min(10, delay * 2)

    async def run(self) -> None:
        """Hub 不支持时仅退出画面扩展，基础控制和执行继续。"""
        tasks = []
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False, follow_redirects=False) as client:
                generation = self.message.connection_generation
                if generation not in self.support_cache:
                    response = await client.get(url=f"{self.identity.hub_url}/v1/nodes/{self.identity.node_id}/visual/support",
                        headers={"Authorization": f"Bearer {self.identity.node_token.get_secret_value()}"})
                    self.support_cache.clear()
                    self.support_cache[generation] = response.status_code == 200 and response.json().get("visual_protocol_version") == 1
                if not self.support_cache[generation]:
                    logger.info("Hub 未支持画面扩展，原执行继续")
                    return
                tasks = [asyncio.create_task(coro=self.monitor()), asyncio.create_task(coro=self.poll(client=client)),
                         asyncio.create_task(coro=self.upload())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        except (OSError, ValueError, KeyError, TimeoutError, WebSocketException, httpx.HTTPError):
            logger.warning("画面扩展暂不可用，原执行继续")
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.stop_capture()

    async def close(self) -> str:
        """停止观察与发送，并返回真实的自有资源清理状态。"""
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        await self.stop_capture()
        return self.cleanup
