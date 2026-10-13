"""长运行目录不会产生超长 Chromium UNIX 套接字路径。"""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from runbridge_node.runtime import BrowserServer,PlaywrightConfig

@pytest.mark.asyncio
async def test_long_runtime_keeps_private_short_tmp_and_verified_cleanup(tmp_path,monkeypatch):
    directory=tmp_path / ('long-'*30)
    process=SimpleNamespace(stdin=SimpleNamespace(write=lambda data:None,drain=AsyncMock()),stdout=SimpleNamespace(readline=AsyncMock(return_value=json.dumps({'type':'ready','version':'1.63.0','browser_pid':1234}).encode())))
    spawn=AsyncMock(return_value=process)
    monkeypatch.setattr('runbridge_node.runtime.asyncio.create_subprocess_exec',spawn)
    monkeypatch.setattr('runbridge_node.runtime.os.getpgid',lambda pid:1234)
    server=BrowserServer(config=PlaywrightConfig(runtime_directory=directory))
    await server.start()
    actual=Path(spawn.call_args.kwargs['env']['TMPDIR'])
    assert actual==server.temporary_directory and len(str(actual).encode())<50
    assert actual.stat().st_mode & 0o777 == 0o700
    assert str(directory) not in str(actual)
    server._close_processes=AsyncMock(return_value='UNKNOWN')
    assert await server.close()=='UNKNOWN' and actual.exists()
    server._close_processes=AsyncMock(return_value='COMPLETE')
    assert await server.close()=='COMPLETE' and not actual.exists()
