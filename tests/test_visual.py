"""真实 Chrome 画面流、查询兼容和可选采集进程清理。"""

import asyncio
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.async_api import async_playwright
from websockets.asyncio.client import connect

from runbridge_node.capabilities import package_version
from runbridge_node.config import NodeConfig
from runbridge_node.executor import websocket_url
from runbridge_node.protocol import SessionOpen
from runbridge_node.visual import VisualPublisher
from runbridge_node.visual_capture import CaptureProcess, probe_visual
from runbridge_node.visual_protocol import NodeQueryView, SessionQueryView, VisualTarget, supported_browscreen_version
from runbridge_node.visual_wire import unpack_frame
from test_chrome import chrome_node
from test_live_connection import evidence, runtime


@pytest.fixture
def visual_installation():
    """真实画面场景只在明确安装 extra 的环境中运行。"""
    if not supported_browscreen_version(value=package_version(name="browscreen")):
        pytest.skip("画面真机验收需要 uv sync --extra visual")


@pytest.mark.asyncio
async def test_missing_and_incompatible_extension_do_not_probe(monkeypatch):
    for value in (None, "0.2.1", "0.3.0", "0.3.2rc1", "0.4.0.dev1", "0.4.0", "9.0.0", "invalid"):
        monkeypatch.setattr("runbridge_node.visual_capture.package_version", lambda *, name: value)
        assert not await probe_visual()


def test_query_models_accept_old_hub_and_new_visual_fields():
    now = "2026-10-12T00:00:00Z"
    session = {"session_id": "session_a", "node_id": "node_a", "resource_id": "chrome", "grant_id": "grant_a",
               "connection_generation": 1, "runtime_version": "146.0.0.0", "backend": "chrome-cdp", "state": "READY",
               "created_at": now, "updated_at": now, "expires_at": now}
    node = {"node_id": "node_a", "name": "测试", "connection_status": "ONLINE", "connection_generation": 1,
            "heartbeat_count": 0, "last_seen_at": None, "capabilities_observed_at": None, "observation_age_ms": None,
            "capabilities_stale": False, "capabilities": None}
    assert SessionQueryView.model_validate(session).visual is None
    assert NodeQueryView.model_validate(node).visual is None
    session["visual"] = {"supported": True, "state": "WAITING", "stream_path": "/v1/sessions/session_a/visual/stream"}
    node["visual"] = {"supported": True, "streams": []}
    assert SessionQueryView.model_validate(session).visual.stream_path.endswith("/visual/stream")
    assert NodeQueryView.model_validate(node).visual.supported


async def consume_color(*, websocket, color, target_id, minimum_frame=0, previous_target_id=None):
    """独立解码 PNG 比对实际像素，不以状态或 HTTP 200 代替画面正确。"""
    from PIL import Image

    async with asyncio.timeout(delay=10):
        while True:
            value = await websocket.recv()
            if isinstance(value, str):
                assert json.loads(value)["type"] == "state"
                continue
            metadata, png = unpack_frame(data=value)
            if metadata.target_id == previous_target_id:
                continue
            assert metadata.target_id == target_id
            with Image.open(fp=io.BytesIO(png)) as image:
                pixel = image.convert(mode="RGB").getpixel((image.width - 5, image.height - 5))
                if pixel == color and metadata.frame_id > minimum_frame:
                    return metadata, image.size


