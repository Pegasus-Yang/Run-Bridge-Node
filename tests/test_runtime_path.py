"""损坏或归属不明的活动记录必须隔离，不能误删、误杀或报告完成。"""

import json

import pytest

from runbridge_node.runtime import recover_record


@pytest.mark.parametrize(
    "content", ["{broken", "[]", "{}", '{"temporary_directory": 1}']
)
async def test_malformed_record_remains_unknown(tmp_path, content):
    path = tmp_path / "session.json"
    path.write_text(content)
    assert await recover_record(path=path) == "UNKNOWN"
    assert path.read_text() == content


async def test_record_outside_private_tmp_is_never_removed(tmp_path):
    owned = tmp_path / "rb-data"
    owned.mkdir()
    (owned / "important").write_text("preserve")
    path = tmp_path / "record.json"
    path.write_text(json.dumps({"temporary_directory": str(owned)}))
    assert await recover_record(path=path) == "UNKNOWN"
    assert (owned / "important").read_text() == "preserve"


async def test_stop_before_initialization_releases_only_own_worker(tmp_path):
    import asyncio
    from runbridge_node.runtime import PlaywrightConfig, ToolWorker

    stop = asyncio.Event()
    stop.set()
    worker = ToolWorker(
        config=PlaywrightConfig(
            mode="borrowed",
            authorization_scope="BROWSER_INSTANCE",
            cdp_endpoint="ws://127.0.0.1:1/devtools/browser/test",
        ),
        record_path=tmp_path / "startup.json",
    )

    async def ignore(value):
        pass

    try:
        with pytest.raises(ValueError, match="SESSION_STOPPED"):
            await worker.start(
                session_id="session_stop", generation=1, callback=ignore, stop=stop
            )
    finally:
        assert await worker.close() == "COMPLETE"
    assert not worker.temporary_directory.exists()
    assert not worker.record_path.exists()
