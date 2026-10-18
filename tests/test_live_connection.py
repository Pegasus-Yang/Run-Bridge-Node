"""以两个项目各自的虚拟环境与真实 CLI 验证 HTTP/WebSocket 连接。"""

import asyncio
import json
import os
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus


NODE_PROJECT = Path(__file__).resolve().parents[1]
HUB_PROJECT = Path(os.environ.get("RUNBRIDGE_HUB_PROJECT", NODE_PROJECT.parent / "runbridge-hub"))


def executable(*, project: Path, name: str) -> str:
    """选择指定项目虚拟环境的入口。

    :returns: 可执行文件路径。
    """
    return str(project / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (f"{name}.exe" if os.name == "nt" else name))


class Runtime:
    """管理真实本地测试进程；所有数据在 pytest 临时目录中。"""

    def __init__(self, *, directory: Path):
        self.directory = directory
        self.enrollment_file = directory / "enrollment.token"
        generated = subprocess.run([executable(project=HUB_PROJECT, name="runbridge-hub"), "generate-token", "--output", str(self.enrollment_file)], cwd=HUB_PROJECT, capture_output=True, text=True, timeout=5)
        if generated.returncode != 0:
            raise AssertionError("实际 Hub 登记凭据生成失败")
        self.enrollment = self.enrollment_file.read_text(encoding="utf-8").strip()
        if self.enrollment in generated.stdout or self.enrollment in generated.stderr:
            raise AssertionError("登记凭据生成输出回显了秘密，内容已隐藏")
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            self.port = reserve.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.hub = None
        self.nodes = []
        self.logs = []
        self.environment = dict(os.environ)
        for key in ["RUNBRIDGE_ENROLLMENT_TOKEN", "RUNBRIDGE_ACCESS_TOKEN", "VIRTUAL_ENV"]:
            self.environment.pop(key, None)

    def start_hub(self):
        """启动实际单 Worker Hub，复用同一 SQLite 文件。"""
        self.hub = self._spawn(project=HUB_PROJECT, name="runbridge-hub", arguments=["serve", "--port", str(self.port), "--db-path", str(self.directory / "hub.sqlite3"), "--enrollment-token-file", str(self.enrollment_file), "--heartbeat-interval", "0.05", "--heartbeat-timeout", "2"], log_name="hub.log")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.hub.poll() is not None:
                raise AssertionError("实际 Hub 进程启动失败，详细输出保存在测试日志")
            try:
                if httpx.get(url=f"{self.url}/health", timeout=0.3).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.03)
        raise AssertionError("实际 Hub 未在期限内就绪")

    def command(self, *, arguments: list[str], success: bool = True):
        """执行实际 Node CLI。

        :returns: 子进程结果。
        """
        result = subprocess.run([executable(project=NODE_PROJECT, name="runbridge-node"), *arguments], cwd=NODE_PROJECT, env=self.environment, capture_output=True, text=True, timeout=10)
        if success and result.returncode != 0:
            raise AssertionError("实际 Node CLI 执行失败，错误内容未自动回显")
        return result

    def register(self, *, filename: str = "node.json") -> Path:
        """用实际 CLI 保存并登记稳定身份。

        :returns: 配置路径。
        """
        path = self.directory / filename
        self.command(arguments=["register", "--hub-url", self.url, "--name", "live-test", "--config", str(path), "--enrollment-token-file", str(self.enrollment_file)])
        return path

    def grant(self, *, config: Path, filename: str = "access.json") -> dict:
        """用实际 CLI 签发私有对接文件。

        :returns: 仅供测试使用的凭据配置。
        """
        path = self.directory / filename
        self.command(arguments=["grant", "--config", str(config), "--output", str(path)])
        return json.loads(path.read_text(encoding="utf-8"))

    def start_node(self, *, config: Path):
        """不携带登记凭据启动实际 Node。

        :returns: 节点进程。
        """
        process = self._spawn(project=NODE_PROJECT, name="runbridge-node", arguments=["run", "--config", str(config)], log_name=f"node-{len(self.nodes)}.log")
        self.nodes.append(process)
        return process

    def query(self, *, access: dict):
        """通过对接许可查询实际 API。

        :returns: HTTP 响应。
        """
        return httpx.get(url=f"{self.url}/v1/nodes/{access['node_id']}/capabilities", headers={"Authorization": f"Bearer {access['access_token']}"}, timeout=0.5)

    def wait_view(self, *, access: dict, status: str = "ONLINE", minimum_generation: int = 1, heartbeat_count: int = 2) -> dict:
        """等待来自真实控制连接的观察结果。

        :returns: 节点视图。
        """
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                response = self.query(access=access)
                if response.status_code == 200:
                    view = response.json()
                    if view["connection_status"] == status and view["connection_generation"] >= minimum_generation and (status != "ONLINE" or view["heartbeat_count"] >= heartbeat_count):
                        return view
            except httpx.HTTPError:
                pass
            time.sleep(0.03)
        raise AssertionError("实际节点状态未达到预期")

    def stop(self, *, process):
        """正常停止进程并确认退出。"""
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
                raise AssertionError("测试进程未能正常停止") from None

    def _spawn(self, *, project: Path, name: str, arguments: list[str], log_name: str):
        """将诊断保存到本机临时日志。

        :returns: 子进程。
        """
        log = self.directory / log_name
        if log not in self.logs:
            self.logs.append(log)
        with log.open(mode="a", encoding="utf-8") as output:
            return subprocess.Popen([executable(project=project, name=name), *arguments], cwd=project, env=self.environment, stdout=output, stderr=subprocess.STDOUT)


