"""R1 只报告控制能力与安装元数据，不宣称设备就绪。"""

import platform
import shutil
import socket
from importlib.metadata import PackageNotFoundError, version

from runbridge_node import __version__
from runbridge_node.protocol import BackendCapability, CapabilitySnapshot


def package_version(*, name: str) -> str | None:
    """读取当前虚拟环境的分发版本。

    :param name: 分发名称。
    :returns: 已安装版本或空值。
    """
    try:
        return version(distribution_name=name)
    except PackageNotFoundError:
        return None


def probe_capabilities() -> CapabilitySnapshot:
    """探测本机安装元数据，执行资源保持空目录。

    :returns: 有明确覆盖状态的能力快照。
    """
    httpx_version = package_version(name="httpx")
    playwright_version = package_version(name="playwright")
    return CapabilitySnapshot(
        host={"hostname": socket.gethostname(), "platform": platform.system(), "machine": platform.machine(), "python_version": platform.python_version(), "client_version": __version__},
        backends=[
            BackendCapability(name="runbridge-node", installed=True, runtime_version=__version__, version_status="DETECTED", declared_protocols=["runbridge-control-v2"], coverage_status="SUPPORTED"),
            BackendCapability(name="http", installed=httpx_version is not None, runtime_version=httpx_version, version_status="DETECTED" if httpx_version else "NOT_INSTALLED", declared_protocols=["http-request"]),
            BackendCapability(name="playwright", installed=playwright_version is not None, runtime_version=playwright_version, version_status="DETECTED" if playwright_version else "NOT_INSTALLED"),
            BackendCapability(name="appium", installed=shutil.which("appium") is not None, declared_protocols=["webdriver-http"]),
            BackendCapability(name="adb", installed=shutil.which("adb") is not None),
        ],
    )
