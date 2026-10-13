"""本机稳定身份与真实安装元数据。"""

import os
import platform

import pytest
from pydantic import ValidationError

from runbridge_node.capabilities import probe_capabilities
from runbridge_node.config import NodeConfig


def test_identity_file_is_private_and_never_overwritten(tmp_path):
    path = tmp_path / "node.json"
    secret = "test-identity-" + "x" * 40
    configuration = NodeConfig(hub_url="http://127.0.0.1:8787/", node_id="node_test", name="test", node_token=secret)
    configuration.save(path=path)
    loaded = NodeConfig.load(path=path)
    assert loaded.node_id == configuration.node_id
    assert loaded.hub_url == "http://127.0.0.1:8787"
    if secret in repr(loaded):
        raise AssertionError("配置 repr 含秘密，内容已隐藏")
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        configuration.save(path=path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("url", ["ftp://example.test", "https://user:secret@example.test", "https://example.test?secret=value"])
def test_hub_url_disallows_credentials_and_non_http(url):
    with pytest.raises(ValidationError):
        NodeConfig(hub_url=url, node_id="node_test", name="test", node_token="test-identity-" + "x" * 40)


def test_probe_reports_installed_tools_without_fake_ready_devices():
    snapshot = probe_capabilities()
    assert snapshot.host["python_version"] == platform.python_version()
    assert snapshot.host["python_version"].startswith("3.14.")
    assert snapshot.resources == []
    backends = {backend.name: backend for backend in snapshot.backends}
    assert backends["runbridge-node"].coverage_status == "SUPPORTED"
    assert backends["http"].installed is True
    for name in ["http", "playwright", "appium", "adb"]:
        assert backends[name].coverage_status == "NOT_IMPLEMENTED"
