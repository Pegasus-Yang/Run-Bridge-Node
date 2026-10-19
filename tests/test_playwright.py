"""显式启用的实际 Python worker、故障清理和借用连接验收。"""

import asyncio
import os
import subprocess
import threading
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psutil
import pytest

from runbridge_node.runtime import PlaywrightConfig, ToolWorker, same_process
from runbridge_node.tool_contract import Execute, Target


pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("RUNBRIDGE_RUN_BROWSER_TESTS") != "1",
        reason="需显式启用真实浏览器测试",
    ),
]


async def wait_gone(*, pid, created):
    for _ in range(100):
        if same_process(pid=pid, created=created) is None:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("本次专用 Chromium 未退出")


@pytest.mark.parametrize("cause", ["normal", "worker-kill", "driver-kill"])
async def test_actual_worker_cleanup_confirms_browser_and_private_profile(
    tmp_path, cause
):
    messages = asyncio.Queue()

    async def collect(value):
        await messages.put(value)

    worker = ToolWorker(
        config=PlaywrightConfig(), record_path=tmp_path / "session.json"
    )
    try:
        metadata = await worker.start(
            session_id="session_a", generation=1, callback=collect
        )
        pid, created = metadata["browser_pid"], metadata["browser_created"]
        profile = Path(metadata["profile"])
        assert profile.is_relative_to(worker.temporary_directory)
        assert len(str(worker.temporary_directory).encode()) < 50
        assert worker.temporary_directory.stat().st_mode & 0o777 == 0o700
        assert worker.record_path.stat().st_mode & 0o777 == 0o600
        if cause == "worker-kill":
            worker.process.kill()
            await worker.process.wait()
        elif cause == "driver-kill":
            children = psutil.Process(worker.process.pid).children(recursive=True)
            driver = next(
                item
                for item in children
                if any("/playwright/driver/node" in arg for arg in item.cmdline())
            )
            driver.kill()
        else:
            request = Execute(
                request_id="read",
                session_id="session_a",
                connection_generation=1,
                remaining_ms=1000,
                method="page.url",
                target=Target(type="page", id=metadata["objects"]["default_page_id"]),
            )
            await worker.send(value=request.model_dump(mode="json"))
            async with asyncio.timeout(5):
                while (message := await messages.get())["type"] != "result":
                    pass
            assert (
                message["status"] == "SUCCEEDED"
                and message["result"]["value"] == "about:blank"
            )
        assert await worker.close() == "COMPLETE"
        assert await worker.close() == "COMPLETE"
        await wait_gone(pid=pid, created=created)
        assert not profile.exists() and not worker.temporary_directory.exists()
    finally:
        await worker.close()


async def test_borrowed_chrome_release_keeps_original_page_cookie_and_storage(tmp_path):
    from playwright.async_api import async_playwright

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b'<html><input id="field"><h1>borrowed</h1>'
                b"<button onclick=\"document.querySelector('#result').textContent='clicked'\">save</button>"
                b'<p id="result"></p></html>'
            )

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile_directory = tempfile.TemporaryDirectory(prefix="rb-owner-", dir="/tmp")
    profile = Path(profile_directory.name)
    process = None
    worker = None
    try:
        async with async_playwright() as owner:
            process = subprocess.Popen(
                [
                    owner.chromium.executable_path,
                    "--headless",
                    "--enable-automation",
                    "--use-mock-keychain",
                    "--password-store=basic",
                    "--no-sandbox",
                    "--remote-debugging-port=0",
                    "--remote-debugging-address=127.0.0.1",
                    f"--user-data-dir={profile}",
                    "about:blank",
                ],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            active = profile / "DevToolsActivePort"
            for _ in range(100):
                if active.exists():
                    break
                await asyncio.sleep(0.05)
            port, route = active.read_text().splitlines()[:2]
            endpoint = f"ws://127.0.0.1:{port}{route}"
            browser = await owner.chromium.connect_over_cdp(
                endpoint_url=endpoint, no_defaults=True
            )
            context = browser.contexts[0]
            page = context.pages[0]
            url = f"http://127.0.0.1:{server.server_port}"
            await page.goto(url=url, wait_until="domcontentloaded", timeout=5000)
            await context.add_cookies(
                cookies=[{"name": "login", "value": "kept", "url": url}]
            )
            await page.evaluate(expression="localStorage.setItem('owner','kept')")
            background = await context.new_page()
            await background.bring_to_front()
            messages = asyncio.Queue()

            async def collect(value):
                await messages.put(value)

            worker = ToolWorker(
                config=PlaywrightConfig(
                    mode="borrowed",
                    authorization_scope="BROWSER_INSTANCE",
                    cdp_endpoint=endpoint,
                ),
                record_path=tmp_path / "worker.json",
            )
            metadata = await worker.start(
                session_id="session_b", generation=1, callback=collect
            )
            target = Target(
                type="page",
                id=next(
                    item["id"]
                    for item in metadata["objects"]["pages"]
                    if item["url"] == url + "/"
                ),
                locator=[{"method": "locator", "params": {"selector": "#field"}}],
            )
            await worker.send(
                value=Execute(
                    request_id="fill",
                    session_id="session_b",
                    connection_generation=1,
                    remaining_ms=1000,
                    method="locator.fill",
                    target=target,
                    params={"value": "worker changed"},
                ).model_dump(mode="json")
            )
            async with asyncio.timeout(5):
                while (message := await messages.get())["type"] != "result":
                    pass
            assert message["status"] == "SUCCEEDED"
            await background.bring_to_front()
            await worker.send(
                value=Execute(
                    request_id="click_background_page",
                    session_id="session_b",
                    connection_generation=1,
                    remaining_ms=3000,
                    method="locator.click",
                    target=Target(
                        type="page",
                        id=target.id,
                        locator=[
                            {
                                "method": "get_by_role",
                                "params": {
                                    "role": "button",
                                    "name": "save",
                                    "exact": True,
                                },
                            }
                        ],
                    ),
                ).model_dump(mode="json")
            )
            async with asyncio.timeout(5):
                while True:
                    message = await messages.get()
                    if (
                        message["type"] == "result"
                        and message["request_id"] == "click_background_page"
                    ):
                        break
            assert message["status"] == "SUCCEEDED", message
            assert await page.locator(selector="#result").inner_text() == "clicked"
            assert await worker.close() == "COMPLETE"
            assert (
                process.poll() is None
                and not page.is_closed()
                and not background.is_closed()
            )
            assert (
                await page.locator(selector="#field").input_value() == "worker changed"
            )
            assert (
                await page.evaluate(expression="localStorage.getItem('owner')")
                == "kept"
            )
            assert any(
                cookie["name"] == "login" and cookie["value"] == "kept"
                for cookie in await context.cookies()
            )
            await browser.close()
            assert process.poll() is None
    finally:
        if worker:
            await worker.close()
        if process and process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        profile_directory.cleanup()
