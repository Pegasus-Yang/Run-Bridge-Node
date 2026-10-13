"""真实 Chromium、官方 Python SDK、资源隔离及故障清理验收。"""

import asyncio
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import time
import zipfile
from pathlib import Path

import httpx
import pytest
from playwright.async_api import Error, TimeoutError as PlaywrightTimeoutError, async_playwright
from pydantic import ValidationError
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from runbridge_node.executor import websocket_url, PlaywrightExecutor
from runbridge_node.config import NodeConfig, write_private_json
from runbridge_node.runtime import BrowserServer, PlaywrightConfig
from test_live_connection import NODE_PROJECT, evidence, runtime


RUNTIME = Path(os.environ.get("RUNBRIDGE_PLAYWRIGHT_RUNTIME_DIR", NODE_PROJECT / ".runbridge/playwright"))
NODE_BINARY = os.environ.get("RUNBRIDGE_NODE_BINARY", shutil.which("node") or "node")


def headers(*, access: dict) -> dict:
    """构造测试认证头。

    :returns: 不应写入证据的请求头。
    """
    return {"Authorization": f"Bearer {access['access_token']}"}


def wait_session(*, runtime, access: dict, session_id: str, state: str = "CLOSED") -> dict:
    """等待真实节点的清理报告。

    :returns: 实际会话状态。
    """
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        response = httpx.get(url=f"{runtime.url}/v1/sessions/{session_id}", headers=headers(access=access), timeout=1)
        if response.status_code == 200:
            view = response.json()
            if view["state"] == state and (state == "INTERRUPTED" or view["cleanup"] == "COMPLETE"):
                return view
        time.sleep(0.03)
    raise AssertionError("真实会话未达到预期终止和清理状态")


def create(*, runtime, access: dict, lease: float = 300, version: str = "1.63.0"):
    """使用公开 API 创建实际浏览器会话。

    :returns: HTTP 响应。
    """
    return httpx.post(url=f"{runtime.url}/v1/nodes/{access['node_id']}/sessions", headers=headers(access=access), json={"resource_id": "chromium", "client_version": version, "lease_seconds": lease}, timeout=40)


class BrowserFixture(dict):
    """隐藏 pytest 失败信息中的测试凭据。"""

    def __repr__(self):
        return "<BrowserFixture credentials hidden>"


@pytest.fixture
def browser_node(runtime):
    if not (RUNTIME / "node_modules/playwright/package.json").exists():
        pytest.skip("真实 Playwright 验收需要先运行 prepare-playwright")
    config = runtime.register()
    owner = json.loads(config.read_text())
    access = runtime.grant(config=config)
    playwright_config = runtime.directory / "playwright.json"
    playwright_config.write_text(json.dumps({"runtime_directory": str(RUNTIME), "node_executable": NODE_BINARY, "resource_id": "chromium", "launch_options": {"headless": True, "args": ["--lang=en-US"]}}))
    process = runtime._spawn(project=NODE_PROJECT, name="runbridge-node", arguments=["run", "--config", str(config), "--playwright-config", str(playwright_config)], log_name="playwright-node.log")
    runtime.nodes.append(process)
    view = runtime.wait_view(access=access)
    resource = view["capabilities"]["resources"][0]
    assert resource["readiness"] == "READY" and resource["occupancy"] == "FREE"
    yield BrowserFixture({"runtime": runtime, "config": config, "owner": owner, "access": access, "process": process, "view": view})
    logs = "\n".join(path.read_text() for path in runtime.logs)
    if "Traceback" in logs or "ERROR:" in logs:
        raise AssertionError("真实执行进程日志存在未处理错误")


async def attach(*, playwright, runtime, access: dict, session: dict):
    """使用官方 connect API 和受保护端点。

    :returns: 官方 Browser 对象。
    """
    return await playwright.chromium.connect(endpoint=websocket_url(hub_url=runtime.url, path=session["native_path"]), headers=headers(access=access), timeout=10000)


def test_unknown_launch_options_are_not_silently_ignored(tmp_path):
    with pytest.raises(ValidationError):
        PlaywrightConfig(runtime_directory=tmp_path, launch_options={"headless_typo": True})
    with pytest.raises(ValidationError):
        PlaywrightConfig(runtime_directory=tmp_path, launch_options={"host": "0.0.0.0"})