@pytest.fixture
def runtime(tmp_path):
    if not Path(executable(project=HUB_PROJECT, name="runbridge-hub")).is_file():
        pytest.skip("真实联调需要先准备 Hub 的 .venv，可使用 RUNBRIDGE_HUB_PROJECT 指定项目")
    context = Runtime(directory=tmp_path)
    context.start_hub()
    try:
        yield context
    finally:
        for process in context.nodes:
            context.stop(process=process)
        context.stop(process=context.hub)


def evidence(*, test_name: str, details: dict):
    """只保存公开运行事实，禁止保存凭据。

    :param test_name: 场景名称。
    :param details: 无秘密的事实记录。
    """
    output = os.environ.get("RUNBRIDGE_TEST_EVIDENCE_FILE")
    if output is not None:
        path = Path(output)
        values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        values.append({"test": test_name, "status": "PASS", "checked_at": datetime.now(UTC).isoformat(), "details": details})
        path.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_actual_cli_connects_heartbeats_reconnects_and_persists(runtime):
    configuration = runtime.register()
    before = configuration.read_bytes()
    repeat = runtime.command(arguments=["register", "--hub-url", runtime.url, "--config", str(configuration), "--enrollment-token-file", str(runtime.enrollment_file)])
    assert json.loads(repeat.stdout)["created"] is False
    assert configuration.read_bytes() == before
    identity = json.loads(before)
    access = runtime.grant(config=configuration)
    node = runtime.start_node(config=configuration)
    initial = runtime.wait_view(access=access)
    assert initial["capabilities"]["host"]["python_version"].startswith("3.14.")
    assert initial["capabilities_stale"] is False
    assert initial["capabilities"]["resources"] == []
    inspected = runtime.command(arguments=["inspect", identity["node_id"], "--access-file", str(runtime.directory / "access.json"), "--output", "json"])
    assert json.loads(inspected.stdout)["connection_status"] == "ONLINE"
    assert httpx.get(url=f"{runtime.url}/v1/nodes/{identity['node_id']}", timeout=1).status_code == 401

    async def rejected_control():
        with pytest.raises(InvalidStatus) as rejected:
            async with connect(uri=f"ws://127.0.0.1:{runtime.port}/v1/nodes/{identity['node_id']}/control", additional_headers={"Authorization": "Bearer invalid-node-identity"}, proxy=None):
                pass
        assert rejected.value.response.status_code == 403

    asyncio.run(rejected_control())
    runtime.stop(process=runtime.hub)
    runtime.start_hub()
    reconnected = runtime.wait_view(access=access, minimum_generation=initial["connection_generation"] + 1)
    assert node.poll() is None
    assert configuration.read_bytes() == before
    runtime.command(arguments=["revoke", access["grant_id"], "--config", str(configuration)])
    assert runtime.query(access=access).status_code == 401
    second_access = runtime.grant(config=configuration, filename="second-access.json")
    assert runtime.wait_view(access=second_access)["connection_status"] == "ONLINE"
    runtime.stop(process=node)
    offline = runtime.wait_view(access=second_access, status="OFFLINE")
    assert offline["capabilities_stale"] is True
    runtime.stop(process=runtime.hub)
    runtime.start_hub()
    assert runtime.wait_view(access=second_access, status="OFFLINE")["capabilities"] is not None
    assert runtime.query(access=access).status_code == 401
    logs = "\n".join(path.read_text(encoding="utf-8") for path in runtime.logs)
    for secret in [runtime.enrollment, identity["node_token"], access["access_token"], second_access["access_token"]]:
        if secret in logs or secret in inspected.stdout or secret in repeat.stdout:
            raise AssertionError("响应或进程日志含凭据，内容已隐藏")
    if "Traceback" in logs:
        raise AssertionError("实际进程日志含未处理异常，详细内容保存在临时日志")
    evidence(test_name="actual_cli_lifecycle", details={"python_version": initial["capabilities"]["host"]["python_version"], "client_version": initial["capabilities"]["host"]["client_version"], "initial_generation": initial["connection_generation"], "reconnected_generation": reconnected["connection_generation"], "initial_heartbeats_observed": initial["heartbeat_count"], "registration_idempotent": True, "wrong_identity_rejected": True, "automatic_reconnect": True, "revocation_survives_restart": True, "offline_snapshot_marked_stale": True, "secrets_absent_from_logs": True})


