"""使用锁定的 Node.js Playwright 运行时，不依赖 Python 私有协议。"""

import asyncio
import json
import os
import shutil
import signal
import tempfile
from pathlib import Path

from pydantic import Field, JsonValue, model_validator

from runbridge_node.protocol import Identifier, Model


PLAYWRIGHT_VERSION = "1.63.0"
RUNTIME_SOURCE = Path(__file__).parent / "playwright_runtime"
LAUNCH_KEYS = {"args", "artifactsDir", "channel", "chromiumSandbox", "downloadsPath", "env", "executablePath", "headless", "ignoreDefaultArgs", "proxy", "slowMo", "timeout", "tracesDir"}


class PlaywrightConfig(Model):
    """节点所有者启用的受管理 Chromium 资源位。"""

    runtime_directory: Path
    node_executable: str = "node"
    resource_id: Identifier = "chromium"
    launch_options: dict[str, JsonValue] = Field(default_factory=dict, repr=False)

    @model_validator(mode="after")
    def validate_options(self):
        """不静默忽略配置字段；传输参数由 Node 管理。

        :returns: 已检查的配置。
        """
        if set(self.launch_options) - LAUNCH_KEYS:
            raise ValueError("存在不支持的 Chromium launchServer 配置字段")
        self.runtime_directory = self.runtime_directory.resolve()
        return self


def runtime_environment(*, directory: Path) -> dict[str, str]:
    """只给执行运行时指定专用浏览器缓存。

    :returns: 子进程环境。
    """
    values = dict(os.environ)
    values["PLAYWRIGHT_BROWSERS_PATH"] = str(directory / "browsers")
    values.pop("DEBUG", None)
    values.pop("PWDEBUG", None)
    return values


async def prepare_runtime(*, directory: Path, node_executable: str = "node") -> None:
    """从包内锁文件安装独立运行时和 Chromium，不清理共享缓存。

    :param directory: Node 所有者选择的目录。
    :param node_executable: Node.js 可执行文件。
    """
    directory = directory.resolve()
    npm = shutil.which("npm")
    node = shutil.which(node_executable)
    if npm is None or node is None:
        raise ValueError("准备 Playwright 需要 Node.js 和 npm")
    directory.mkdir(parents=True, exist_ok=True)
    for filename in ["package.json", "package-lock.json"]:
        source = RUNTIME_SOURCE / filename
        target = directory / filename
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError("运行时目录存在不同的依赖文件，请选择独立空目录")
        target.write_bytes(source.read_bytes())
    environment = runtime_environment(directory=directory)
    environment["PATH"] = f"{Path(node).parent}{os.pathsep}{environment.get('PATH', '')}"
    environment["npm_config_cache"] = str(directory / "npm-cache")
    for arguments in [[npm, "ci", "--prefix", str(directory), "--ignore-scripts", "--no-audit", "--no-fund"], [node, str(directory / "node_modules/playwright/cli.js"), "install", "chromium"]]:
        process = await asyncio.create_subprocess_exec(*arguments, env=environment)
        if await process.wait() != 0:
            raise ValueError("Playwright 运行时准备失败，请检查安装输出")


class BrowserServer:
    """每会话一个自建进程，通过 stdin EOF 和公开 close 清理。"""

    def __init__(self, *, config: PlaywrightConfig):
        self.config = config
        self.process = None
        self.metadata = None
        self.browser_group = None
        self.temporary_directory = None

    async def start(self) -> dict:
        """启动本机原生浏览器服务，端点不对外公开。

        :returns: 仅供 Node 内部使用的准备信息。
        """
        # Chromium 的 SingletonSocket 受 UNIX 路径长度限制，运行目录不能作为 TMPDIR。
        temporary_root = Path("/tmp") if os.name == "posix" else Path(tempfile.gettempdir())
        self.temporary_directory = Path(tempfile.mkdtemp(prefix="rb-", dir=temporary_root))
        environment = runtime_environment(directory=self.config.runtime_directory)
        environment["TMPDIR"] = str(self.temporary_directory)
        self.process = await asyncio.create_subprocess_exec(self.config.node_executable, str(RUNTIME_SOURCE / "server.mjs"), str(self.config.runtime_directory), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=environment, start_new_session=os.name == "posix")
        self.process.stdin.write((json.dumps(self.config.launch_options) + "\n").encode())
        await self.process.stdin.drain()
        raw = await asyncio.wait_for(self.process.stdout.readline(), timeout=30)
        metadata = json.loads(raw)
        if metadata.get("type") != "ready" or metadata.get("version") != PLAYWRIGHT_VERSION:
            raise ValueError("Playwright 服务未就绪或版本与锁文件不一致")
        self.metadata = metadata
        if os.name == "posix":
            self.browser_group = os.getpgid(metadata["browser_pid"])
        return metadata

    async def close(self) -> str:
        """确认自建进程退出；强制终止只针对本次创建的进程组。

        :returns: COMPLETE 或 UNKNOWN。
        """
        result = await self._close_processes()
        if result == "COMPLETE" and self.temporary_directory is not None:
            try:
                await asyncio.to_thread(shutil.rmtree, self.temporary_directory)
            except OSError:
                return "UNKNOWN"
        return result

    async def _close_processes(self) -> str:
        """确认 helper 和公开 API 返回的自建浏览器进程组都已退出。

        :returns: 进程清理状态。
        """
        process = self.process
        if process is None:
            return "COMPLETE"
        if process.stdin is not None:
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=8)
            raw = await process.stdout.read()
            records = [json.loads(line) for line in raw.splitlines()]
            if process.returncode == 0 and any(item.get("type") == "closed" and item.get("cleanup") == "COMPLETE" for item in records):
                return "COMPLETE"
        except (OSError, ValueError, TimeoutError):
            pass
        groups = [process.pid]
        if self.metadata is not None and self.browser_group == self.metadata["browser_pid"]:
            groups.append(self.browser_group)
        try:
            if os.name == "posix":
                for group in groups:
                    try:
                        os.killpg(group, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            elif process.returncode is None:
                process.kill()
            await asyncio.wait_for(process.wait(), timeout=3)
        except (OSError, TimeoutError):
            pass
        if os.name == "posix":
            for _ in range(30):
                remaining = []
                for group in groups:
                    try:
                        os.killpg(group, 0)
                        remaining.append(group)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        return "UNKNOWN"
                if not remaining:
                    if self.metadata is not None and self.browser_group != self.metadata["browser_pid"]:
                        return "UNKNOWN"
                    return "COMPLETE"
                await asyncio.sleep(0.1)
        return "UNKNOWN"