def test_browser_server_exits_and_owned_browser_is_gone():
    if not (RUNTIME / "node_modules/playwright/package.json").exists():
        pytest.skip("需要先运行 prepare-playwright")

    async def scenario():
        server = BrowserServer(config=PlaywrightConfig(runtime_directory=RUNTIME, node_executable=NODE_BINARY))
        metadata = await server.start()
        try:
            assert metadata["version"] == "1.63.0"
            assert metadata["endpoint"].startswith("ws://127.0.0.1:")
        finally:
            assert await server.close() == "COMPLETE"
        assert server.process.returncode == 0
        assert not server.temporary_directory.exists()
        if os.name == "posix":
            with pytest.raises(ProcessLookupError):
                os.kill(metadata["browser_pid"], 0)
        return {"runtime_version": metadata["version"], "node_version": metadata["node_version"], "browser_process_exited": True}

    evidence(test_name="owned_browser_cleanup", details=asyncio.run(scenario()))


def test_official_sdk_objects_events_files_and_errors(browser_node):
    context = browser_node
    runtime = context["runtime"]
    access = context["access"]
    wrong_version = create(runtime=runtime, access=access, version="1.62.0")
    assert wrong_version.status_code == 428
    result = runtime.command(arguments=["session", "create", "--access-file", str(runtime.directory / "access.json"), "--client-version", "1.63.0"])
    session = json.loads(result.stdout)
    assert session["state"] == "READY"
    busy = create(runtime=runtime, access=access)
    assert busy.status_code == 409 and busy.json()["code"] == "RESOURCE_BUSY"
    assert runtime.query(access=access).json()["capabilities"]["resources"][0]["occupancy"] == "BUSY"
    upload = runtime.directory / "upload.bin"
    payload = bytes(range(256)) * 1024
    upload.write_bytes(payload)
    static = runtime.directory / "http-fixture"
    static.mkdir()
    (static / "index.html").write_text("<title>Node-side HTTP</title><p>browser network fixture</p>")
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        fixture_port = reserve.getsockname()[1]
    http_process = runtime._spawn(project=NODE_PROJECT, name="python", arguments=["-m", "http.server", str(fixture_port), "--bind", "127.0.0.1", "--directory", str(static)], log_name="http-fixture.log")
    runtime.nodes.append(http_process)
    fixture_url = f"http://127.0.0.1:{fixture_port}"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            if httpx.get(url=fixture_url, timeout=0.2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.02)
    screenshot_path = runtime.directory / "screenshot.png"
    download_path = runtime.directory / "download.bin"
    trace_path = runtime.directory / "trace.zip"

    async def scenario():
        async with async_playwright() as playwright:
            browser = await attach(playwright=playwright, runtime=runtime, access=access, session=session)
            browser_context = await browser.new_context(viewport={"width": 800, "height": 600}, locale="zh-CN", accept_downloads=True)
            await browser_context.tracing.start(screenshots=True, snapshots=True, sources=True)
            page = await browser_context.new_page()
            await page.goto(url=fixture_url)
            assert await page.title() == "Node-side HTTP"
            await page.set_content(html='''<html><body><input aria-label="姓名"><button id="dialog" onclick="alert('native-dialog')">弹窗</button><button id="popup" onclick="window.open('about:blank')">新页面</button><input id="file" type="file"><canvas width="800" height="600"></canvas><a id="download" download="download.bin">下载</a></body></html>''')
            await page.get_by_role(role="textbox", name="姓名", exact=True).fill(value="RunBridge")
            assert await page.get_by_role(role="textbox", name="姓名").input_value() == "RunBridge"
            assert await page.evaluate(expression="navigator.language") == "zh-CN"
            dialogs = []

            async def on_dialog(dialog):
                dialogs.append(dialog.message)
                await dialog.accept()

            page.on(event="dialog", f=on_dialog)
            await page.locator(selector="#dialog").click()
            assert dialogs == ["native-dialog"]
            async with page.expect_popup() as popup_event:
                await page.locator(selector="#popup").click()
            popup = await popup_event.value
            await popup.set_content(html="<title>native-popup</title>")
            assert await popup.title() == "native-popup"
            await popup.close()

            async def route_callback(route):
                await route.fulfill(status=200, content_type="application/json", body='{"native":"callback"}')

            await page.route(url="**/native-stub", handler=route_callback)
            await page.goto(url="http://runbridge.test/native-stub")
            assert "callback" in await page.text_content(selector="body")
            await page.set_content(html='<input id="file" type="file"><canvas width="800" height="600"></canvas><a id="download" download="download.bin">下载</a>')
            await page.locator(selector="#file").set_input_files(files=str(upload))
            uploaded = await page.locator(selector="#file").evaluate(expression="async element => {const file=element.files[0]; const bytes=new Uint8Array(await file.arrayBuffer()); return {name:file.name,size:file.size,sum:bytes.reduce((a,b)=>a+b,0)}}")
            assert uploaded == {"name": upload.name, "size": len(payload), "sum": sum(payload)}
            await page.evaluate(expression="""() => { const canvas=document.querySelector('canvas'); const context=canvas.getContext('2d'); const pixels=context.createImageData(800,600); for(let i=0;i<pixels.data.length;i++) pixels.data[i]=i%4===3 ? 255 : Math.random()*256; context.putImageData(pixels,0,0); const bytes=Uint8Array.from({length:262144},(_,i)=>i%256); document.querySelector('#download').href=URL.createObjectURL(new Blob([bytes])); }""")
            png = await page.screenshot(path=str(screenshot_path), full_page=True)
            assert png.startswith(b"\x89PNG") and len(png) > 65536
            async with page.expect_download() as download_event:
                await page.locator(selector="#download").click()
            download = await download_event.value
            await download.save_as(path=str(download_path))
            assert download_path.read_bytes() == payload
            with pytest.raises(Error, match="browser_type.connect"):
                await download.path()
            with pytest.raises(PlaywrightTimeoutError, match="Timeout 60ms") as native_error:
                await page.locator(selector="#missing").click(timeout=60)
            assert "#missing" in str(native_error.value)
            await browser_context.tracing.stop(path=str(trace_path))
            await browser_context.close()
            await browser.close()
            return {"browser_version": browser.version, "screenshot_bytes": len(png), "screenshot_sha256": hashlib.sha256(png).hexdigest(), "upload_bytes": len(payload), "download_bytes": download_path.stat().st_size, "download_sha256": hashlib.sha256(download_path.read_bytes()).hexdigest(), "events": ["dialog", "popup", "download"], "native_route_callback": True, "native_timeout_error": True, "node_local_http_navigation": True}

    details = asyncio.run(scenario())
    closed = wait_session(runtime=runtime, access=access, session_id=session["session_id"])
    with zipfile.ZipFile(file=trace_path) as archive:
        assert "trace.trace" in archive.namelist()
    inspected = runtime.command(arguments=["session", "get", session["session_id"], "--access-file", str(runtime.directory / "access.json")])
    assert json.loads(inspected.stdout)["cleanup"] == "COMPLETE"
    repeated = runtime.command(arguments=["session", "close", session["session_id"], "--access-file", str(runtime.directory / "access.json")])
    assert json.loads(repeated.stdout)["state"] == "CLOSED"
    assert runtime.wait_view(access=access)["heartbeat_count"] > context["view"]["heartbeat_count"]
    assert runtime.query(access=access).json()["capabilities"]["resources"][0]["occupancy"] == "FREE"
    logs = "\n".join(path.read_text() for path in runtime.logs)
    for secret in [runtime.enrollment, context["owner"]["node_token"], access["access_token"]]:
        if secret in logs or secret in inspected.stdout or secret in result.stdout:
            raise AssertionError("实际 Playwright 链路输出含秘密，内容已隐藏")
    if "Traceback" in logs or "ERROR:" in logs:
        raise AssertionError("实际执行日志存在未处理异常")
    details.update({"cleanup": closed["cleanup"], "native_trace_zip": True, "resource_conflict_rejected": True, "heartbeat_continues_during_execution": True, "secrets_absent_from_logs": True})
    evidence(test_name="official_sdk_native_playwright", details=details)


