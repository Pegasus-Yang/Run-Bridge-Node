"""每会话的 Python 工具进程；只接收结构化动作。"""

import asyncio
import json
import sys
from collections import OrderedDict
from time import monotonic

from pydantic import ValidationError

from runbridge_node.ipc import encode, read_blocking
from runbridge_node.tool_contract import Execute, fingerprint, validate_call
from runbridge_node.tools import ToolError, create_tool


async def run() -> None:
    first = await asyncio.to_thread(read_blocking, stream=sys.stdin.buffer)
    if first is None or first.get("type") != "open":
        return
    session_id = first["session_id"]
    generation = first["connection_generation"]
    lock = asyncio.Lock()
    event_seq = 0

    async def emit(value: dict, *, optional: bool = False):
        nonlocal event_seq
        if optional and lock.locked():
            return
        value = {
            "protocol_version": 2,
            "session_id": session_id,
            "connection_generation": generation,
            **value,
        }
        if value["type"] == "event":
            event_seq += 1
            value["event_seq"] = event_seq
        packet = encode(value=value)
        async with lock:

            def write():
                sys.stdout.buffer.write(packet)
                sys.stdout.buffer.flush()

            await asyncio.to_thread(write)

    tool = create_tool(
        name=first["tool"], config=first["config"], session_id=session_id, emit=emit
    )
    queue = asyncio.Queue(maxsize=16)
    seen = {}
    results = OrderedDict()
    cache_bytes = 0
    consumer = None
    operation_done = asyncio.Event()
    operation_done.set()

    async def complete(request, *, status, outcome, result=None, code=None, stage=None):
        nonlocal cache_bytes
        value = {
            "type": "result",
            "request_id": request.request_id,
            "status": status,
            "execution_outcome": outcome,
            "result": result,
            "error": {
                "code": code,
                "message": "工具操作未完成，请根据错误码和实际页面状态检查",
                "stage": stage or ("execute" if tool.entered else "validate"),
                "retryable": False,
            }
            if code
            else None,
        }
        size = len(json.dumps(value).encode())
        results[request.request_id] = (value, size)
        cache_bytes += size
        while len(results) > 128 or cache_bytes > 64 * 1024 * 1024:
            _, (_, removed) = results.popitem(last=False)
            cache_bytes -= removed
        seen[request.request_id] = (seen[request.request_id][0], status)
        await emit(value)

    async def consume():
        while True:
            request, received = await queue.get()
            operation_done.clear()
            try:
                if tool.closing:
                    tool.entered = False
                    await complete(
                        request,
                        status="FAILED",
                        outcome="NOT_STARTED",
                        code="SESSION_NOT_ACTIVE",
                    )
                    continue
                remaining = request.remaining_ms - int((monotonic() - received) * 1000)
                if remaining <= 0:
                    tool.entered = False
                    await complete(
                        request,
                        status="FAILED",
                        outcome="NOT_STARTED",
                        code="ACTION_TIMEOUT",
                    )
                    continue
                request = request.model_copy(update={"remaining_ms": remaining})
                seen[request.request_id] = (seen[request.request_id][0], "RUNNING")
                await emit(
                    {"type": "command_started", "request_id": request.request_id}
                )
                result = await tool.execute(request=request)
                await complete(
                    request, status="SUCCEEDED", outcome="COMPLETED", result=result
                )
            except ToolError as error:
                await complete(
                    request, status="FAILED", outcome=error.outcome, code=error.code
                )
            except ValidationError, TypeError, ValueError:
                await complete(
                    request,
                    status="FAILED",
                    outcome="NOT_STARTED",
                    code="INVALID_PARAMS",
                )
            finally:
                queue.task_done()
                operation_done.set()

    try:
        metadata = await tool.open()
        await emit({"type": "ready", **metadata})
        tool.start_background()
        consumer = asyncio.create_task(consume())
        while True:
            value = await asyncio.to_thread(read_blocking, stream=sys.stdin.buffer)
            if value is None or value.get("type") == "close":
                break
            if value.get("type") == "visual_select":
                await tool.select_visual(target_id=value["target_id"])
                continue
            request = Execute.model_validate(value)
            if (
                request.session_id != session_id
                or request.connection_generation != generation
                or request.tool != first["tool"]
                or request.tool_api_version != 1
            ):
                raise ValueError("INVALID_SESSION_COMMAND")
            validate_call(request=request, tool=first["tool"])
            digest = fingerprint(request=request)
            previous = seen.get(request.request_id)
            if previous is not None:
                if previous[0] != digest:
                    await emit(
                        {
                            "type": "result",
                            "request_id": request.request_id,
                            "status": "FAILED",
                            "execution_outcome": "NOT_STARTED",
                            "result": None,
                            "error": {
                                "code": "REQUEST_ID_CONFLICT",
                                "stage": "validate",
                                "retryable": False,
                            },
                        }
                    )
                elif request.request_id in results:
                    await emit(results[request.request_id][0])
                else:
                    await emit(
                        {
                            "type": "command_ack",
                            "request_id": request.request_id,
                            "state": previous[1],
                        }
                    )
                continue
            if len(seen) >= 10000:
                raise ValueError("REQUEST_LIMIT")
            seen[request.request_id] = (digest, "ACCEPTED")
            if queue.full():
                await complete(
                    request,
                    status="FAILED",
                    outcome="NOT_STARTED",
                    code="RESOURCE_BUSY",
                    stage="queue",
                )
                continue
            queue.put_nowait((request, monotonic()))
            await emit(
                {
                    "type": "command_ack",
                    "request_id": request.request_id,
                    "state": "ACCEPTED",
                }
            )
    except ValueError, ValidationError, ImportError:
        await emit({"type": "failed", "code": "TOOL_INITIALIZATION_FAILED"})
    finally:
        await tool.close()
        if consumer is not None:
            for _ in range(queue.qsize()):
                request, _ = queue.get_nowait()
                await complete(
                    request,
                    status="FAILED",
                    outcome="NOT_STARTED",
                    code="SESSION_NOT_ACTIVE",
                )
                queue.task_done()
            await asyncio.wait_for(operation_done.wait(), timeout=2)
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)
        await emit({"type": "closed", "cleanup": "COMPLETE"})


if __name__ == "__main__":
    asyncio.run(run())
