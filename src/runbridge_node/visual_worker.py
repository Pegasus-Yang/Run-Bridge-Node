"""隔离的 Browscreen 包装进程，只监听本机并监视父进程 EOF。"""

import argparse
import asyncio
import json
import logging
import os
import socket
import sys
import threading
from importlib.metadata import version
from pathlib import Path

from runbridge_node.visual_protocol import supported_browscreen_version


def load_browscreen():
    """按支持范围延迟加载可选库，基础 Node 不导入该库。"""
    if not supported_browscreen_version(value=version(distribution_name="browscreen")):
        raise ValueError("不受支持的 Browscreen 版本")
    from browscreen.app import create_app
    from browscreen.models import Settings
    import uvicorn

    return create_app, Settings, uvicorn


async def serve(*, work_dir: Path) -> None:
    """先绑定随机回环端口，再交付就绪信息。

    :param work_dir: Node 为此采集实例创建的私有目录。
    """
    create_app, Settings, uvicorn = load_browscreen()
    logging.disable(level=logging.CRITICAL)
    with socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        settings = Settings(work_dir=work_dir, port=listener.getsockname()[1])
        app = create_app(settings=settings)
        server = uvicorn.Server(config=uvicorn.Config(app=app, host="127.0.0.1", port=settings.port,
                                                     workers=1, loop="asyncio", log_config=None, access_log=False))
        loop = asyncio.get_running_loop()

        def watch_parent():
            """使用原始管道和 daemon 线程，避免退出时等待阻塞读线程。"""
            try:
                while os.read(sys.stdin.fileno(), 1):
                    pass
                loop.call_soon_threadsafe(setattr, server, "should_exit", True)
            except (OSError, RuntimeError):
                pass

        threading.Thread(target=watch_parent, daemon=True).start()
        task = asyncio.create_task(coro=server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(delay=8):
                while not server.started:
                    if task.done():
                        await task
                        raise ValueError("采集服务没有启动")
                    await asyncio.sleep(delay=0.01)
            print(json.dumps({"type": "ready", "port": settings.port}), flush=True)
            await task
        finally:
            server.should_exit = True
            await task


def main() -> None:
    """只交付固定错误码，不输出调试端点或异常输入。"""
    parser = argparse.ArgumentParser(description="RunBridge 内部画面采集进程")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    try:
        if args.check:
            load_browscreen()
            return
        if args.work_dir is None:
            raise ValueError("缺少采集目录")
        asyncio.run(serve(work_dir=args.work_dir))
    except Exception:
        print(json.dumps({"type": "failed", "error_code": "VISUAL_WORKER_FAILED"}), flush=True)
        raise SystemExit(1) from None
    finally:
        if args.work_dir is not None:
            # 该目录只由 Node 创建；不递归删除不属于采集的内容。
            for name in (".cdp", ".mouse"):
                try:
                    (args.work_dir / name).unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                args.work_dir.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    main()
