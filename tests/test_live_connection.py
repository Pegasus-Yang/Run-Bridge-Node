"""协议和安装边界：执行 URL 不包含本机浏览器地址。"""

from runbridge_node.executor import websocket_url
from runbridge_node.protocol import SessionOpen


def test_execution_url_preserves_hub_prefix_and_uses_outbound_websocket():
    assert (
        websocket_url(hub_url="https://hub.test/base", path="/v2/nodes/node_a/control")
        == "wss://hub.test/base/v2/nodes/node_a/control"
    )


def test_open_message_has_tool_contract_without_native_endpoint():
    value = SessionOpen(
        connection_generation=1, session_id="session_a", resource_id="chromium"
    ).model_dump()
    assert value["protocol_version"] == 2 and value["tool"] == "playwright"
    assert not {"ws_endpoint", "client_version", "headers"} & value.keys()
