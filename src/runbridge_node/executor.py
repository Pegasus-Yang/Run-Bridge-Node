"""Node 工具资源、项目指令连接与 Python worker 管理。"""

import asyncio
import logging
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from runbridge_node.config import NodeConfig
from runbridge_node.protocol import (
    BackendCapability,
    CapabilitySnapshot,
    ResourceCapability,
    SessionClosed,
    SessionOpen,
    SessionPrepared,
    SessionStop,
)
from runbridge_node.runtime import PlaywrightConfig, ToolWorker, recover_record
from runbridge_node.tool_contract import METHODS, MAX_MESSAGE
from runbridge_node.visual_protocol import VISUAL_PROTOCOL


logger = logging.getLogger(__name__)


def websocket_url(*, hub_url: str, path: str) -> str:
    parsed = urlsplit(hub_url)
    return urlunsplit(
        (
            "wss" if parsed.scheme == "https" else "ws",
            parsed.netloc,
            f"{parsed.path}{path}",
            "",
            "",
        )
    )


@dataclass
class Execution:
    message: SessionOpen
    stopped: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None


class PlaywrightExecutor:
    """一个明确资源位只运行一个 Python 工具会话。"""

    def __init__(
        self, *, identity: NodeConfig, config: PlaywrightConfig, state_directory: Path
    ):
        self.identity = identity
        self.config = config
        self.state_directory = state_directory
        self.active = None
        self.ready = False
        self.quarantined = False
        self.visual_available = False
        self.visual_support_cache = {}
        self.runtime_version = None

    async def probe(self):
        self.state_directory.mkdir(parents=True, exist_ok=True)
        for record in self.state_directory.glob("*.json"):
            if await recover_record(path=record) != "COMPLETE":
                self.quarantined = True
        if self.quarantined:
            return
        worker = ToolWorker(
            config=self.config, record_path=self.state_directory / "probe.json"
        )
        try:

            async def ignore(value):
                pass

            metadata = await worker.start(
                session_id=f"probe_{uuid4().hex}", generation=1, callback=ignore
            )
            self.runtime_version = metadata["runtime_version"]
            self.ready = True
            if self.config.mode == "managed":
                self.visual_available = metadata.get("visual_ready") is True
            else:
                from runbridge_node.visual_capture import probe_visual

                self.visual_available = await probe_visual()
        except OSError, ValueError, TimeoutError:
            self.ready = False
        finally:
            if await worker.close() != "COMPLETE":
                self.quarantined = True
                self.ready = False

    def snapshot(self, *, base: CapabilitySnapshot) -> CapabilitySnapshot:
        value = base.model_copy(deep=True)
        backend = "playwright" if self.config.mode == "managed" else "chrome-cdp"
        try:
            installed = version("playwright")
        except PackageNotFoundError:
            installed = None
        protocols = ["runbridge-execution-v2"] + (
            [VISUAL_PROTOCOL] if self.visual_available else []
        )
        value.backends = [
            BackendCapability(
                name=backend,
                installed=installed is not None,
                runtime_version=self.runtime_version,
                version_status="DETECTED" if self.ready else "NOT_PROBED",
                declared_protocols=protocols,
                coverage_status="SUPPORTED" if self.ready else "REQUIRES_VERIFICATION",
            )
        ]
        value.resources = [
            ResourceCapability(
                resource_id=self.config.resource_id,
                backend=backend,
                kind="MANAGED_CHROMIUM"
                if self.config.mode == "managed"
                else "BORROWED_CHROME_CDP",
                authorization_scope=self.config.authorization_scope,
                tool="playwright",
                tool_api_version=1,
                methods=list(METHODS),
                readiness="READY"
                if self.ready and not self.quarantined
                else "UNAVAILABLE",
                occupancy="UNKNOWN"
                if self.quarantined
                else ("BUSY" if self.active else "FREE"),
            )
        ]
        return value

    async def start(self, *, message: SessionOpen, send, publish):
        if (
            message.resource_id != self.config.resource_id
            or message.tool != "playwright"
            or message.tool_api_version != 1
            or not self.ready
            or self.quarantined
            or self.active
        ):
            await send(
                message=SessionPrepared(
                    connection_generation=message.connection_generation,
                    session_id=message.session_id,
                    error_code="NODE_RESOURCE_UNAVAILABLE",
                )
            )
            await send(
                message=SessionClosed(
                    connection_generation=message.connection_generation,
                    session_id=message.session_id,
                    cleanup="COMPLETE",
                )
            )
            return
        execution = Execution(message=message)
        self.active = execution
        execution.task = asyncio.create_task(
            self.serve(execution=execution, send=send, publish=publish)
        )

    def stop(self, *, message: SessionStop):
        if self.active and self.active.message.session_id == message.session_id:
            self.active.stopped.set()

    async def serve(self, *, execution: Execution, send, publish):
        from runbridge_node.visual import VisualPublisher
        from runbridge_node.worker_visual import WorkerVisualPublisher

        message = execution.message
        worker = ToolWorker(
            config=self.config,
            record_path=self.state_directory / f"{message.session_id}.json",
        )
        websocket = None
        visual = None
        capture_targets = {}
        tasks = []
        error = None
        prepared = False

        async def receive_worker(value):
            nonlocal capture_targets
            kind = value.get("type")
            if kind == "capture_targets":
                capture_targets.clear()
                capture_targets.update(value["targets"])
            elif kind == "visual_frame":
                if isinstance(visual, WorkerVisualPublisher):
                    visual.frame(value=value)
            elif kind == "event":
                if isinstance(visual, WorkerVisualPublisher):
                    visual.objects(value=value["data"]["objects"])
                if websocket is not None and prepared:
                    await websocket.send(value_to_json(value=value))
            elif (
                kind in {"result", "command_ack", "command_started"}
                and websocket is not None
            ):
                await websocket.send(value_to_json(value=value))

        try:
            await publish()
            metadata = await worker.start(
                session_id=message.session_id,
                generation=message.connection_generation,
                callback=receive_worker,
                stop=execution.stopped,
            )
            capture_targets.update(metadata.get("capture_targets", {}))
            url = websocket_url(
                hub_url=self.identity.hub_url,
                path=f"/v2/nodes/{self.identity.node_id}/sessions/{message.session_id}/execution",
            )
            async with connect(
                uri=url,
                additional_headers={
                    "Authorization": f"Bearer {self.identity.node_token.get_secret_value()}",
                    "x-runbridge-generation": str(message.connection_generation),
                },
                max_size=MAX_MESSAGE,
                max_queue=4,
                close_timeout=2,
                open_timeout=10,
            ) as websocket:
                # 页面目录可能大于控制通道上限；在执行通道交付并确认后再报告准备完成。
                await websocket.send(
                    value_to_json(
                        value={
                            "protocol_version": 2,
                            "type": "session_ready",
                            "session_id": message.session_id,
                            "connection_generation": message.connection_generation,
                            "runtime_version": metadata["runtime_version"],
                            "objects": metadata["objects"],
                        }
                    )
                )
                import json

                acknowledgement = json.loads(
                    await asyncio.wait_for(websocket.recv(), timeout=10)
                )
                if acknowledgement != {
                    "protocol_version": 2,
                    "type": "session_ready_ack",
                    "session_id": message.session_id,
                    "connection_generation": message.connection_generation,
                }:
                    raise ValueError("INVALID_SESSION_PREPARATION")
                await send(
                    message=SessionPrepared(
                        connection_generation=message.connection_generation,
                        session_id=message.session_id,
                        runtime_version=metadata["runtime_version"],
                    )
                )
                prepared = True
                if self.visual_available:
                    if self.config.mode == "managed":
                        visual = WorkerVisualPublisher(
                            identity=self.identity, message=message, worker=worker
                        )
                        visual.objects(value=metadata["objects"])
                    else:
                        visual = VisualPublisher(
                            identity=self.identity,
                            endpoint=self.config.cdp_endpoint,
                            message=message,
                            support_cache=self.visual_support_cache,
                            target_map=capture_targets,
                        )
                    visual.start()

                async def receive_commands():
                    async for raw in websocket:
                        import json

                        value = json.loads(raw)
                        if (
                            value.get("protocol_version") != 2
                            or value.get("type") != "execute"
                        ):
                            raise ValueError("INVALID_EXECUTION_MESSAGE")
                        await worker.send(value=value)

                tasks = [
                    asyncio.create_task(receive_commands()),
                    asyncio.create_task(execution.stopped.wait()),
                    asyncio.create_task(worker.process.wait()),
                ]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                if (
                    worker.process.returncode is not None
                    and not execution.stopped.is_set()
                ):
                    error = "WORKER_EXITED"
        except OSError, ValueError, TimeoutError, ConnectionClosed, InvalidStatus:
            error = (
                None
                if execution.stopped.is_set()
                else (
                    "TOOL_EXECUTION_DISCONNECTED"
                    if prepared
                    else "TOOL_INITIALIZATION_FAILED"
                )
            )
        finally:
            if visual is not None:
                await visual.close()
            cleanup = await worker.close()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if cleanup != "COMPLETE":
                self.quarantined = True
                self.ready = False
            if self.active is execution:
                self.active = None
            try:
                if not prepared:
                    await send(
                        message=SessionPrepared(
                            connection_generation=message.connection_generation,
                            session_id=message.session_id,
                            error_code=error or "TOOL_INITIALIZATION_FAILED",
                        )
                    )
                await send(
                    message=SessionClosed(
                        connection_generation=message.connection_generation,
                        session_id=message.session_id,
                        cleanup=cleanup,
                        error_code=error,
                    )
                )
                await publish()
            except OSError, ValueError, ConnectionClosed:
                pass

    async def shutdown(self):
        if self.active:
            execution = self.active
            execution.stopped.set()
            await execution.task


def value_to_json(*, value: dict) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
