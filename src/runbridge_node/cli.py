"""Node 登记、运行、执行和结构化查询入口。"""

import argparse
import asyncio
import logging
import os
import signal
import socket
import sys
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from runbridge_node.client import ClientError, NodeClient, inspect_node, request_json
from runbridge_node.config import AccessConfig
from runbridge_node.protocol import SessionCreate, SessionView
from runbridge_node.visual_protocol import SessionQueryView
from runbridge_node.executor import PlaywrightExecutor
from runbridge_node.startup import RunSettings, prepare_identity


async def execute(*, args) -> None:
    """执行命令；诊断与秘密交付分开。

    :param args: 已解析命令参数。
    """
    if args.command == "session":
        access = AccessConfig.load(path=args.access_file)
        if args.action == "create":
            body = SessionCreate(resource_id=args.resource_id, tool=args.tool, request_id=args.request_id or f"open_{uuid4().hex}", lease_seconds=args.lease_seconds)
            result = await request_json(hub_url=access.hub_url, method="POST", path=f"/v2/nodes/{access.node_id}/sessions", token=access.access_token.get_secret_value(), body=body.model_dump(mode="json"), timeout=40)
        else:
            result = await request_json(hub_url=access.hub_url, method="GET" if args.action == "get" else "DELETE", path=f"/v2/sessions/{args.session_id}", token=access.access_token.get_secret_value(), timeout=15)
        view_type = SessionQueryView if args.action == "get" else SessionView
        print(view_type.model_validate(result).model_dump_json(indent=2))
        return
    if args.command == "inspect":
        access = AccessConfig.load(path=args.access_file) if args.access_file is not None else None
        hub_url = args.hub_url or (access.hub_url if access is not None else None)
        token = access.access_token.get_secret_value() if access is not None else os.environ.get("RUNBRIDGE_ACCESS_TOKEN")
        if not hub_url or not token:
            raise ClientError("查询需要 --access-file，或 --hub-url 与 RUNBRIDGE_ACCESS_TOKEN")
        result = await inspect_node(hub_url=hub_url, node_id=args.node_id, token=token)
        print(result.model_dump_json(indent=2))
        return
    if args.command == "register":
        _, result = await prepare_identity(settings=RunSettings(hub_url=args.hub_url, identity_file=args.config, name=args.name, enrollment_token_file=args.enrollment_token_file), require_registration=True)
        print(result.model_dump_json(indent=2))
        return
    settings = RunSettings.load(path=args.settings)
    config, registered = await prepare_identity(settings=settings)
    if registered is not None:
        logging.info("节点登记完成 node_id=%s created=%s", registered.node_id, registered.created)
    executor = None
    if "playwright" in settings.tools:
        from importlib.util import find_spec
        if find_spec("playwright") is None:
            raise ClientError("缺少 Python Playwright；请在当前虚拟环境安装 runbridge-node[playwright]")
        executor = PlaywrightExecutor(identity=config, config=settings.tools["playwright"], state_directory=settings.identity_file.parent / f"state-{config.node_id}")
    client = NodeClient(config=config, executor=executor)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            pass
    await client.run(stop=stop)


def main() -> None:
    """提供独立于平台或 Agent 的 CLI。"""
    parser = argparse.ArgumentParser(prog="runbridge-node", description="RunBridge 本机节点客户端")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register", help="创建本机身份并登记")
    register.add_argument("--hub-url", required=True)
    register.add_argument("--enrollment-token-file", type=Path)
    register.add_argument("--name", default=socket.gethostname())
    commands.add_parser("run", help="读取 YAML，登记、启动并执行本机 Python 工具")
    register.add_argument("--config", type=Path, default=Path(".runbridge/node.json"))
    inspect = commands.add_parser("inspect", help="可选诊断：使用Hub租约访问文件查询节点和能力")
    inspect.add_argument("node_id")
    inspect.add_argument("--access-file", type=Path)
    inspect.add_argument("--hub-url")
    inspect.add_argument("--output", choices=["json"], default="json")
    commands.choices["run"].add_argument("--settings", type=Path, required=True, help="读取 config_version: 2 的统一 YAML")
    sessions = commands.add_parser("session", help="使用对接许可申请、查询或释放浏览器会话")
    actions = sessions.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create")
    create.add_argument("--resource-id", default="chromium")
    create.add_argument("--tool", default="playwright")
    create.add_argument("--request-id")
    create.add_argument("--lease-seconds", type=float, default=300)
    for action in [create, actions.add_parser("get"), actions.add_parser("close")]:
        action.add_argument("--access-file", type=Path, required=True)
        if action is not create:
            action.add_argument("session_id")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(execute(args=args))
    except ValidationError:
        print("配置或协议数据无效，输入值已隐藏", file=sys.stderr)
        raise SystemExit(2) from None
    except (ClientError, OSError, ValueError) as error:
        print(f"操作失败：{error}", file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        pass