def test_replaced_node_process_stops_and_replacement_remains_online(runtime):
    configuration = runtime.register()
    access = runtime.grant(config=configuration)
    first = runtime.start_node(config=configuration)
    initial = runtime.wait_view(access=access)
    second = runtime.start_node(config=configuration)
    replacement = runtime.wait_view(access=access, minimum_generation=initial["connection_generation"] + 1)
    first.wait(timeout=5)
    assert first.returncode == 1
    assert second.poll() is None
    assert runtime.wait_view(access=access)["connection_generation"] == replacement["connection_generation"]
    evidence(test_name="duplicate_identity_replacement", details={"old_process_stopped": True, "replacement_online": True, "generation_increased": True})


def test_two_yaml_nodes_register_start_and_restart_independently(runtime):
    settings_files = []
    identities = []
    accesses = []
    processes = []
    for label in ("a", "b"):
        directory = runtime.directory / label
        directory.mkdir()
        settings = directory / "node.yaml"
        settings.write_text(f"hub_url: {runtime.url}\nname: office-{label}\nenrollment_token_file: {runtime.enrollment_file}\n")
        process = runtime._spawn(project=NODE_PROJECT, name="runbridge-node", arguments=["run", "--settings", str(settings)], log_name=f"yaml-{label}.log")
        runtime.nodes.append(process)
        identity = directory / ".runbridge/node.json"
        deadline = time.monotonic() + 8
        while not identity.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.03)
        assert identity.exists()
        # 生成身份后仍须等待上线，不能以文件存在代替登记结果。
        deadline = time.monotonic() + 8
        while "节点在线" not in (runtime.directory / f"yaml-{label}.log").read_text():
            assert time.monotonic() < deadline and process.poll() is None
            time.sleep(0.03)
        access = runtime.grant(config=identity, filename=f"{label}/access.json")
        runtime.wait_view(access=access)
        settings_files.append(settings)
        identities.append(identity)
        accesses.append(access)
        processes.append(process)
    assert accesses[0]["node_id"] != accesses[1]["node_id"]
    initial = [runtime.wait_view(access=access) for access in accesses]
    assert all(process.poll() is None for process in processes)
    before = identities[0].read_bytes()
    runtime.stop(process=processes[0])
    settings_files[0].write_text(f"hub_url: {runtime.url}\nname: office-a\n")
    restarted = runtime._spawn(project=NODE_PROJECT, name="runbridge-node", arguments=["run", "--settings", str(settings_files[0])], log_name="yaml-a-restart.log")
    runtime.nodes.append(restarted)
    runtime.wait_view(access=accesses[0], minimum_generation=initial[0]["connection_generation"] + 1)
    assert identities[0].read_bytes() == before
    assert runtime.wait_view(access=accesses[1])["connection_generation"] == initial[1]["connection_generation"]
    assert processes[1].poll() is None
    logs = "\n".join(path.read_text() for path in runtime.logs)
    for secret in [runtime.enrollment, *[json.loads(path.read_text())["node_token"] for path in identities], *[access["access_token"] for access in accesses]]:
        if secret in logs:
            raise AssertionError("YAML 启动日志包含凭据，内容已隐藏")
    evidence(test_name="yaml_bootstrap_multiple_nodes", details={"distinct_identities": True, "simultaneously_online": 2, "restart_without_enrollment": True, "identity_preserved": True, "other_node_unaffected": True})


def test_node_rejects_wrong_identity_without_retrying(runtime):
    configuration = runtime.register()
    bad = json.loads(configuration.read_text(encoding="utf-8"))
    bad["node_token"] = "incorrect-identity-" + "z" * 40
    wrong_file = runtime.directory / "wrong-identity.json"
    wrong_file.write_text(json.dumps(bad), encoding="utf-8")
    result = runtime.command(arguments=["run", "--config", str(wrong_file)], success=False)
    assert result.returncode == 1
    if bad["node_token"] in result.stderr:
        raise AssertionError("身份拒绝诊断含秘密，内容已隐藏")
    evidence(test_name="invalid_node_identity", details={"process_rejected": True, "credential_not_printed": True})