def test_session_isolation_revocation_and_expiry(browser_node):
    context = browser_node
    runtime = context["runtime"]
    access = context["access"]
    second_access = runtime.grant(config=context["config"], filename="second-access.json")
    session = create(runtime=runtime, access=access).json()
    assert httpx.get(url=f"{runtime.url}/v1/sessions/{session['session_id']}", headers=headers(access=second_access)).status_code == 403

    async def scenario():
        url = websocket_url(hub_url=runtime.url, path=session["native_path"])
        for token, expected in [("invalid", 401), (second_access["access_token"], 403)]:
            with pytest.raises(InvalidStatus) as rejected:
                async with connect(uri=url, additional_headers={"Authorization": f"Bearer {token}"}, user_agent_header="Playwright/1.63.0", proxy=None):
                    pass
            assert rejected.value.response.status_code == expected
        async with async_playwright() as playwright:
            browser = await attach(playwright=playwright, runtime=runtime, access=access, session=session)
            page = await browser.new_page()
            await page.set_content(html="<title>before-revoke</title>")
            runtime.command(arguments=["revoke", access["grant_id"], "--config", str(context["config"])])
            deadline = asyncio.get_running_loop().time() + 5
            while browser.is_connected() and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.03)
            assert not browser.is_connected()
            with pytest.raises(Error):
                await page.title()

    asyncio.run(scenario())
    assert runtime.query(access=access).status_code == 401
    runtime.wait_view(access=second_access)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        with sqlite3.connect(database=runtime.directory / "hub.sqlite3") as database:
            record = json.loads(database.execute("SELECT record FROM sessions WHERE session_id = ?", (session["session_id"],)).fetchone()[0])
        if record["cleanup"] == "COMPLETE":
            break
        time.sleep(0.03)
    assert record["state"] == "CLOSED" and record["close_reason"] == "GRANT_REVOKED" and record["cleanup"] == "COMPLETE"
    expiring = create(runtime=runtime, access=second_access, lease=1.5)
    assert expiring.status_code == 201
    closed = wait_session(runtime=runtime, access=second_access, session_id=expiring.json()["session_id"])
    assert closed["close_reason"] == "SESSION_EXPIRED"
    evidence(test_name="session_isolation_revoke_expiry", details={"wrong_token_rejected": True, "other_grant_rejected": True, "revoked_connection_closed": True, "revoked_resource_cleaned": True, "unattached_session_lease_cleaned": True})


