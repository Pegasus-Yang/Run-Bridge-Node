"""长度前缀 IPC 的类型、边界及截断验证。"""

import asyncio
import io
import struct

import pytest

from runbridge_node.ipc import encode, read_blocking, receive
from runbridge_node.tool_contract import MAX_MESSAGE


def test_binary_length_prefix_round_trip_and_eof():
    value = {"type": "example", "value": "中文"}
    stream = io.BytesIO(encode(value=value))
    assert read_blocking(stream=stream) == value
    assert read_blocking(stream=stream) is None


@pytest.mark.parametrize(
    "data",
    [struct.pack("!I", MAX_MESSAGE + 1), b"\x00\x00", struct.pack("!I", 20) + b"{}"],
)
def test_truncated_or_oversized_message_fails(data):
    with pytest.raises((ValueError, EOFError)):
        read_blocking(stream=io.BytesIO(data))


async def test_async_stream_handles_partial_chunks():
    reader = asyncio.StreamReader()
    packet = encode(value={"type": "test"})
    for byte in packet:
        reader.feed_data(bytes([byte]))
    assert await receive(reader=reader) == {"type": "test"}
