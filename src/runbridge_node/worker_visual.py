"""把 Python worker 同一 Page 的最新截图上传到独立画面通道。"""

import base64
from time import monotonic

from runbridge_node.visual import VisualPublisher
from runbridge_node.visual_protocol import (
    VisualFrame,
    VisualHello,
    VisualSelect,
    VisualSourceState,
    VisualTarget,
)
from runbridge_node.visual_wire import pack_frame


class WorkerVisualPublisher(VisualPublisher):
    def __init__(self, *, identity, message, worker):
        super().__init__(
            identity=identity, endpoint="", message=message, support_cache={}
        )
        self.worker = worker
        self.requested_target = None

    def hello(self):
        return VisualHello(
            capture_backend="python-playwright",
            browscreen_version=None,
            runtime_version=self.worker.metadata["runtime_version"],
        )

    def objects(self, *, value):
        previous = self.requested_target
        self.requested_target = value.get("default_page_id")
        self.targets = [
            VisualTarget(target_id=page["id"], label=f"页面 {index + 1}")
            for index, page in enumerate(value.get("pages", []))
        ]
        ids = {target.target_id for target in self.targets}
        if self.request and self.request.target_id != self.requested_target:
            self.request = None
        if previous != self.requested_target or self.state.target_id not in ids:
            self.latest = None
            self.state = VisualSourceState(
                state="WAITING" if self.requested_target else "WAITING_TARGET",
                reason_code="SCREENSHOT_NOT_READY"
                if self.requested_target
                else "TARGET_CLOSED",
            )
        self.changed.set()

    def frame(self, *, value):
        if value["target_id"] != self.requested_target:
            return
        png = base64.b64decode(value["png"], validate=True)
        if len(png) > 2 * 1024 * 1024:
            return
        metadata = VisualFrame(
            connection_generation=self.message.connection_generation,
            session_id=self.message.session_id,
            resource_id=self.message.resource_id,
            stream_id=value["stream_id"],
            target_id=value["target_id"],
            frame_id=value["frame_id"],
            capture_started_at=value["capture_started_at"],
        )
        self.state = VisualSourceState(
            state="WAITING",
            stream_id=metadata.stream_id,
            target_id=metadata.target_id,
            reason_code="SCREENSHOT_NOT_READY",
            request_id=self.request.request_id if self.request else None,
        )
        self.latest = (pack_frame(metadata=metadata, png=png), monotonic(), metadata)
        self.changed.set()

    async def receive(self, *, websocket):
        while True:
            self.request = VisualSelect.model_validate_json(await websocket.recv())
            self.requested_target = self.request.target_id
            self.latest = None
            self.state = VisualSourceState(
                state="WAITING",
                reason_code="SCREENSHOT_NOT_READY",
            )
            self.changed.set()
            await self.worker.send(
                value={"type": "visual_select", "target_id": self.request.target_id}
            )

    async def run(self):
        await self.upload()
