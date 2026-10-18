"""同页采集的切换、迟到帧和选择确认不能混用。"""

import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from runbridge_node.config import NodeConfig
from runbridge_node.protocol import SessionOpen
from runbridge_node.visual_protocol import VisualSelect
from runbridge_node.worker_visual import WorkerVisualPublisher


def publisher():
    return WorkerVisualPublisher(
        identity=NodeConfig(
            hub_url="http://127.0.0.1:1",
            node_id="node_a",
            name="测试",
            node_token="x" * 64,
        ),
        message=SessionOpen(
            connection_generation=1, session_id="session_a", resource_id="chromium"
        ),
        worker=SimpleNamespace(
            metadata={"runtime_version": "1.63.0"}, send=AsyncMock()
        ),
    )


def state(selected):
    return {"default_page_id": selected, "pages": [{"id": "page_a"}, {"id": "page_b"}]}


def frame(target):
    return {
        "target_id": target,
        "stream_id": "stream_" + target,
        "frame_id": 1,
        "capture_started_at": "2030-01-01T00:00:00Z",
        "png": base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode(),
    }


def test_selection_change_withdraws_old_image_and_drops_late_frames():
    source = publisher()
    source.objects(value=state("page_a"))
    source.frame(value=frame("page_a"))
    assert source.latest is not None
    source.objects(value=state("page_b"))
    assert source.latest is None
    source.frame(value=frame("page_a"))
    assert source.latest is None
    source.frame(value=frame("page_b"))
    assert source.latest is not None
    source.objects(value=state(None))
    source.frame(value=frame("page_b"))
    assert source.latest is None


async def test_visual_selection_waits_for_stream_before_confirming_target():
    source = publisher()
    source.objects(value=state("page_a"))
    source.worker.send.side_effect = asyncio.CancelledError
    receiver = SimpleNamespace(
        recv=AsyncMock(
            return_value=VisualSelect(
                request_id="select_a", target_id="page_b"
            ).model_dump_json()
        )
    )
    with pytest.raises(asyncio.CancelledError):
        await source.receive(websocket=receiver)
    assert source.state.stream_id is None and source.state.target_id is None
    source.objects(value=state("page_b"))
    source.frame(value=frame("page_b"))
    assert (
        source.state.request_id == "select_a"
        and source.state.stream_id
        and source.state.target_id == "page_b"
    )
    source.objects(value=state("page_a"))
    source.frame(value=frame("page_a"))
    assert source.state.request_id is None
