"""Node 登记、运行、许可管理和结构化查询入口。"""

import argparse
import asyncio
import logging
import os
import signal
import socket
import sys
from pathlib import Path

from pydantic import ValidationError

from runbridge_node.client import ClientError, NodeClient, inspect_node, request_json
from runbridge_node.chrome import ChromeConfig, ChromeExecutor
from runbridge_node.config import AccessConfig, NodeConfig
from runbridge_node.protocol import GrantRequest, SessionCreate, SessionView
from runbridge_node.visual_protocol import SessionQueryView
from runbridge_node.executor import PlaywrightExecutor
from runbridge_node.runtime import PlaywrightConfig, prepare_runtime, PLAYWRIGHT_VERSION
from runbridge_node.startup import RunSettings, prepare_identity


async def execute(*, args) -> None:
    """执行命令；诊断与秘密交付分开。

    :param args: 已解析命令参数。
    """
    if args.command == "prepare-playwright":
        await prepare_runtime(directory=args.runtime_dir, node_executable=args.node_executable)
        print(f"Playwright {PLAYWRIGHT_VERSION} 运行时已准备：{args.runtime_dir.resolve()}")
        return
    if args.command == "session":
        access = AccessConfig.model_validate_json(args.access_file.read_text(encoding="utf-8"))
        if args.action == "create":
            body = SessionCreate(resource_id=args.resource_id, client_version=args.client_version, lease_seconds=args.lease_seconds)
            result = await request_json(hub_url=access.hub_url, method="POST", path=f"/v1/nodes/{access.node_id}/sessions", token=access.access_token.get_secret_value(), body=body.model_dump(mode="json"), timeout=40)
        else:
            result = await request_json(hub_url=access.hub_url, method="GET" if args.action == "get" else "DELETE", path=f"/v1/sessions/{args.session_id}", token=access.access_token.get_secret_value(), timeout=15)
        view_type = SessionQueryView if args.action == "get" else SessionView
        print(view_type.model_validate(result).model_dump_json(indent=2))
        return
    if args.command == "inspect":
        access = AccessConfig.model_validate_json(args.access_file.read_text(encoding="utf-8")) if args.access_file is not None else None
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
    settings = None
    if args.command == "run" and args.settings is not None:
        settings = RunSettings.load(path=args.settings)
        config, registered = await prepare_identity(settings=settings)
        if registered is not None:
            logging.info("节点登记完成 node_id=%s created=%s", registered.node_id, registered.created)
    else:
        config = NodeConfig.load(path=args.config or Path(".runbridge/node.json"))
    executor = None
    if args.command == "run" and (args.playwright_config is not None or settings is not None and settings.playwright is not None):
        runtime = settings.playwright if settings is not None else PlaywrightConfig.model_validate_json(args.playwright_config.read_text(encoding="utf-8"))
        executor = PlaywrightExecutor(identity=config, config=runtime)
    if args.command == "run" and (args.chrome_config is not None or settings is not None and settings.chrome is not None):
        chrome = settings.chrome if settings is not None else ChromeConfig.model_validate_json(args.chrome_config.read_text(encoding="utf-8"))
        executor = ChromeExecutor(identity=config, config=chrome)
    client = NodeClient(config=config, executor=executor)
    if args.command == "grant":
        if args.output.exists():
            raise ClientError("对接码输出文件已存在，未签发新许可")
        created = await client.create_grant(request=GrantRequest(resource_ids=args.resource_id, expires_in_seconds=args.expires_in))
        access = AccessConfig(hub_url=config.hub_url, node_id=config.node_id, grant_id=created.grant_id, access_token=created.access_token, expires_at=created.expires_at)
        try:
            access.save(path=args.output)
        except OSError:
            try:
                await client.revoke(grant_id=created.grant_id)
            except ClientError:
                raise ClientError(f"对接码保存失败，撤销未确认；请检查许可 {created.grant_id}") from None
            raise ClientError("对接码保存失败，本次许可已撤销") from None
        print(f"许可 {created.grant_id} 的对接码已保存：{args.output}")
    elif args.command == "revoke":
        await client.revoke(grant_id=args.grant_id)
        print(f"许可已撤销：{args.grant_id}")
    elif args.command == "run":
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
    for command in [register, commands.add_parser("run", help="连接、上报能力并发送心跳"), commands.add_parser("grant", help="创建独立对接码"), commands.add_parser("revoke", help="撤销对接码")]:
        command.add_argument("--config", type=Path, default=None if command is commands.choices["run"] else Path(".runbridge/node.json"))
    grant = commands.choices["grant"]
    grant.add_argument("--output", type=Path, required=True)
    grant.add_argument("--resource-id", action="append")
    grant.add_argument("--expires-in", type=float)
    commands.choices["revoke"].add_argument("grant_id")
    inspect = commands.add_parser("inspect", help="使用对接码查询节点和能力")
    inspect.add_argument("node_id")
    inspect.add_argument("--access-file", type=Path)
    inspect.add_argument("--hub-url")
    inspect.add_argument("--output", choices=["json"], default="json")
    execution = commands.choices["run"].add_mutually_exclusive_group()
    commands.choices["run"].add_argument("--settings", type=Path, help="读取统一 YAML，首次登记并启动；不可与旧配置参数混用")
    execution.add_argument("--playwright-config", type=Path)
    execution.add_argument("--chrome-config", type=Path, help="授权复用已有 Chrome；不启动或关闭浏览器")
    prepare = commands.add_parser("prepare-playwright", help="安装锁定的独立 Playwright 运行时和 Chromium")
    prepare.add_argument("--runtime-dir", type=Path, default=Path(".runbridge/playwright"))
    prepare.add_argument("--node-executable", default="node")
    sessions = commands.add_parser("session", help="使用对接许可申请、查询或释放浏览器会话")
    actions = sessions.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create")
    create.add_argument("--resource-id", default="chromium")
    create.add_argument("--client-version", required=True)
    create.add_argument("--lease-seconds", type=float, default=300)
    for action in [create, actions.add_parser("get"), actions.add_parser("close")]:
        action.add_argument("--access-file", type=Path, required=True)
        if action is not create:
            action.add_argument("session_id")
    args = parser.parse_args()
    if args.command == "run" and args.settings is not None and any(value is not None for value in (args.config, args.playwright_config, args.chrome_config)):
        parser.error("--settings 不能与 --config、--playwright-config 或 --chrome-config 同时使用")
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
