"""用独立用户 Chrome 验证原登录、实例授权和只断开清理。"""

import asyncio
import json
import os
import signal
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from playwright.async_api import Error, async_playwright
from pydantic import ValidationError
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from runbridge_node.chrome import ChromeConfig
from runbridge_node.executor import websocket_url
from test_live_connection import NODE_PROJECT, evidence, executable, runtime
from test_playwright import BrowserFixture, headers, wait_session


CHROME_BINARY = Path(os.environ.get("RUNBRIDGE_CHROME_BINARY", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))


class AccountHandler(BaseHTTPRequestHandler):
    """提供 Cookie 控制的真实测试业务页。"""

    def do_GET(self):
        """登录端点设置 Cookie，账号页按 Cookie 决定实际身份。"""
        if self.path == "/login":
            self.send_response(code=200)
            self.send_header(keyword="Set-Cookie", value="runbridge_test_login=logged-in; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400")
            content = '<script>localStorage.setItem("account-marker", "existing-user");location.href="/account"</script>'
        else:
            authenticated = "runbridge_test_login=logged-in" in self.headers.get("Cookie", "")
            self.send_response(code=200)
            content = f'''<meta charset="utf-8"><title>已有 Chrome 登录验收</title><p id="account">{"existing-user" if authenticated else "anonymous"}</p><input aria-label="内容"><button onclick='document.querySelector("#result").textContent=document.querySelector("input").value'>提交</button><p id="result"></p>'''
        self.send_header(keyword="Content-Type", value="text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())

    def log_message(self, format, *args):
        """测试 HTTP 服务不记录 Cookie 或请求内容。"""


class UserChrome:
    """测试所有者独立运行的浏览器，不由 Node 创建或回收。"""

    def __init__(self, *, directory: Path):
        self.directory = directory
        self.process = None
        self.endpoint = None

    def start(self) -> None:
        """用全新测试 Profile 启动真实 Google Chrome。"""
        self.directory.mkdir(mode=0o700)
        with (self.directory / "chrome.log").open(mode="w") as log:
            self.process = subprocess.Popen([str(CHROME_BINARY), "--headless=new", "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1", f"--user-data-dir={self.directory / 'profile'}", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "about:blank"], stdout=log, stderr=log, start_new_session=os.name == "posix")
        # 独立 Chrome 冷启动可能超过 10 秒，仍检查进程退出和真实端点。
        deadline = time.monotonic() + 20
        marker = self.directory / "profile/DevToolsActivePort"
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError("测试所有者 Chrome 启动失败")
            if marker.is_file():
                values = marker.read_text().splitlines()
                if len(values) == 2:
                    self.endpoint = f"ws://127.0.0.1:{values[0]}{values[1]}"
                    return
            time.sleep(0.03)
        raise AssertionError("测试 Chrome 没有提供 CDP 端点")

    def close(self) -> None:
        """仅测试所有者结束自己创建的浏览器，Node 无此入口。"""
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    if os.name == "posix":
                        os.killpg(self.process.pid, signal.SIGKILL)
                    else:
                        self.process.kill()
                    self.process.wait(timeout=3)


async def targets(*, endpoint: str) -> list[dict]:
    """以只读 CDP 检查原目标及是否仍有调试附加。

    :returns: Chrome 目标列表。
    """
    async with connect(uri=endpoint, proxy=None) as browser:
        await browser.send(json.dumps({"id": 1, "method": "Target.getTargets"}))
        return json.loads(await browser.recv())["result"]["targetInfos"]


async def account_state(*, endpoint: str, url: str) -> dict:
    """独立直连原浏览器验证业务身份和存储，而非采信执行状态。

    :returns: 测试业务事实。
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(endpoint_url=endpoint, no_defaults=True)
        try:
            context = browser.contexts[0]
            page = next(item for item in context.pages if item.url == url)
            await page.reload()
            return {"account": await page.locator(selector="#account").inner_text(), "storage": await page.evaluate(expression='localStorage.getItem("account-marker")'), "cookies": await context.cookies(urls=[url])}
        finally:
            await browser.close()


@pytest.fixture
def chrome_node(runtime):
    if not CHROME_BINARY.is_file():
        pytest.skip("真实 Chrome 验收需要 RUNBRIDGE_CHROME_BINARY 指向已安装 Google Chrome")
    server = ThreadingHTTPServer(server_address=("127.0.0.1", 0), RequestHandlerClass=AccountHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/account"
    chrome = UserChrome(directory=runtime.directory / "user-chrome")
    try:
        chrome.start()

        async def login():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(endpoint_url=chrome.endpoint, no_defaults=True)
                try:
                    await browser.contexts[0].pages[0].goto(url=url.replace("/account", "/login"))
                    await browser.contexts[0].pages[0].wait_for_url(url=url)
                finally:
                    await browser.close()

        asyncio.run(login())
        original = next(item["targetId"] for item in asyncio.run(targets(endpoint=chrome.endpoint)) if item["url"] == url)
        before = asyncio.run(account_state(endpoint=chrome.endpoint, url=url))
        assert before["account"] == "existing-user" and before["storage"] == "existing-user"
        config = runtime.register()
        access = BrowserFixture(runtime.grant(config=config))
        chrome_config = runtime.directory / "chrome.json"
        chrome_config.write_text(json.dumps({"resource_id": "chrome", "authorization_scope": "BROWSER_INSTANCE", "cdp_endpoint": chrome.endpoint}))
        chrome_config.chmod(mode=0o600)
        node = runtime._spawn(project=NODE_PROJECT, name="runbridge-node", arguments=["run", "--config", str(config), "--chrome-config", str(chrome_config)], log_name="chrome-node.log")
        runtime.nodes.append(node)
        view = runtime.wait_view(access=access)
        assert view["capabilities"]["resources"][0]["readiness"] == "READY"
        yield BrowserFixture({"runtime": runtime, "access": access, "config": config, "chrome_config": chrome_config, "process": node, "chrome": chrome, "url": url, "original": original, "before": before, "view": view})
        runtime.stop(process=node)
        assert chrome.process.poll() is None
        after = asyncio.run(account_state(endpoint=chrome.endpoint, url=url))
        assert after == before
        remaining = asyncio.run(targets(endpoint=chrome.endpoint))
        assert any(item["targetId"] == original and not item["attached"] for item in remaining)
        logs = "\n".join(path.read_text() for path in runtime.logs)
        if "Traceback" in logs or "ERROR:" in logs or chrome.endpoint in logs:
            raise AssertionError("真实借用进程存在未处理异常或泄露本机端点")
    finally:
        for process in runtime.nodes:
            runtime.stop(process=process)
        chrome.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def session_response(*, context, access: dict | None = None, lease: float = 300, **extra):
    """调用公开管理接口，额外字段用于验证端点不可远程注入。

    :returns: 实际 HTTP 响应。
    """
    runtime = context["runtime"]
    access = access or context["access"]
    return httpx.post(url=f"{runtime.url}/v1/nodes/{access['node_id']}/sessions", headers=headers(access=access), json={"resource_id": "chrome", "client_version": "1.63.0", "lease_seconds": lease, **extra}, timeout=40)


async def attach(*, playwright, context, session: dict):
    """官方 API 接入 Hub，不使用本机 Chrome 端点。

    :returns: 官方 Browser 对象。
    """
    return await playwright.chromium.connect_over_cdp(endpoint_url=websocket_url(hub_url=context["runtime"].url, path=session["native_path"]), headers=headers(access=context["access"]), no_defaults=True, timeout=10000)


@pytest.mark.parametrize("values", [{"cdp_endpoint": "ws://127.0.0.1:9222/devtools/browser/test"}, *[{"authorization_scope": "BROWSER_INSTANCE", "cdp_endpoint": value} for value in ["http://127.0.0.1:9222", "ws://example.com:9222/devtools/browser/test", "ws://127.0.0.1:9222/devtools/page/test", "ws://127.0.0.1:9222/devtools/browser/test?token=secret", "ws://user:secret@127.0.0.1:9222/devtools/browser/test"]]])
def test_chrome_config_requires_explicit_instance_authorization(values):
    with pytest.raises(ValidationError):
        ChromeConfig.model_validate(values)


def test_chrome_reuses_login_and_releases_only_connection(chrome_node):
    context = chrome_node
    runtime = context["runtime"]
    response = session_response(context=context)
    assert response.status_code == 201
    session = response.json()
    assert session["backend"] == "chrome-cdp" and session["native_protocol"] == "cdp"
    assert session["authorization_scope"] == "BROWSER_INSTANCE"
    assert context["chrome"].endpoint not in json.dumps(runtime.query(access=context["access"]).json())
    assert session_response(context=context).json()["code"] == "RESOURCE_BUSY"

    async def scenario():
        async with async_playwright() as playwright:
            browser = await attach(playwright=playwright, context=context, session=session)
            page = next(item for item in browser.contexts[0].pages if item.url == context["url"])
            assert await page.locator(selector="#account").inner_text() == "existing-user"
            await page.get_by_role(role="textbox", name="内容").fill(value="复用原页面")
            await page.get_by_role(role="button", name="提交").click()
            assert await page.locator(selector="#result").inner_text() == "复用原页面"
            assert (await page.screenshot())[:8] == b"\x89PNG\r\n\x1a\n"
            raw = await browser.new_browser_cdp_session()
            for method in ["Browser.close", "Browser.crash", "Target.sendMessageToTarget"]:
                with pytest.raises(Error, match="RUNBRIDGE_BORROWED_BROWSER_COMMAND_FORBIDDEN"):
                    await raw.send(method=method)
            assert await page.title() == "已有 Chrome 登录验收"
            await browser.close()
            assert not browser.is_connected()
            with pytest.raises(Error):
                await page.title()

    asyncio.run(scenario())
    closed = wait_session(runtime=runtime, access=context["access"], session_id=session["session_id"])
    assert closed["cleanup"] == "COMPLETE"
    assert context["chrome"].process.poll() is None
    assert asyncio.run(account_state(endpoint=context["chrome"].endpoint, url=context["url"])) == context["before"]
    again = session_response(context=context).json()

    async def explicit_release():
        async with async_playwright() as playwright:
            browser = await attach(playwright=playwright, context=context, session=again)
            released = await asyncio.to_thread(httpx.delete, url=f"{runtime.url}/v1/sessions/{again['session_id']}", headers=headers(access=context["access"]), timeout=15)
            assert released.status_code == 200 and released.json()["cleanup"] == "COMPLETE"
            for _ in range(30):
                if not browser.is_connected():
                    break
                await asyncio.sleep(0.05)
            assert not browser.is_connected()

    asyncio.run(explicit_release())
    repeat = httpx.delete(url=f"{runtime.url}/v1/sessions/{again['session_id']}", headers=headers(access=context["access"]), timeout=5)
    assert repeat.json()["cleanup"] == "COMPLETE"
    evidence(test_name="chrome_existing_login_and_detach", details={"chrome_version": session["runtime_version"], "original_page_reused": True, "business_login_preserved": True, "cookie_and_local_storage_unchanged": True, "native_page_actions_and_screenshot": True, "browser_exit_commands_rejected": True, "sdk_and_api_release_disconnect_only": True, "old_objects_invalid": True, "browser_survives": True})


def test_chrome_grant_scope_and_endpoint_are_enforced(chrome_node):
    context = chrome_node
    runtime = context["runtime"]
    limited_file = runtime.directory / "limited.json"
    runtime.command(arguments=["grant", "--config", str(context["config"]), "--output", str(limited_file), "--resource-id", "another-chrome"])
    limited = json.loads(limited_file.read_text())
    assert runtime.query(access=limited).json()["capabilities"]["resources"] == []
    denied = session_response(context=context, access=limited)
    assert denied.status_code == 403 and denied.json()["code"] == "RESOURCE_OUTSIDE_GRANT"
    injection = session_response(context=context, cdp_endpoint=context["chrome"].endpoint)
    assert injection.status_code == 422
    assert session_response(context=context, client_version="1.59.0").status_code == 428
    session = session_response(context=context).json()
    other = runtime.grant(config=context["config"], filename="other.json")
    assert httpx.get(url=f"{runtime.url}/v1/sessions/{session['session_id']}", headers=headers(access=other), timeout=2).status_code == 403
    assert httpx.delete(url=f"{runtime.url}/v1/sessions/{session['session_id']}", headers=headers(access=other), timeout=2).status_code == 403

    async def rejected():
        url = websocket_url(hub_url=runtime.url, path=session["native_path"])
        for endpoint, token, version, code in [(url, other["access_token"], "1.63.0", 403), (url, "invalid-token", "1.63.0", 401), (url, context["access"]["access_token"], "1.62.0", 428), (url.replace("/cdp", "/playwright"), context["access"]["access_token"], "1.63.0", 409)]:
            with pytest.raises(InvalidStatus) as failure:
                async with connect(uri=endpoint, additional_headers={"Authorization": f"Bearer {token}"}, user_agent_header=f"Playwright/{version}", proxy=None):
                    pass
            assert failure.value.response.status_code == code

    asyncio.run(rejected())
    released = httpx.delete(url=f"{runtime.url}/v1/sessions/{session['session_id']}", headers=headers(access=context["access"]), timeout=15).json()
    assert released["state"] == "CLOSED" and released["cleanup"] == "COMPLETE"
    evidence(test_name="chrome_authorization_scope", details={"scope": "BROWSER_INSTANCE", "outside_resource_rejected": True, "different_grant_rejected": True, "endpoint_injection_rejected": True, "wrong_protocol_and_sdk_rejected": True, "idle_session_cleanup_complete": True})


def test_other_browser_targets_cannot_be_attached(chrome_node):
    context = chrome_node
    other = UserChrome(directory=context["runtime"].directory / "outside-browser")
    try:
        other.start()
        foreign = next(item["targetId"] for item in asyncio.run(targets(endpoint=other.endpoint)) if item["type"] == "page")
        session = session_response(context=context).json()

        async def scenario():
            async with async_playwright() as playwright:
                browser = await attach(playwright=playwright, context=context, session=session)
                try:
                    raw = await browser.new_browser_cdp_session()
                    with pytest.raises(Error):
                        await raw.send(method="Target.attachToTarget", params={"targetId": foreign, "flatten": True})
                    assert not any(item["targetId"] == foreign for item in (await raw.send(method="Target.getTargets"))["targetInfos"])
                finally:
                    await browser.close()

        asyncio.run(scenario())
        wait_session(runtime=context["runtime"], access=context["access"], session_id=session["session_id"])
        assert other.process.poll() is None
        evidence(test_name="chrome_foreign_instance_targets", details={"different_real_browser_target_rejected": True, "different_browser_not_visible": True, "both_browser_processes_survive": True})
    finally:
        other.close()


def test_documented_chrome_examples_reuse_original_page(chrome_node):
    context = chrome_node
    runtime = context["runtime"]
    screenshot = runtime.directory / "example.png"
    source = NODE_PROJECT / "examples/chrome_reuse.py"
    completed = subprocess.run([executable(project=NODE_PROJECT, name="python"), str(source), "--access-file", str(runtime.directory / "access.json"), "--page-url", context["url"], "--screenshot", str(screenshot)], cwd=NODE_PROJECT, capture_output=True, text=True, timeout=25)
    if completed.returncode != 0:
        raise AssertionError("Chrome 示例执行失败，未回显可能含凭据的 SDK 原文")
    assert json.loads(completed.stdout)["reused_existing_page"] is True
    assert screenshot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    guide = (NODE_PROJECT / "doc/development/调用方联调.md").read_text()
    example = "doc/development/examples/执行会话调用.py"
    assert example in guide
    documented_screenshot = runtime.directory / "documented-chrome.png"
    documented = subprocess.run(args=[executable(project=NODE_PROJECT, name="python"), str(NODE_PROJECT / example), "--access-file", str(runtime.directory / "access.json"), "--resource-id", "chrome", "--page-url", context["url"], "--screenshot", str(documented_screenshot)], cwd=NODE_PROJECT, capture_output=True, text=True, timeout=40)
    if documented.returncode != 0:
        raise AssertionError("Chrome 开发联调示例未通过实际连接验收")
    records = [json.loads(line) for line in documented.stdout.splitlines()]
    assert records[1]["state"] == "ACTIVE"
    assert records[1]["title"] == "已有 Chrome 登录验收"
    assert records[-1]["cleanup"] == "COMPLETE"
    assert documented_screenshot.read_bytes().startswith(b"\x89PNG")
    evidence(test_name="chrome_documented_examples", details={"standalone_example_executed": True, "guide_code_executed": True, "original_page_reused": True, "screenshot_verified": True})


@pytest.mark.parametrize("cause", ["lease", "grant-expiry", "revoke", "node-stop", "node-kill", "hub-restart"])
def test_chrome_disconnect_cleans_attachment_without_closing_browser(chrome_node, cause):
    context = chrome_node
    runtime = context["runtime"]
    if cause == "grant-expiry":
        expiry_file = runtime.directory / "expiry.json"
        runtime.command(arguments=["grant", "--config", str(context["config"]), "--output", str(expiry_file), "--resource-id", "chrome", "--expires-in", "3"])
        context["access"] = BrowserFixture(json.loads(expiry_file.read_text()))
    session = session_response(context=context, lease=2 if cause == "lease" else 300).json()

    async def scenario():
        async with async_playwright() as playwright:
            browser = await attach(playwright=playwright, context=context, session=session)
            page = next(item for item in browser.contexts[0].pages if item.url == context["url"])
            pending = asyncio.create_task(page.locator(selector="#never-exists").wait_for(timeout=0))
            await asyncio.sleep(0.1)
            try:
                if cause == "revoke":
                    await asyncio.to_thread(runtime.command, arguments=["revoke", context["access"]["grant_id"], "--config", str(context["config"])])
                elif cause == "node-stop":
                    await asyncio.to_thread(runtime.stop, process=context["process"])
                elif cause == "node-kill":
                    context["process"].kill()
                    await asyncio.to_thread(context["process"].wait, timeout=5)
                elif cause == "hub-restart":
                    await asyncio.to_thread(runtime.stop, process=runtime.hub)
                    await asyncio.to_thread(runtime.start_hub)
                with pytest.raises(Error):
                    await asyncio.wait_for(pending, timeout=8)
                assert not browser.is_connected()
                with pytest.raises(Error):
                    await page.title()
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
                await browser.close()

    asyncio.run(scenario())
    if cause == "lease":
        record = wait_session(runtime=runtime, access=context["access"], session_id=session["session_id"])
        assert record["close_reason"] == "SESSION_EXPIRED" and record["cleanup"] == "COMPLETE"
    elif cause in {"revoke", "grant-expiry"}:
        assert runtime.query(access=context["access"]).status_code == 401
        with sqlite3.connect(database=runtime.directory / "hub.sqlite3") as database:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                record = json.loads(database.execute("SELECT record FROM sessions WHERE session_id=?", (session["session_id"],)).fetchone()[0])
                if record["cleanup"] == "COMPLETE":
                    break
                time.sleep(0.03)
        assert record["cleanup"] == "COMPLETE" and record["close_reason"] == ("GRANT_REVOKED" if cause == "revoke" else "SESSION_EXPIRED")
    elif cause == "hub-restart":
        runtime.wait_view(access=context["access"], minimum_generation=context["view"]["connection_generation"] + 1)
        record = wait_session(runtime=runtime, access=context["access"], session_id=session["session_id"], state="INTERRUPTED")
        assert record["cleanup"] == "UNKNOWN"
        new_session = session_response(context=context).json()
        assert new_session["state"] == "READY" and new_session["session_id"] != session["session_id"]
        assert httpx.delete(url=f"{runtime.url}/v1/sessions/{new_session['session_id']}", headers=headers(access=context["access"]), timeout=15).json()["cleanup"] == "COMPLETE"
    else:
        record = wait_session(runtime=runtime, access=context["access"], session_id=session["session_id"], state="INTERRUPTED")
        assert record["cleanup"] == ("COMPLETE" if cause == "node-stop" else "UNKNOWN")
    assert context["chrome"].process.poll() is None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        observed = asyncio.run(targets(endpoint=context["chrome"].endpoint))
        if any(item["targetId"] == context["original"] and not item["attached"] for item in observed):
            break
        time.sleep(0.03)
    assert any(item["targetId"] == context["original"] and not item["attached"] for item in observed)
    assert asyncio.run(account_state(endpoint=context["chrome"].endpoint, url=context["url"])) == context["before"]
    evidence(test_name=f"chrome_disconnect_{cause}", details={"old_sdk_objects_invalid": True, "original_target_detached": True, "browser_process_survives": True, "original_login_and_storage_preserved": True, "hub_cleanup": record["cleanup"], "execution_outcome": record["execution_outcome"]})
