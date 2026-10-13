"""复用授权 Chrome 的原页面；退出仅释放连接，保留浏览器。"""

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


async def execute(*, access_file: Path, resource_id: str, page_url: str, screenshot: Path | None) -> None:
    """只选择 URL 完全匹配且唯一的已有页面，不自动跳转或创建页面。

    :param access_file: 调用许可文件。
    :param resource_id: 所有者授权的 Chrome 资源。
    :param page_url: 已有页面的精确 URL。
    :param screenshot: 可选调用方截图路径。
    """
    access = AccessConfig.model_validate_json(access_file.read_text(encoding="utf-8"))
    token = access.access_token.get_secret_value()
    body = SessionCreate(resource_id=resource_id, client_version=version(distribution_name="playwright"))
    created = await request_json(hub_url=access.hub_url, method="POST", path=f"/v1/nodes/{access.node_id}/sessions", token=token, body=body.model_dump(mode="json"), timeout=40)
    session = SessionView.model_validate(created)
    try:
        if session.native_protocol != "cdp" or session.native_path is None:
            raise ClientError("资源不是已授权 Chrome CDP 会话")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(endpoint_url=websocket_url(hub_url=access.hub_url, path=session.native_path), headers={"Authorization": f"Bearer {token}"}, no_defaults=True, timeout=10000)
            try:
                pages = [page for context in browser.contexts for page in context.pages if page.url == page_url]
                if len(pages) != 1:
                    raise ClientError("已有页面没有唯一匹配；未打开、关闭或导航用户页面")
                page = pages[0]
                if screenshot is not None:
                    await page.screenshot(path=screenshot, full_page=True)
                print(json.dumps({"session_id": session.session_id, "title": await page.title(), "browser_version": browser.version, "reused_existing_page": True}, ensure_ascii=False))
            finally:
                await browser.close()
    finally:
        released = await request_json(hub_url=access.hub_url, method="DELETE", path=f"/v1/sessions/{session.session_id}", token=token, timeout=15)
        if released["cleanup"] != "COMPLETE":
            raise ClientError("会话断开尚未确认；请查询状态，不自动重放")


def main() -> None:
    """失败诊断不打印握手、Cookie 或本机端点。"""
    parser = argparse.ArgumentParser(description="RunBridge 已有 Chrome 复用示例")
    parser.add_argument("--access-file", type=Path, required=True)
    parser.add_argument("--resource-id", default="chrome")
    parser.add_argument("--page-url", required=True)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    try:
        asyncio.run(execute(access_file=args.access_file, resource_id=args.resource_id, page_url=args.page_url, screenshot=args.screenshot))
    except (ClientError, Error, httpx.HTTPError, OSError, ValueError, ValidationError):
        print("Chrome 复用失败；请查询会话及本机授权状态，未自动重放操作", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
