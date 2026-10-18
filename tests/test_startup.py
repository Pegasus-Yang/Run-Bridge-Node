"""统一 YAML 的路径、登记重试与浏览器选择契约。"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from runbridge_node.cli import main
from runbridge_node.client import ClientError
from runbridge_node.config import NodeConfig
from runbridge_node.protocol import RegistrationResult
from runbridge_node.runtime import PlaywrightConfig
from runbridge_node.startup import RunSettings, prepare_identity


def test_yaml_paths_are_anchored_to_file_from_other_working_directory(
    tmp_path, monkeypatch
):
    settings_file = tmp_path / "office/node.yaml"
    settings_file.parent.mkdir()
    settings_file.write_text("""config_version: 2
hub_url: http://hub.test:8787/
enrollment_token_file: enrollment.token
tools:
  playwright:
    browser_cache_directory: shared-browsers
    launch_options:
      executable_path: browsers/chromium
      headless: true
""")
    monkeypatch.chdir(Path("/"))
    settings = RunSettings.load(path=settings_file)
    assert settings.identity_file == settings_file.parent / ".runbridge/node.json"
    assert settings.enrollment_token_file == settings_file.parent / "enrollment.token"
    browser = settings.tools["playwright"]
    assert browser.browser_cache_directory == settings_file.parent / "shared-browsers"
    assert browser.launch_options["executable_path"] == str(
        settings_file.parent / "browsers/chromium"
    )
    assert settings.hub_url == "http://hub.test:8787"


@pytest.mark.parametrize(
    "text",
    [
        "- not-a-mapping",
        "hub_url: [",
        "unknown_setting: true",
        "playwright: {}\nchrome:\n  authorization_scope: BROWSER_INSTANCE\n  cdp_endpoint: ws://127.0.0.1:9222/devtools/browser/test",
    ],
)
def test_invalid_or_ambiguous_yaml_is_rejected(tmp_path, text):
    path = tmp_path / "node.yaml"
    path.write_text(text)
    with pytest.raises((ValueError, ValidationError)):
        RunSettings.load(path=path)


@pytest.mark.asyncio
async def test_registration_failure_retries_with_same_saved_identity(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("RUNBRIDGE_ENROLLMENT_TOKEN", raising=False)
    token = tmp_path / "enrollment.token"
    token.write_text("test-enrollment-" + "x" * 48)
    settings = RunSettings(
        hub_url="http://hub.test:8787",
        identity_file=tmp_path / "node.json",
        enrollment_token_file=token,
    )
    register = AsyncMock(side_effect=ClientError("network failed"))
    monkeypatch.setattr("runbridge_node.startup.NodeClient.register", register)
    with pytest.raises(ClientError):
        await prepare_identity(settings=settings)
    before = settings.identity_file.read_bytes()
    identity = NodeConfig.load(path=settings.identity_file)
    register.side_effect = None
    register.return_value = RegistrationResult(node_id=identity.node_id, created=False)
    loaded, result = await prepare_identity(settings=settings)
    assert loaded.node_id == identity.node_id and result.created is False
    assert settings.identity_file.read_bytes() == before
    assert register.await_count == 2
    assert settings.identity_file.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_existing_identity_restarts_without_enrollment_and_rejects_other_hub(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("RUNBRIDGE_ENROLLMENT_TOKEN", raising=False)
    path = tmp_path / "node.json"
    original = NodeConfig(
        hub_url="http://hub.test", name="old", node_id="node_saved", node_token="x" * 64
    )
    original.save(path=path)
    register = AsyncMock()
    monkeypatch.setattr("runbridge_node.startup.NodeClient.register", register)
    loaded, result = await prepare_identity(settings=RunSettings(identity_file=path))
    assert loaded.node_id == original.node_id and result is None
    register.assert_not_awaited()
    with pytest.raises(ClientError, match="其他 Hub"):
        await prepare_identity(
            settings=RunSettings(identity_file=path, hub_url="http://other.test")
        )


@pytest.mark.asyncio
async def test_missing_initial_credentials_do_not_create_identity(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("RUNBRIDGE_ENROLLMENT_TOKEN", raising=False)
    settings = RunSettings(
        hub_url="http://hub.test", identity_file=tmp_path / "node.json"
    )
    with pytest.raises(ClientError, match="首次启动"):
        await prepare_identity(settings=settings)
    assert not settings.identity_file.exists()


def test_browser_cache_default_does_not_override_official_environment():
    assert PlaywrightConfig().browser_cache_directory is None


def test_yaml_and_legacy_cli_parameters_cannot_be_mixed(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["runbridge-node", "run", "--settings", "node.yaml", "--config", "old.json"],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err
