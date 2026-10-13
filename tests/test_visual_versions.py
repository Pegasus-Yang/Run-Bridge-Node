"""可选库版本范围、隔离进程加载和实际上传版本。"""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from runbridge_node.config import NodeConfig
from runbridge_node.protocol import SessionOpen
from runbridge_node.visual import VisualPublisher
from runbridge_node.visual_capture import probe_visual
from runbridge_node.visual_worker import load_browscreen


@pytest.mark.parametrize("value", ["0.3.1", "0.3.2", "0.3.10", "0.3.1.post1", "0.3.2+local"])
async def test_compatible_version_reaches_probe_and_worker_imports(monkeypatch, value):
    """探测和采集进程均接受范围内版本，不能仅放宽安装声明。"""
    monkeypatch.setattr("runbridge_node.visual_capture.package_version", lambda *, name: value)
    child = SimpleNamespace(wait=AsyncMock(return_value=0), returncode=0)
    spawn = AsyncMock(return_value=child)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    assert await probe_visual()
    spawn.assert_awaited_once()

    monkeypatch.setattr("runbridge_node.visual_worker.version", lambda *, distribution_name: value)
    create_app, settings = object(), object()
    uvicorn = ModuleType("uvicorn")
    monkeypatch.setitem(sys.modules, "browscreen.app", SimpleNamespace(create_app=create_app))
    monkeypatch.setitem(sys.modules, "browscreen.models", SimpleNamespace(Settings=settings))
    monkeypatch.setitem(sys.modules, "uvicorn", uvicorn)
    assert load_browscreen() == (create_app, settings, uvicorn)


@pytest.mark.parametrize("value", ["0.3.0", "0.4.0", "0.3.2rc1", "invalid"])
def test_worker_rejects_unsupported_version_before_import(monkeypatch, value):
    """直接启动隔离进程也不能绕过范围检查。"""
    monkeypatch.setattr("runbridge_node.visual_worker.version", lambda *, distribution_name: value)
    with pytest.raises(ValueError, match="不受支持的 Browscreen 版本"):
        load_browscreen()


async def test_upload_hello_reports_installed_version(monkeypatch):
    """安装后续补丁版时，上报的版本必须与安装元数据一致。"""
    monkeypatch.setattr("runbridge_node.visual.package_version", lambda *, name: "0.3.2")
    messages = []

    class Connection:
        async def send(self, *, message):
            messages.append(json.loads(message))
            raise asyncio.CancelledError

    @asynccontextmanager
    async def opening(**kwargs):
        yield Connection()

    monkeypatch.setattr("runbridge_node.visual.connect", opening)
    publisher = VisualPublisher(
        identity=NodeConfig(hub_url="http://127.0.0.1:1", node_id="node_a", name="测试", node_token="test-node-token-" * 3),
        endpoint="ws://127.0.0.1:1/devtools/browser/browser_a",
        message=SessionOpen(connection_generation=1, session_id="session_a", resource_id="chrome"), support_cache={})
    with pytest.raises(asyncio.CancelledError):
        await publisher.upload()
    assert messages == [{"type": "hello", "visual_protocol_version": 1, "browscreen_version": "0.3.2"}]
