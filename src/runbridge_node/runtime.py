"""Python 工具进程的环境、进程归属与确认清理。"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from time import time

import psutil
from pydantic import Field, JsonValue, model_validator

from runbridge_node.config import write_private_json
from runbridge_node.ipc import encode, receive
from runbridge_node.protocol import Identifier, Model


LAUNCH_KEYS = {
    "args",
    "artifacts_dir",
    "channel",
    "chromium_sandbox",
    "downloads_path",
    "env",
    "executable_path",
    "headless",
    "ignore_default_args",
    "proxy",
    "slow_mo",
    "timeout",
    "traces_dir",
}


class PlaywrightConfig(Model):
    """一个所有者明确配置的 Python Playwright 资源。"""

    resource_id: Identifier = "chromium"
    mode: str = "managed"
    browser_cache_directory: Path | None = None
    launch_options: dict[str, JsonValue] = Field(default_factory=dict, repr=False)
    cdp_endpoint: str | None = None
    authorization_scope: str | None = None

    @model_validator(mode="after")
    def validate_options(self):
        if self.mode not in {"managed", "borrowed"}:
            raise ValueError("工具模式必须是 managed 或 borrowed")
        if set(self.launch_options) - LAUNCH_KEYS:
            raise ValueError(
                "存在不支持的 Python launch 字段；旧 camelCase 配置需要先迁移"
            )
        if self.mode == "borrowed":
            from runbridge_node.chrome import validate_endpoint

            self.cdp_endpoint = validate_endpoint(value=self.cdp_endpoint or "")
            if (
                self.authorization_scope != "BROWSER_INSTANCE"
                or self.launch_options
                or self.browser_cache_directory is not None
            ):
                raise ValueError("借用需要 BROWSER_INSTANCE，不能包含浏览器启动配置")
        elif self.cdp_endpoint is not None or self.authorization_scope is not None:
            raise ValueError("managed 不能配置借用端点")
        if self.browser_cache_directory is not None:
            self.browser_cache_directory = self.browser_cache_directory.resolve()
        timeout = self.launch_options.get("timeout", 20000)
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 30000:
            raise ValueError("启动 timeout 必须介于 0 和 30000 毫秒之间")
        return self


def same_process(*, pid: int, created: float) -> psutil.Process | None:
    """拒绝 PID 重用；僵尸进程已不再占有浏览器资源。"""
    try:
        proc = psutil.Process(pid)
        if (
            abs(proc.create_time() - created) < 0.01
            and proc.status() != psutil.STATUS_ZOMBIE
        ):
            return proc
    except psutil.NoSuchProcess:
        pass
    return None


async def recover_record(*, path: Path) -> str:
    """只回收活动记录明确拥有的进程和专用 Profile。"""
    try:
        record = json.loads(path.read_text())
        temporary = Path(record["temporary_directory"]).resolve()
        expected_root = Path(
            "/tmp" if os.name == "posix" else tempfile.gettempdir()
        ).resolve()
        marker = temporary / ".runbridge-owner.json"
        if (
            temporary.parent != expected_root
            or not temporary.name.startswith("rb-")
            or not marker.is_file()
        ):
            return "UNKNOWN"
        if json.loads(marker.read_text()) != record:
            return "UNKNOWN"
        if record["mode"] not in {"managed", "borrowed"}:
            return "UNKNOWN"
        int(record["worker_pid"])
        float(record["worker_created"])
        float(record["started_at"])
    except OSError, ValueError, KeyError, TypeError:
        return "UNKNOWN"
    owned = []
    try:
        if record["mode"] == "managed":
            for item in psutil.process_iter(attrs=["pid", "create_time", "cmdline"]):
                if (
                    item.info["create_time"] is None
                    or item.info["create_time"] < record["started_at"] - 1
                ):
                    continue
                for arg in item.info["cmdline"] or []:
                    if arg.startswith("--user-data-dir=") and Path(
                        arg.split("=", 1)[1]
                    ).resolve().is_relative_to(temporary):
                        owned.append((item.pid, item.info["create_time"]))
                        break
        worker = same_process(
            pid=record["worker_pid"], created=record["worker_created"]
        )
        if worker is not None:
            if "runbridge_node.worker" not in worker.cmdline():
                return "UNKNOWN"
            owned.extend(
                (child.pid, child.create_time())
                for child in worker.children(recursive=True)
            )
            owned.append((worker.pid, worker.create_time()))
        for pid, created in reversed(owned):
            proc = same_process(pid=pid, created=created)
            if proc is not None:
                proc.terminate()
        for _ in range(30):
            if not any(
                same_process(pid=pid, created=created) for pid, created in owned
            ):
                shutil.rmtree(temporary)
                path.unlink(missing_ok=True)
                return "COMPLETE"
            await asyncio.sleep(0.1)
        for pid, created in owned:
            proc = same_process(pid=pid, created=created)
            if proc is not None:
                proc.kill()
        for _ in range(30):
            if not any(
                same_process(pid=pid, created=created) for pid, created in owned
            ):
                shutil.rmtree(temporary)
                path.unlink(missing_ok=True)
                return "COMPLETE"
            await asyncio.sleep(0.1)
    except psutil.AccessDenied, psutil.NoSuchProcess, OSError:
        return "UNKNOWN"
    return "UNKNOWN"


class ToolWorker:
    """以本节点 Python 创建每会话 worker；活动记录跨重启保留。"""

    def __init__(self, *, config: PlaywrightConfig, record_path: Path):
        self.config = config
        self.record_path = record_path
        self.process = None
        self.metadata = {}
        self.reader_task = None
        self.prepared = asyncio.get_running_loop().create_future()
        self.prepared.add_done_callback(self.observe_preparation)
        self.write_lock = asyncio.Lock()
        self.temporary_directory = None
        self.callback = None
        self.cleanup = None

    async def send(self, *, value: dict):
        async with self.write_lock:
            self.process.stdin.write(encode(value=value))
            await self.process.stdin.drain()

    @staticmethod
    def observe_preparation(future):
        if not future.cancelled():
            future.exception()

    async def start(
        self,
        *,
        session_id: str,
        generation: int,
        callback,
        stop: asyncio.Event | None = None,
    ) -> dict:
        self.callback = callback
        self.temporary_directory = Path(
            tempfile.mkdtemp(prefix="rb-", dir="/tmp" if os.name == "posix" else None)
        )
        environment = dict(os.environ, TMPDIR=str(self.temporary_directory))
        if self.config.browser_cache_directory is not None:
            environment["PLAYWRIGHT_BROWSERS_PATH"] = str(
                self.config.browser_cache_directory
            )
        for key in ("DEBUG", "PWDEBUG"):
            environment.pop(key, None)
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "runbridge_node.worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=environment,
            start_new_session=os.name == "posix",
        )
        proc = psutil.Process(self.process.pid)
        record = {
            "worker_pid": proc.pid,
            "worker_created": proc.create_time(),
            "started_at": time(),
            "temporary_directory": str(self.temporary_directory),
            "session_id": session_id,
            "mode": self.config.mode,
        }
        write_private_json(path=self.record_path, values=record)
        write_private_json(
            path=self.temporary_directory / ".runbridge-owner.json", values=record
        )
        self.reader_task = asyncio.create_task(self.read())
        if stop is not None and stop.is_set():
            raise ValueError("SESSION_STOPPED")
        await self.send(
            value={
                "type": "open",
                "session_id": session_id,
                "connection_generation": generation,
                "tool": "playwright",
                "config": {
                    **self.config.model_dump(mode="json"),
                    "temporary_directory": str(self.temporary_directory),
                },
            }
        )
        if stop is None:
            return await asyncio.wait_for(asyncio.shield(self.prepared), timeout=30)
        waiting = asyncio.ensure_future(asyncio.shield(self.prepared))
        stopped = asyncio.create_task(stop.wait())
        try:
            done, _ = await asyncio.wait(
                {waiting, stopped}, timeout=30, return_when=asyncio.FIRST_COMPLETED
            )
            if stopped in done:
                raise ValueError("SESSION_STOPPED")
            if waiting not in done:
                raise TimeoutError("TOOL_INITIALIZATION_TIMEOUT")
            return waiting.result()
        finally:
            waiting.cancel()
            stopped.cancel()
            await asyncio.gather(waiting, stopped, return_exceptions=True)

    async def read(self):
        try:
            while True:
                value = await receive(reader=self.process.stdout)
                if value["type"] == "ready":
                    self.metadata.update(value)
                    if not self.prepared.done():
                        self.prepared.set_result(self.metadata)
                elif value["type"] == "ownership":
                    self.metadata.update(value)
                elif value["type"] == "failed":
                    if not self.prepared.done():
                        self.prepared.set_exception(
                            ValueError("TOOL_INITIALIZATION_FAILED")
                        )
                elif value["type"] != "closed":
                    await self.callback(value)
        except (
            asyncio.IncompleteReadError,
            BrokenPipeError,
            ConnectionError,
            ValueError,
        ):
            if not self.prepared.done():
                self.prepared.set_exception(ValueError("TOOL_INITIALIZATION_FAILED"))

    async def close(self) -> str:
        if self.cleanup == "COMPLETE":
            return self.cleanup
        if self.process is None:
            if (
                self.temporary_directory is not None
                and self.temporary_directory.exists()
            ):
                shutil.rmtree(self.temporary_directory)
            self.cleanup = "COMPLETE"
            return "COMPLETE"
        if self.process.returncode is None:
            try:
                await self.send(value={"type": "close"})
                self.process.stdin.close()
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except BrokenPipeError, ConnectionError, TimeoutError:
                pass
        cleanup = (
            await recover_record(path=self.record_path)
            if self.record_path.exists()
            else "UNKNOWN"
        )
        if self.process.returncode is None:
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2)
            except TimeoutError:
                cleanup = "UNKNOWN"
        if self.reader_task is not None:
            self.reader_task.cancel()
            await asyncio.gather(self.reader_task, return_exceptions=True)
        self.cleanup = cleanup
        return cleanup
