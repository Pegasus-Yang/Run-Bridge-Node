"""本机采集进程的创建与清理，不能启动或关闭借用的 Chrome。"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from runbridge_node.capabilities import package_version
from runbridge_node.visual_protocol import supported_browscreen_version


async def probe_visual() -> bool:
    """在隔离进程中验证可选安装，导入失败不影响执行。

    :returns: 当前环境是否具备受支持且能够导入的扩展。
    """
    if not supported_browscreen_version(value=package_version(name="browscreen")):
        return False
    process = None
    try:
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "runbridge_node.visual_worker", "--check",
                                                      stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        return await asyncio.wait_for(process.wait(), timeout=8) == 0
    except (OSError, TimeoutError):
        return False
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()


class CaptureProcess:
    """每个被选中的目标使用一个自有进程和临时目录。"""

    def __init__(self):
        self.process: asyncio.subprocess.Process | None = None
        self.directory: Path | None = None
        self.url: str | None = None

    async def start(self, *, endpoint: str) -> None:
        """端点由 Node 从固定实例产生，不能由远程调用方提交。"""
        self.directory = Path(tempfile.mkdtemp(prefix="runbridge-visual-"))
        path = self.directory / ".cdp"
        path.write_text(data=endpoint, encoding="utf-8")
        path.chmod(mode=0o600)
        environment = dict(os.environ)
        for key in ("RUNBRIDGE_ENROLLMENT_TOKEN", "RUNBRIDGE_ACCESS_TOKEN", "RUNBRIDGE_NODE_TOKEN"):
            environment.pop(key, None)
        self.process = await asyncio.create_subprocess_exec(sys.executable, "-m", "runbridge_node.visual_worker",
            "--work-dir", str(self.directory), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=environment)
        async with asyncio.timeout(delay=10):
            raw = await self.process.stdout.readline()
        if len(raw) > 4096:
            raise ValueError("采集就绪消息过大")
        result = json.loads(raw)
        if result.get("type") != "ready" or not isinstance(result.get("port"), int) or not 1 <= result["port"] <= 65535:
            raise ValueError("采集进程启动失败")
        self.url = f"http://127.0.0.1:{result['port']}"

    async def close(self) -> str:
        """限时结束自己创建的进程，清理未确认时返回 UNKNOWN。"""
        try:
            if self.process is not None and self.process.returncode is None:
                if self.process.stdin is not None:
                    self.process.stdin.close()
                for action in (None, self.process.terminate, self.process.kill):
                    if action is not None and self.process.returncode is None:
                        try:
                            action()
                        except ProcessLookupError:
                            pass
                    try:
                        await asyncio.wait_for(self.process.wait(), timeout=2)
                        break
                    except TimeoutError:
                        continue
                if self.process.returncode is None:
                    return "UNKNOWN"
            if self.directory is not None:
                try:
                    await asyncio.to_thread(shutil.rmtree, path=self.directory)
                except FileNotFoundError:
                    pass
            self.url = None
            return "COMPLETE"
        except OSError:
            return "UNKNOWN"
