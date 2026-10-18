"""Node 本机 Python Playwright 工具；对象不离开本进程。"""

import asyncio
import base64
import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psutil
from playwright.async_api import (
    Error,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from pydantic import ValidationError

from runbridge_node.tool_contract import Execute, Target, validate_call, validate_output
from runbridge_node.tools import ToolError
from runbridge_node.tools.dom import CAPTURE, INSPECT


ActionError = ToolError


class PlaywrightTool:
    """每会话独立 Browser、对象表、页面策略和画面采集。"""

    def __init__(self, *, config: dict, session_id: str, emit):
        self.config = config
        self.session_id = session_id
        self.emit = emit
        self.playwright = None
        self.browser = None
        self.objects: dict[str, tuple[str, object, bool]] = {}
        self.identities: dict[int, str] = {}
        self.selected = None
        self.dialog_policy = {}
        self.last_dialog = {}
        self.capture_targets = {}
        self.closing = False
        self.entered = False
        self.tasks: set[asyncio.Task] = set()
        self.capture_task = None
        self.mode = config["mode"]

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def remember(self, *, kind: str, value, owned: bool) -> dict:
        key = self.identities.get(id(value))
        if key is None:
            key = f"{kind}_{uuid4().hex}"
            self.identities[id(value)] = key
            self.objects[key] = (kind, value, owned)
            if kind == "context":
                value.on(
                    "page",
                    lambda page: self.remember(kind="page", value=page, owned=owned),
                )
            elif kind == "page":
                value.on("close", lambda: self.spawn(self.event(name="page_closed")))
                value.on(
                    "framenavigated",
                    lambda _: self.spawn(self.event(name="page_updated")),
                )
                value.on(
                    "dialog",
                    lambda dialog: self.spawn(self.dialog(page_id=key, dialog=dialog)),
                )
                if self.mode == "borrowed":
                    self.spawn(self.map_capture(page=value, page_id=key))
                self.spawn(self.event(name="page_created"))
        return {"type": kind, "id": key}

    async def map_capture(self, *, page, page_id: str):
        try:
            cdp = await page.context.new_cdp_session(page=page)
            data = await cdp.send(method="Target.getTargetInfo")
            await cdp.detach()
            self.capture_targets[data["targetInfo"]["targetId"]] = page_id
            await self.emit(
                {"type": "capture_targets", "targets": dict(self.capture_targets)}
            )
        except Error:
            pass

    def state(self) -> dict:
        contexts = []
        pages = []
        root = None
        for key, (kind, value, owned) in list(self.objects.items()):
            ref = {"type": kind, "id": key}
            if kind == "browser":
                root = ref
            elif kind == "context" and value in self.browser.contexts:
                contexts.append(ref)
            elif kind == "page" and not value.is_closed():
                pages.append(
                    {
                        **ref,
                        "page_id": key,
                        "context_id": self.identities.get(id(value.context)),
                        "url": value.url,
                    }
                )
        ids = {page["id"] for page in pages}
        if self.selected not in ids:
            self.selected = None
        return {
            "root": root,
            "contexts": contexts,
            "pages": pages,
            "default_page_id": self.selected,
            "ownership": self.mode,
            "last_dialog": dict(self.last_dialog),
        }

    async def event(self, *, name: str):
        if not self.closing and self.browser is not None:
            await self.emit(
                {"type": "event", "event": name, "data": {"objects": self.state()}}
            )

    async def open(self) -> dict:
        self.playwright = await async_playwright().start()
        metadata = {"runtime_version": version("playwright"), "ownership": self.mode}
        if self.mode == "managed":
            self.browser = await self.playwright.chromium.launch(
                **{"timeout": 20000, **self.config["launch_options"]}
            )
            cdp = await self.browser.new_browser_cdp_session()
            data = await cdp.send(method="SystemInfo.getProcessInfo")
            pid = next(
                int(item["id"])
                for item in data["processInfo"]
                if item["type"] == "browser"
            )
            proc = psutil.Process(pid)
            profile = next(
                value.split("=", 1)[1]
                for value in proc.cmdline()
                if value.startswith("--user-data-dir=")
            )
            if (
                not Path(profile)
                .resolve()
                .is_relative_to(Path(self.config["temporary_directory"]).resolve())
            ):
                raise ValueError("BROWSER_OWNERSHIP_UNCONFIRMED")
            await cdp.detach()
            metadata.update(
                browser_pid=pid, browser_created=proc.create_time(), profile=profile
            )
            # 先报告进程归属，后续页面初始化失败时主进程仍能准确回收。
            await self.emit({"type": "ownership", **metadata})
            self.remember(kind="browser", value=self.browser, owned=True)
            context = await self.browser.new_context(
                viewport={"width": 1280, "height": 720}, locale="zh-CN"
            )
            self.remember(kind="context", value=context, owned=True)
            page = await context.new_page()
            self.selected = self.remember(kind="page", value=page, owned=True)["id"]
            png = await page.screenshot(type="png", timeout=5000)
            metadata["visual_ready"] = png.startswith(b"\x89PNG\r\n\x1a\n")
        else:
            self.browser = await self.playwright.chromium.connect_over_cdp(
                endpoint_url=self.config["cdp_endpoint"],
                no_defaults=True,
                timeout=10000,
            )
            self.remember(kind="browser", value=self.browser, owned=False)
            for context in self.browser.contexts:
                self.remember(kind="context", value=context, owned=False)
                for page in context.pages:
                    ref = self.remember(kind="page", value=page, owned=False)
                    await self.map_capture(page=page, page_id=ref["id"])
            pages = self.state()["pages"]
            if len(pages) == 1:
                self.selected = pages[0]["id"]
        metadata["objects"] = self.state()
        metadata["capture_targets"] = dict(self.capture_targets)
        return metadata

    def resolve(self, *, target: Target):
        if target.type == "session":
            if target.id != self.session_id:
                raise ActionError(code="OBJECT_NOT_FOUND")
            return self
        entry = self.objects.get(target.id)
        if entry is None:
            raise ActionError(code="OBJECT_NOT_FOUND")
        kind, value, _ = entry
        if target.type != kind:
            raise ActionError(code="OBJECT_TYPE_MISMATCH")
        if kind == "page" and value.is_closed():
            raise ActionError(code="OBJECT_CLOSED")
        if kind == "context" and value not in self.browser.contexts:
            raise ActionError(code="OBJECT_CLOSED")
        return value

    async def locator(self, *, target: Target):
        root = self.resolve(target=target)
        for step in target.locator:
            params = step.params
            match step.method:
                case "frame_locator":
                    root = root.frame_locator(**params)
                case "locator":
                    root = root.locator(**params)
                case "get_by_role":
                    root = root.get_by_role(**params)
                case "get_by_label":
                    root = root.get_by_label(**params)
                case "get_by_text":
                    root = root.get_by_text(**params)
                case "get_by_test_id":
                    root = root.get_by_test_id(**params)
        if await root.count() > 1:
            raise ActionError(code="AMBIGUOUS_TARGET")
        return root

    async def execute(self, *, request: Execute) -> dict:
        """将工具库异常转为项目错误，通用 worker 无需了解 Playwright。"""
        try:
            result = await self.execute_action(request=request)
            validate_output(method=request.method, result=result)
            return result
        except PlaywrightTimeoutError:
            raise ToolError(
                code="ACTION_TIMEOUT",
                outcome="OUTCOME_UNKNOWN" if self.entered else "COMPLETED",
            ) from None
        except Error:
            raise ToolError(
                code="OPERATION_FAILED",
                outcome="OUTCOME_UNKNOWN" if self.entered else "COMPLETED",
            ) from None
        except ValidationError:
            raise ToolError(
                code="RESULT_INVALID",
                outcome="OUTCOME_UNKNOWN" if self.entered else "COMPLETED",
            ) from None

    def start_background(self):
        if self.mode == "managed":
            self.capture_task = asyncio.create_task(self.capture())

    async def select_visual(self, *, target_id: str):
        if any(page["id"] == target_id for page in self.state()["pages"]):
            self.selected = target_id
            await self.event(name="selection_changed")

    async def execute_action(self, *, request: Execute) -> dict:
        self.entered = False
        spec, params = validate_call(request=request)
        value = self.resolve(target=request.target)
        locator = (
            await self.locator(target=request.target)
            if request.target.locator
            else None
        )
        timeout = min(params.timeout, request.remaining_ms)
        # 内部方法只接受公开参数模型；不接收属性路径或任意 Python 源码。
        if request.method == "page.goto":
            address = urlsplit(params.url)
            if (
                address.scheme not in {"http", "https"}
                or not address.hostname
                or address.username
                or address.password
            ):
                raise ActionError(code="INVALID_NAVIGATION_URL")
        self.entered = spec.mutating
        match request.method:
            case "browser.contexts":
                result = [
                    self.remember(
                        kind="context", value=item, owned=self.mode == "managed"
                    )
                    for item in value.contexts
                ]
            case "browser.new_context":
                context = await value.new_context(
                    viewport=params.viewport.model_dump(), locale=params.locale
                )
                result = self.remember(kind="context", value=context, owned=True)
            case "context.pages":
                result = [
                    self.remember(
                        kind="page",
                        value=item,
                        owned=self.objects[request.target.id][2],
                    )
                    for item in value.pages
                ]
            case "context.new_page":
                page = await value.new_page()
                result = self.remember(
                    kind="page", value=page, owned=self.objects[request.target.id][2]
                )
            case "context.close":
                if not self.objects[request.target.id][2]:
                    raise ActionError(code="BORROWED_CONTEXT_CLOSE_FORBIDDEN")
                await value.close()
                result = {"completed": True}
            case "page.goto":
                response = await value.goto(
                    url=params.url, wait_until=params.wait_until, timeout=timeout
                )
                result = {
                    "url": value.url,
                    "title": await value.title(),
                    "http_status": response.status if response else None,
                }
            case "page.go_back":
                await value.go_back(wait_until=params.wait_until, timeout=timeout)
                result = {"url": value.url}
            case "page.title":
                result = await value.title()
            case "page.url":
                result = value.url
            case "page.frames":
                result = {
                    "frames": [
                        {"name": item.name, "url": item.url} for item in value.frames
                    ]
                }
            case "page.close":
                await value.close()
                result = {"completed": True}
            case "page.aria_snapshot":
                text = await value.aria_snapshot(timeout=timeout, mode="default")
                result = {
                    "url": value.url,
                    "title": await value.title(),
                    "snapshot": text[:20000],
                    "truncated": len(text) > 20000,
                }
            case "page.screenshot":
                data = await value.screenshot(
                    type="png", full_page=params.full_page, timeout=timeout
                )
                if len(data) > 2 * 1024 * 1024:
                    raise ActionError(code="SCREENSHOT_TOO_LARGE")
                return {
                    "kind": "binary",
                    "mime_type": "image/png",
                    "encoding": "base64",
                    "size": len(data),
                    "data": base64.b64encode(data).decode(),
                }
            case "page.set_viewport_size":
                result = params.viewport_size.model_dump()
                await value.set_viewport_size(viewport_size=result)
            case "page.keyboard.press":
                await value.keyboard.press(key=params.key)
                result = {"completed": True, "url": value.url}
            case "page.mouse.wheel":
                await value.mouse.wheel(delta_x=params.delta_x, delta_y=params.delta_y)
                result = {"completed": True}
            case "locator.fill":
                await locator.fill(value=params.value, timeout=timeout)
                result = {"completed": True}
            case "locator.click":
                await locator.click(button=params.button, timeout=timeout)
                result = {"completed": True, "url": value.url}
            case "locator.press":
                await locator.press(key=params.key, timeout=timeout)
                result = {"completed": True, "url": value.url}
            case "locator.hover":
                await locator.hover(timeout=timeout)
                result = {"completed": True}
            case "locator.select_option":
                result = {
                    "selected": await locator.select_option(
                        value=params.value, timeout=timeout
                    )
                }
            case "locator.set_checked":
                await locator.set_checked(checked=params.checked, timeout=timeout)
                result = {"checked": await locator.is_checked(timeout=timeout)}
            case "locator.drag_to":
                other = await self.locator(target=params.target)
                await locator.drag_to(target=other, timeout=timeout)
                result = {"completed": True}
            case "locator.inner_text" | "locator.input_value":
                text = (
                    await locator.inner_text(timeout=timeout)
                    if request.method.endswith("inner_text")
                    else await locator.input_value(timeout=timeout)
                )
                result = {"value": text[:20000], "truncated": len(text) > 20000}
            case "locator.wait_for":
                await locator.wait_for(state=params.state, timeout=timeout)
                result = {"completed": True, "state": params.state}
            case "runbridge.wait_for":
                started = asyncio.get_running_loop().time()
                while True:
                    remaining = timeout - int(
                        (asyncio.get_running_loop().time() - started) * 1000
                    )
                    if remaining <= 0:
                        raise PlaywrightTimeoutError("等待实际值超时")
                    text = (
                        await locator.inner_text(timeout=remaining)
                        if params.state == "text"
                        else await locator.input_value(timeout=remaining)
                    )
                    if text == params.value:
                        break
                    if (asyncio.get_running_loop().time() - started) * 1000 >= timeout:
                        raise PlaywrightTimeoutError("等待实际值超时")
                    await asyncio.sleep(0.05)
                result = {"completed": True, "state": params.state}
            case "locator.set_input_files":
                payloads = []
                total = 0
                for file in params.files:
                    try:
                        data = base64.b64decode(file.data, validate=True)
                    except ValueError:
                        raise ActionError(code="INVALID_UPLOAD_DATA") from None
                    total += len(data)
                    if total > 4 * 1024 * 1024:
                        raise ActionError(code="UPLOAD_TOO_LARGE")
                    payloads.append(
                        {"name": file.name, "mimeType": file.mime_type, "buffer": data}
                    )
                await locator.set_input_files(files=payloads, timeout=timeout)
                result = {"files": [item.name for item in params.files]}
            case "runbridge.inspect_dom":
                result = await value.evaluate(expression=INSPECT, arg=params.selector)
            case "runbridge.capture":
                for origin in params.allowed_origins:
                    address = urlsplit(origin)
                    if (
                        address.scheme not in {"http", "https"}
                        or not address.hostname
                        or address.username
                        or address.password
                        or address.path
                        or address.query
                        or address.fragment
                    ):
                        raise ActionError(code="INVALID_ALLOWED_ORIGIN")
                if any(
                    item.mode != "url" and item.selector is None
                    for item in params.captures.values()
                ):
                    raise ActionError(code="CAPTURE_SELECTOR_REQUIRED")
                try:
                    result = await value.evaluate(
                        expression=CAPTURE,
                        arg={
                            "captures": {
                                name: item.model_dump(exclude_none=True)
                                for name, item in params.captures.items()
                            },
                            "origins": params.allowed_origins,
                        },
                    )
                except Error as error:
                    code = next(
                        (
                            code
                            for code in (
                                "CAPTURE_OUTSIDE_ORIGIN",
                                "AMBIGUOUS_CAPTURE",
                                "INVALID_CAPTURE_NUMBER",
                            )
                            if code in str(error)
                        ),
                        "CAPTURE_FAILED",
                    )
                    raise ActionError(code=code) from None
            case "runbridge.tabs":
                result = await self.tabs(params=params)
            case "runbridge.dialog_policy":
                self.dialog_policy[request.target.id] = {
                    "accept": params.accept,
                    "prompt_text": params.prompt_text,
                }
                result = {"configured": True, "accept": params.accept}
            case "runbridge.session_state":
                result = self.state()
            case _:
                raise ActionError(code="METHOD_UNSUPPORTED")
        if (
            request.method in {"runbridge.capture", "runbridge.inspect_dom"}
            and len(json.dumps(result, ensure_ascii=False).encode()) > 256 * 1024
        ):
            raise ActionError(
                code="CAPTURE_TOO_LARGE"
                if request.method.endswith("capture")
                else "DOM_INSPECTION_TOO_LARGE"
            )
        await self.event(name="page_updated")
        return {"kind": "json", "value": result}

    async def tabs(self, *, params) -> dict:
        page_id = params.page_id
        if params.action in {"select", "close"} and page_id is None:
            raise ActionError(code="PAGE_ID_REQUIRED")
        if params.action == "new":
            context = next(
                (
                    entry[1]
                    for entry in self.objects.values()
                    if entry[0] == "context" and entry[1] in self.browser.contexts
                ),
                None,
            )
            if context is None:
                raise ActionError(code="OBJECT_NOT_FOUND")
            page_id = self.remember(
                kind="page",
                value=await context.new_page(),
                owned=self.mode == "managed",
            )["id"]
            self.selected = page_id
        elif params.action in {"select", "close"}:
            page = self.resolve(target=Target(type="page", id=page_id))
            if params.action == "close":
                await page.close()
                page_id = None
            else:
                self.selected = page_id
        await self.event(name="selection_changed")
        return {**self.state(), "page_id": page_id}

    async def dialog(self, *, page_id: str, dialog):
        self.last_dialog[page_id] = {"type": dialog.type, "message": dialog.message}
        policy = self.dialog_policy.pop(page_id, {})
        try:
            if policy.get("accept"):
                await dialog.accept(prompt_text=policy.get("prompt_text") or "")
            else:
                await dialog.dismiss()
            await self.event(name="dialog_observed")
        except Error:
            pass

    async def capture(self):
        """使用库自身的截图超时，弹窗或导航期间失败后可继续采集。"""
        previous = None
        stream_id = None
        sequence = 0
        while not self.closing:
            try:
                target_id = self.selected
                if target_id is None:
                    await asyncio.sleep(0.2)
                    continue
                page = self.resolve(target=Target(type="page", id=target_id))
                if previous != target_id:
                    previous = target_id
                    stream_id = f"stream_{uuid4().hex}"
                    sequence = 0
                started = datetime.now(UTC).isoformat()
                png = await page.screenshot(type="png", timeout=1500)
                sequence += 1
                if (
                    not self.closing
                    and target_id == self.selected
                    and len(png) <= 2 * 1024 * 1024
                ):
                    await self.emit(
                        {
                            "type": "visual_frame",
                            "target_id": target_id,
                            "stream_id": stream_id,
                            "frame_id": sequence,
                            "capture_started_at": started,
                            "png": base64.b64encode(png).decode(),
                        },
                        optional=True,
                    )
            except Error, ActionError:
                pass
            await asyncio.sleep(0.3)

    async def close(self):
        self.closing = True
        try:
            if self.browser is not None:
                await self.browser.close()
        finally:
            if self.capture_task is not None:
                await asyncio.wait({self.capture_task}, timeout=2)
            if self.playwright is not None:
                await self.playwright.stop()
