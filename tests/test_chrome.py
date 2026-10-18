"""本机已有 Chrome 的明确授权与端点限制。"""

import pytest
from pydantic import ValidationError

from runbridge_node.runtime import PlaywrightConfig


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:9222",
        "ws://example.com:9222/devtools/browser/a",
        "ws://127.0.0.1:9222/devtools/page/a",
        "ws://127.0.0.1:9222/devtools/browser/a?token=x",
        "ws://u:p@127.0.0.1:9222/devtools/browser/a",
    ],
)
def test_endpoint_rejects_discovery_remote_page_and_secret_urls(endpoint):
    with pytest.raises(ValidationError):
        PlaywrightConfig(
            mode="borrowed",
            authorization_scope="BROWSER_INSTANCE",
            cdp_endpoint=endpoint,
        )


def test_instance_authorization_is_required_and_no_launch_options_are_allowed():
    endpoint = "ws://127.0.0.1:9222/devtools/browser/a"
    for extra in (
        {},
        {
            "authorization_scope": "BROWSER_INSTANCE",
            "launch_options": {"headless": True},
        },
    ):
        with pytest.raises(ValidationError):
            PlaywrightConfig(mode="borrowed", cdp_endpoint=endpoint, **extra)
    assert (
        PlaywrightConfig(
            mode="borrowed",
            authorization_scope="BROWSER_INSTANCE",
            cdp_endpoint=endpoint,
        ).mode
        == "borrowed"
    )


@pytest.mark.parametrize(
    "options", [{"executablePath": "old"}, {"timeout": 0}, {"timeout": 30001}]
)
def test_old_launch_options_and_unbounded_timeouts_are_rejected(options):
    with pytest.raises(ValidationError):
        PlaywrightConfig(launch_options=options)
