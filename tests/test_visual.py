"""真实 Chrome 画面流、查询兼容和可选采集进程清理。"""

import asyncio
import json

import httpx
import pytest

from runbridge_node.config import NodeConfig
from runbridge_node.protocol import SessionOpen
from runbridge_node.visual import VisualPublisher
from runbridge_node.visual_capture import CaptureProcess, probe_visual
from runbridge_node.visual_protocol import NodeQueryView, SessionQueryView, VisualTarget
from runbridge_node.visual_wire import unpack_frame


@pytest.mark.asyncio
async def test_missing_and_incompatible_extension_do_not_probe(monkeypatch):
    for value in (
        None,
        "0.2.1",
        "0.3.0",
        "0.3.2rc1",
        "0.4.0.dev1",
        "0.4.0",
        "9.0.0",
        "invalid",
    ):
        monkeypatch.setattr(
            "runbridge_node.visual_capture.package_version", lambda *, name: value
        )
        assert not await probe_visual()


def test_query_models_accept_old_hub_and_new_visual_fields():
    now = "2026-10-12T00:00:00Z"
    session = {
        "session_id": "session_a",
        "node_id": "node_a",
        "resource_id": "chrome",
        "grant_id": "grant_a",
        "connection_generation": 1,
        "runtime_version": "146.0.0.0",
        "backend": "chrome-cdp",
        "state": "READY",
        "created_at": now,
        "updated_at": now,
        "expires_at": now,
    }
    node = {
        "node_id": "node_a",
        "name": "测试",
        "connection_status": "ONLINE",
        "connection_generation": 1,
        "heartbeat_count": 0,
        "last_seen_at": None,
        "capabilities_observed_at": None,
        "observation_age_ms": None,
        "capabilities_stale": False,
        "capabilities": None,
    }
    assert SessionQueryView.model_validate(session).visual is None
    assert NodeQueryView.model_validate(node).visual is None
    session["visual"] = {
        "supported": True,
        "state": "WAITING",
        "stream_path": "/v1/sessions/session_a/visual/stream",
    }
    node["visual"] = {"supported": True, "streams": []}
    assert SessionQueryView.model_validate(session).visual.stream_path.endswith(
        "/visual/stream"
    )
    assert NodeQueryView.model_validate(node).visual.supported


@pytest.mark.asyncio
async def test_capture_process_start_failure_cleans_own_directory(monkeypatch):
    capture = CaptureProcess()

    async def fail(*args, **kwargs):
        raise OSError("模拟进程创建失败")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fail)
    with pytest.raises(OSError):
        await capture.start(endpoint="ws://127.0.0.1:1/devtools/page/test")
    directory = capture.directory
    assert await capture.close() == "COMPLETE"
    assert not directory.exists()


@pytest.mark.asyncio
async def test_repeated_capture_error_after_recovery_removes_frame_again():
    """两次相同源错误之间成功出图，第二次仍通知消费者并撤下旧图。"""
    publisher = VisualPublisher(
        identity=NodeConfig(
            hub_url="http://127.0.0.1:1",
            node_id="node_a",
            name="测试",
            node_token="test-node-token-" * 3,
        ),
        endpoint="ws://127.0.0.1:1/devtools/browser/browser_a",
        message=SessionOpen(
            connection_generation=1, session_id="session_a", resource_id="chrome"
        ),
        support_cache={},
    )
    publisher.capture = CaptureProcess()
    publisher.capture.url = "http://127.0.0.1:1"
    publisher.targets = [VisualTarget(target_id="target_a", label="页面 1")]
    publisher.set_state(
        state="WAITING",
        reason="SCREENSHOT_NOT_READY",
        stream_id="stream_a",
        target_id="target_a",
    )
    responses, messages = asyncio.Queue(), asyncio.Queue()

    async def handler(request):
        return await responses.get()

    class UploadReceiver:
        async def send(self, *, message):
            messages.put_nowait(message)

    async def receive(*, frame_id=None):
        async with asyncio.timeout(delay=2):
            while True:
                value = await messages.get()
                if frame_id is not None and isinstance(value, bytes):
                    if unpack_frame(data=value)[0].frame_id == frame_id:
                        return
                elif frame_id is None and isinstance(value, str):
                    message = json.loads(value)
                    if message.get("state") == "ERROR":
                        assert message["reason_code"] == "CAPTURE_FAILED"
                        return

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler=handler)
    ) as client:
        tasks = [
            asyncio.create_task(coro=publisher.poll(client=client)),
            asyncio.create_task(coro=publisher.send(websocket=UploadReceiver())),
        ]
        try:
            for frame_id in (1, 2):
                responses.put_nowait(
                    httpx.Response(
                        status_code=200,
                        content=b"\x89PNG\r\n\x1a\nunit-test-frame",
                        headers={
                            "X-Frame-Id": str(frame_id),
                            "X-Capture-Started-At": "2026-10-12T00:00:00Z",
                        },
                    )
                )
                await receive(frame_id=frame_id)
                responses.put_nowait(
                    httpx.Response(status_code=503, json={"code": "capture_failed"})
                )
                await receive()
                assert publisher.latest is None
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
