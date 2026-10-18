"""已有 Chrome 的本机浏览器级授权端点校验。"""

import re
from urllib.parse import urlsplit


def validate_endpoint(*, value: str) -> str:
    """固定实例与回环地址，不扫描浏览器或接收页面级端点。"""
    parsed = urlsplit(value)
    if parsed.scheme != "ws" or parsed.hostname not in {"127.0.0.1", "::1"} or not parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment or re.fullmatch(r"/devtools/browser/[A-Za-z0-9_-]+", parsed.path) is None:
        raise ValueError("需要本机明确的 Chrome 浏览器 WebSocket 端点")
    return value