def test_restart_interrupts_sdk_and_node_recovers_without_replay(browser_node):
    context = browser_node
    runtime = context["runtime"]
    access = context["access"]
    session = create(runtime=runtime, access=access).json()

    async def scenario():
        async with async_playwright() as playwright:
            browser = await attach(playwright=playwright, runtime=runtime, access=access, session=session)
            page = await browser.new_page()
            await page.set_content(html="<title>before-restart</title>")
            runtime.stop(process=runtime.hub)
            runtime.start_hub()
            current = runtime.wait_view(access=access, minimum_generation=context["view"]["connection_generation"] + 1)
            assert current["capabilities"]["resources"][0]["occupancy"] == "FREE"
            with pytest.raises(Error):
                await page.title()
            assert not browser.is_connected()
            return current["connection_generation"]

    generation = asyncio.run(scenario())
    closed = wait_session(runtime=runtime, access=access, session_id=session["session_id"], state="INTERRUPTED")
    assert closed["execution_outcome"] == "OUTCOME_UNKNOWN"
    fresh = create(runtime=runtime, access=access)
    assert fresh.status_code == 201
    released = httpx.delete(url=f"{runtime.url}/v1/sessions/{fresh.json()['session_id']}", headers=headers(access=access), timeout=15)
    assert released.status_code == 200 and released.json()["cleanup"] == "COMPLETE"
    unclaimed = create(runtime=runtime, access=access).json()
    runtime.hub.kill()
    runtime.hub.wait(timeout=3)
    runtime.start_hub()
    recovered = runtime.wait_view(access=access, minimum_generation=generation + 1)
    orphaned = wait_session(runtime=runtime, access=access, session_id=unclaimed["session_id"], state="INTERRUPTED")
    assert orphaned["cleanup"] == "UNKNOWN" and orphaned["execution_outcome"] == "NOT_STARTED"
    assert recovered["capabilities"]["resources"][0]["occupancy"] == "FREE"
    evidence(test_name="active_sdk_restart", details={"old_session_state": closed["state"], "execution_outcome": closed["execution_outcome"], "new_connection_generation": generation, "old_objects_invalid": True, "new_session_ready_and_cleaned": True, "abrupt_restart_unclaimed_session_interrupted": True})