def test_real_data_stream_corresponds_to_page_and_keeps_execution(visual_installation, chrome_node):
    fixture = chrome_node

    async def exercise():
        runtime, access = fixture['runtime'], fixture['access']
        headers = {"Authorization": f"Bearer {access['access_token']}"}
        async with httpx.AsyncClient(timeout=35, trust_env=False) as client, async_playwright() as playwright:
            response = await client.post(url=f"{runtime.url}/v1/nodes/{access['node_id']}/sessions", headers=headers,
                                         json={"resource_id": "chrome", "client_version": "1.63.0"})
            assert response.status_code == 201
            session = response.json()
            sid = session["session_id"]
            ready = (await client.get(url=f"{runtime.url}/v1/sessions/{sid}", headers=headers)).json()
            assert ready["visual"]["state"] == "WAITING" and ready["visual"]["stream_path"] is None
            browser = await playwright.chromium.connect_over_cdp(
                endpoint_url=websocket_url(hub_url=runtime.url, path=session["native_path"]), headers=headers, no_defaults=True)
            try:
                page = next(item for item in browser.contexts[0].pages if item.url == fixture['url'])
                await page.locator(selector="input").fill(value="真实画面流业务操作")
                await page.locator(selector="button").click()
                assert await page.locator(selector="#result").inner_text() == "真实画面流业务操作"
                await page.evaluate(expression='document.documentElement.style.background="rgb(23,117,211)";document.body.style.background="rgb(23,117,211)"')
                active = (await client.get(url=f"{runtime.url}/v1/sessions/{sid}", headers=headers)).json()
                node = (await client.get(url=f"{runtime.url}/v1/nodes/{access['node_id']}/capabilities", headers=headers)).json()
                assert node["visual"]["streams"][0]["stream_path"] == active["visual"]["stream_path"]
                async with connect(uri=websocket_url(hub_url=runtime.url, path=active["visual"]["stream_path"]), additional_headers=headers) as stream:
                    started = time.monotonic()
                    first, size = await consume_color(websocket=stream, color=(23, 117, 211), target_id=fixture['original'])
                    first_received = time.monotonic()
                    await page.evaluate(expression='document.documentElement.style.background="rgb(211,73,19)";document.body.style.background="rgb(211,73,19)"')
                    second, _ = await consume_color(websocket=stream, color=(211, 73, 19), target_id=fixture['original'], minimum_frame=first.frame_id)
                    third, _ = await consume_color(websocket=stream, color=(211, 73, 19), target_id=fixture['original'], minimum_frame=second.frame_id)
                    assert second.stream_id == first.stream_id and size[0] > 100 and size[1] > 100
                    query = (await client.get(url=f"{runtime.url}/v1/sessions/{sid}", headers=headers)).json()
                    assert query["visual"]["state"] == "LIVE" and query["visual"]["last_frame_id"] >= second.frame_id
                    assert await page.locator(selector="#account").inner_text() == "existing-user"
                    evidence(test_name="browscreen_real_data_stream", details={"viewport": list(size),
                        "decoded_frame_ids": [first.frame_id, second.frame_id, third.frame_id],
                        "pixel_colors": [[23, 117, 211], [211, 73, 19]],
                        "first_matching_frame_seconds": round(first_received - started, 3),
                        "three_matching_frames_seconds": round(time.monotonic() - started, 3),
                        "original_target_confirmed": True, "login_and_business_operation": True})
            finally:
                await browser.close()
            async with asyncio.timeout(delay=10):
                while True:
                    closed = (await client.get(url=f"{runtime.url}/v1/sessions/{sid}", headers=headers)).json()
                    if closed["state"] in {"CLOSED", "INTERRUPTED"}:
                        break
                    await asyncio.sleep(delay=0.05)
            assert closed["cleanup"] == "COMPLETE" and closed["visual"]["stream_path"] is None
            assert fixture['chrome'].process.poll() is None

    asyncio.run(exercise())


def test_multiple_pages_require_selection_and_closed_target_stays_unselected(visual_installation, chrome_node):
    """用两种真实页面颜色验证不会默认误选或在关闭后切换到另一页。"""
    fixture = chrome_node

    async def exercise():
        access, runtime_context = fixture["access"], fixture["runtime"]
        headers = {"Authorization": f"Bearer {access['access_token']}"}
        async with httpx.AsyncClient(timeout=35, trust_env=False) as client, async_playwright() as playwright:
            owner = await playwright.chromium.connect_over_cdp(endpoint_url=fixture["chrome"].endpoint, no_defaults=True)
            second_page = await owner.contexts[0].new_page()
            await second_page.set_content(html="<p>独立的第二页面</p>")
            await second_page.evaluate(expression='document.documentElement.style.background="rgb(101,43,177)";document.body.style.background="rgb(101,43,177)"')
            debugger = await owner.contexts[0].new_cdp_session(page=second_page)
            second_id = (await debugger.send(method="Target.getTargetInfo"))["targetInfo"]["targetId"]
            await debugger.detach()
            response = await client.post(url=f"{runtime_context.url}/v1/nodes/{access['node_id']}/sessions", headers=headers,
                                         json={"resource_id": "chrome", "client_version": "1.63.0"})
            session = response.json()
            browser = await playwright.chromium.connect_over_cdp(
                endpoint_url=websocket_url(hub_url=runtime_context.url, path=session["native_path"]), headers=headers, no_defaults=True)
            query_url = f"{runtime_context.url}/v1/sessions/{session['session_id']}"

            async def wait(predicate):
                async with asyncio.timeout(delay=12):
                    while True:
                        value = (await client.get(url=query_url, headers=headers)).json()["visual"]
                        if predicate(value):
                            return value
                        await asyncio.sleep(delay=0.05)

            try:
                value = await wait(lambda item: item["state"] == "WAITING_TARGET" and len(item["targets"]) == 2)
                assert value["target_id"] is None and value["last_frame_id"] is None
                rejected = await client.put(url=f"{query_url}/visual/target", headers=headers, json={"target_id": "not_in_instance"})
                assert rejected.status_code == 404
                result = await client.put(url=f"{query_url}/visual/target", headers=headers, json={"target_id": second_id})
                assert result.status_code == 202
                async with connect(uri=websocket_url(hub_url=runtime_context.url, path=value["stream_path"]), additional_headers=headers) as stream:
                    first, _ = await consume_color(websocket=stream, color=(101, 43, 177), target_id=second_id)
                    selected = await wait(lambda item: item["state"] == "LIVE")
                    assert selected["selection"]["request_id"] == result.json()["request_id"]
                    await second_page.close()
                    closed = await wait(lambda item: item["state"] == "WAITING_TARGET" and item["target_id"] is None)
                    assert len(closed["targets"]) == 1
                    original = next(item for item in browser.contexts[0].pages if item.url == fixture["url"])
                    await original.evaluate(expression='document.documentElement.style.background="rgb(37,179,61)";document.body.style.background="rgb(37,179,61)"')
                    switch = await client.put(url=f"{query_url}/visual/target", headers=headers, json={"target_id": fixture["original"]})
                    assert switch.status_code == 202
                    next_frame, _ = await consume_color(websocket=stream, color=(37, 179, 61), target_id=fixture["original"], previous_target_id=second_id)
                    assert next_frame.stream_id != first.stream_id
                    applied = await wait(lambda item: item["state"] == "LIVE" and item["target_id"] == fixture["original"])
                    assert applied["selection"]["state"] == "APPLIED"
                    evidence(test_name="browscreen_multi_target", details={"initial_page_count": 2,
                        "automatic_selection": False, "closed_target_not_replaced": True,
                        "two_target_pixel_checks": True, "new_stream_on_switch": True})
            finally:
                if not second_page.is_closed():
                    await second_page.close()
                await browser.close()
                await owner.close()

    asyncio.run(exercise())


