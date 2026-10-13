"""普通调用脚本：申请 Node 浏览器，用官方 SDK 执行，然后释放。"""

import argparse
import asyncio
import json
import sys
from importlib.metadata import version
from pathlib import Path

import httpx
from playwright.async_api import Error, async_playwright
from pydantic import ValidationError

from runbridge_node.client import ClientError, request_json
from runbridge_node.config import AccessConfig
from runbridge_node.executor import websocket_url
from runbridge_node.protocol import SessionCreate, SessionView


async def execute(*, access_file: Path, url: str, screenshot: Path | None) -> None:
    """使用调用许可，执行参数直接交给官方 SDK。

    :param access_file: 不含 Node 身份秘密的调用许可文件。
    :param url: 浏览器在节点网络上访问的地址。
    :param screenshot: 调用方截图输出文件。
    """
    access = AccessConfig.model_validate_json(access_file.read_text(encoding="utf-8"))
    token = access.access_token.get_secret_value()
    body = SessionCreate(resource_id="chromium", client_version=version(distribution_name="playwright"))
    created = await request_json(hub_url=access.hub_url, method="POST", path=f"/v1/nodes/{access.node_id}/sessions", token=token, body=body.model_dump(mode="json"), timeout=40)
    session = SessionView.model_validate(created)
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect(endpoint=websocket_url(hub_url=access.hub_url, path=session.native_path), headers={"Authorization": f"Bearer {token}"}, timeout=10000)
            try:
                page = await browser.new_page()
                await page.goto(url=url, wait_until="domcontentloaded")
                if screenshot is not None:
                    await page.screenshot(path=screenshot, full_page=True)
                print(json.dumps({"session_id": session.session_id, "title": await page.title(), "browser_version": browser.version}, ensure_ascii=False))
            finally:
                await browser.close()
    finally:
        await request_json(hub_url=access.hub_url, method="DELETE", path=f"/v1/sessions/{session.session_id}", token=token, timeout=15)


def main() -> None:
    """从私有文件加载凭据，失败时不打印 SDK 握手原文。"""
    parser = argparse.ArgumentParser(description="RunBridge Playwright 调用示例")
    parser.add_argument("--access-file", type=Path, required=True)
    parser.add_argument("--url", default="data:text/html,<title>RunBridge</title><h1>Playwright connected</h1>")
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    try:
        asyncio.run(execute(access_file=args.access_file, url=args.url, screenshot=args.screenshot))
    except (ClientError, Error, httpx.HTTPError, OSError, ValueError, ValidationError):
        print("执行失败；请通过会话查询与本机状态确认结果，未自动重放操作", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