def test_independent_example_runs_and_releases(browser_node):
    context = browser_node
    runtime = context["runtime"]
    result = subprocess.run([str(NODE_PROJECT / ".venv/bin/python"), str(NODE_PROJECT / "examples/playwright_smoke.py"), "--access-file", str(runtime.directory / "access.json"), "--screenshot", str(runtime.directory / "example.png")], cwd=NODE_PROJECT, env=runtime.environment, capture_output=True, text=True, timeout=40)
    if result.returncode != 0:
        raise AssertionError("独立示例未通过，SDK 错误原文未自动回显")
    output = json.loads(result.stdout)
    assert output["title"] == "RunBridge"
    closed = wait_session(runtime=runtime, access=context["access"], session_id=output["session_id"])
    assert closed["cleanup"] == "COMPLETE"
    assert (runtime.directory / "example.png").read_bytes().startswith(b"\x89PNG")
    if context["access"]["access_token"] in result.stdout or context["access"]["access_token"] in result.stderr:
        raise AssertionError("独立示例输出含秘密，内容已隐藏")
    private = runtime.directory / ".runbridge/access-playwright.json"
    write_private_json(path=private, values=json.loads((runtime.directory / "access.json").read_text()))
    guide = (NODE_PROJECT / "doc/user-guide/Playwright快速开始.md").read_text()
    example = "doc/reference/examples/执行会话调用.py"
    assert example in guide
    documented = subprocess.run([str(NODE_PROJECT / ".venv/bin/python"), str(NODE_PROJECT / example), "--access-file", str(private), "--resource-id", "chromium", "--screenshot", str(runtime.directory / "documented.png")], cwd=runtime.directory, env=runtime.environment, capture_output=True, text=True, timeout=40)
    if documented.returncode != 0:
        diagnostic = documented.stderr
        for secret in [runtime.enrollment, context["owner"]["node_token"], context["access"]["access_token"]]:
            diagnostic = diagnostic.replace(secret, "[REDACTED]")
        (runtime.directory / "documented-example-error.log").write_text(diagnostic)
        raise AssertionError("文档中的独立示例未通过，错误原文未自动回显")
    records = [json.loads(line) for line in documented.stdout.splitlines()]
    assert records[1]["title"] == "RunBridge" and records[-1]["cleanup"] == "COMPLETE"
    assert (runtime.directory / "documented.png").read_bytes().startswith(b"\x89PNG")
    evidence(test_name="independent_example", details={"official_sdk_connected": True, "page_title": output["title"], "screenshot_created_on_caller": True, "resource_cleaned": True, "documentation_example_executed": True})



def test_unknown_cleanup_marker_survives_node_restart(tmp_path):
    identity = NodeConfig(hub_url="http://127.0.0.1:8787", node_id="node_quarantine", name="quarantine", node_token="test-node-token-" + "x" * 40)
    config = PlaywrightConfig(runtime_directory=tmp_path)
    first = PlaywrightExecutor(identity=identity, config=config)
    write_private_json(path=first.quarantine_file, values={"node_id": identity.node_id, "cleanup": "UNKNOWN"})
    restarted = PlaywrightExecutor(identity=identity, config=config)
    asyncio.run(restarted.probe())
    assert restarted.quarantined is True and restarted.ready is False



@pytest.mark.skipif(os.name != "posix", reason="当前强制进程组清理验收只覆盖 POSIX")
def test_helper_crash_also_cleans_detached_owned_browser():
    if not (RUNTIME / "node_modules/playwright/package.json").exists():
        pytest.skip("需要先运行 prepare-playwright")

    async def scenario():
        server = BrowserServer(config=PlaywrightConfig(runtime_directory=RUNTIME, node_executable=NODE_BINARY))
        metadata = await server.start()
        try:
            assert server.browser_group == metadata["browser_pid"]
            server.process.kill()
            await server.process.wait()
        finally:
            assert await server.close() == "COMPLETE"
        with pytest.raises(ProcessLookupError):
            os.kill(metadata["browser_pid"], 0)
        assert not server.temporary_directory.exists()
        return {"helper_crashed": True, "detached_owned_browser_reclaimed": True}

    evidence(test_name="helper_crash_cleanup", details=asyncio.run(scenario()))