def test_capture_worker_exits_on_parent_eof(visual_installation, chrome_node):
    """强杀测试父进程后，观察者仍自行退出，借用浏览器继续存活。"""
    fixture = chrome_node
    endpoint = fixture['chrome'].endpoint.split("/devtools/browser/")[0] + f"/devtools/page/{fixture['original']}"
    program = '''import asyncio,json,sys
from runbridge_node.visual_capture import CaptureProcess
async def main():
    capture = CaptureProcess()
    await capture.start(endpoint=json.loads(sys.stdin.readline())["endpoint"])
    print(json.dumps({"url": capture.url, "directory": str(capture.directory), "pid": capture.process.pid}), flush=True)
    await asyncio.Event().wait()
asyncio.run(main())
'''
    parent = subprocess.Popen([sys.executable, "-c", program], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    information = None
    try:
        parent.stdin.write(json.dumps({"endpoint": endpoint}) + "\n")
        parent.stdin.flush()
        information = json.loads(parent.stdout.readline())
        assert httpx.get(url=f"{information['url']}/api/screenshot", timeout=2).status_code in {200, 503}
        parent.kill()
        parent.wait(timeout=3)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if not Path(information["directory"]).exists():
                break
            time.sleep(0.05)
        assert not Path(information["directory"]).exists()
        with pytest.raises(httpx.HTTPError):
            httpx.get(url=information["url"], timeout=1)
        assert fixture['chrome'].process.poll() is None
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)
        if parent.stdin is not None:
            parent.stdin.close()
        if parent.stdout is not None:
            parent.stdout.close()


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
    publisher = VisualPublisher(identity=NodeConfig(hub_url="http://127.0.0.1:1", node_id="node_a", name="测试", node_token="test-node-token-" * 3),
        endpoint="ws://127.0.0.1:1/devtools/browser/browser_a",
        message=SessionOpen(connection_generation=1, session_id="session_a", resource_id="chrome"), support_cache={})
    publisher.capture = CaptureProcess()
    publisher.capture.url = "http://127.0.0.1:1"
    publisher.targets = [VisualTarget(target_id="target_a", label="页面 1")]
    publisher.set_state(state="WAITING", reason="SCREENSHOT_NOT_READY", stream_id="stream_a", target_id="target_a")
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

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler=handler)) as client:
        tasks = [asyncio.create_task(coro=publisher.poll(client=client)), asyncio.create_task(coro=publisher.send(websocket=UploadReceiver()))]
        try:
            for frame_id in (1, 2):
                responses.put_nowait(httpx.Response(status_code=200, content=b"\x89PNG\r\n\x1a\nunit-test-frame",
                    headers={"X-Frame-Id": str(frame_id), "X-Capture-Started-At": "2026-10-12T00:00:00Z"}))
                await receive(frame_id=frame_id)
                responses.put_nowait(httpx.Response(status_code=503, json={"code": "capture_failed"}))
                await receive()
                assert publisher.latest is None
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
