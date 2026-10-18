"""有界长度分帧 JSON，供节点与 Python 工具进程通信。"""

import asyncio
import json
import struct

from runbridge_node.tool_contract import MAX_MESSAGE


def encode(*, value: dict) -> bytes:
    data = json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()
    if len(data) > MAX_MESSAGE:
        raise ValueError("MESSAGE_TOO_LARGE")
    return struct.pack("!I", len(data)) + data


async def receive(*, reader: asyncio.StreamReader) -> dict:
    size = struct.unpack("!I", await reader.readexactly(4))[0]
    if not 0 < size <= MAX_MESSAGE:
        raise ValueError("INVALID_MESSAGE_SIZE")
    value = json.loads(await reader.readexactly(size))
    if not isinstance(value, dict):
        raise ValueError("INVALID_MESSAGE")
    return value


def read_blocking(*, stream) -> dict | None:
    """读取 worker 输入；EOF 作为独立清理信号。"""
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError("INCOMPLETE_MESSAGE")
    size = struct.unpack("!I", header)[0]
    if not 0 < size <= MAX_MESSAGE:
        raise ValueError("INVALID_MESSAGE_SIZE")
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("INCOMPLETE_MESSAGE")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("INVALID_MESSAGE")
    return value
