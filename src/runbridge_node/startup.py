"""统一启动配置和可重复的首次登记流程。"""

import os
import secrets
import socket
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import Field, field_validator, model_validator

from runbridge_node.client import ClientError, NodeClient
from runbridge_node.config import NodeConfig, validate_hub_url
from runbridge_node.protocol import Model, RegistrationResult
from runbridge_node.runtime import PlaywrightConfig


class RunSettings(Model):
    """一个 Node 进程的启动设置，不保存生成的身份秘密。"""

    config_version: Literal[2] = 2
    hub_url: str | None = None
    name: str = Field(default_factory=socket.gethostname, min_length=1, max_length=128)
    identity_file: Path = Path(".runbridge/node.json")
    enrollment_token_file: Path | None = None
    tools: dict[str, PlaywrightConfig] = Field(default_factory=dict)

    @field_validator("hub_url")
    @classmethod
    def hub_address(cls, value: str | None) -> str | None:
        """规范可选 Hub 基址。

        :returns: 规范后的地址。
        """
        return validate_hub_url(value=value) if value is not None else None

    @model_validator(mode="after")
    def known_tools(self):
        """工具通过显式适配器注册，不接受远程模块名。

        :returns: 已检查的设置。
        """
        if set(self.tools) - {"playwright"}:
            raise ValueError("TOOL_UNSUPPORTED")
        return self

    @classmethod
    def load(cls, *, path: Path):
        """读取 YAML；本地相对路径以配置所在目录为准。

        :param path: YAML 启动文件。
        :returns: 已验证的设置。
        """
        try:
            values = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            raise ValueError("YAML 格式无效，输入内容已隐藏") from None
        if not isinstance(values, dict):
            raise ValueError("YAML 顶层必须是配置对象")
        base = path.resolve().parent
        for key, default in (("identity_file", ".runbridge/node.json"), ("enrollment_token_file", None)):
            value = values.get(key, default)
            if isinstance(value, str):
                values[key] = (base / value).resolve()
        if any(key in values for key in ("playwright", "chrome")):
            raise ValueError("旧浏览器配置需要迁移为 config_version: 2 与 tools.playwright")
        tools = values.get("tools", {})
        if not isinstance(tools, dict):
            raise ValueError("tools 必须是配置对象")
        browser = tools.get("playwright")
        if isinstance(browser, dict):
            cache = browser.get("browser_cache_directory")
            if isinstance(cache, str):
                browser["browser_cache_directory"] = (base / cache).resolve()
            options = browser.get("launch_options")
            if isinstance(options, dict):
                for key in ("artifacts_dir", "downloads_path", "executable_path", "traces_dir"):
                    if isinstance(options.get(key), str):
                        options[key] = str((base / options[key]).resolve())
        return cls.model_validate(values)


async def prepare_identity(*, settings: RunSettings, require_registration: bool = False) -> tuple[NodeConfig, RegistrationResult | None]:
    """复用持久身份，必要时先登记再交给常驻连接。

    :param settings: 本次 Node 的设置。
    :param require_registration: 独立 register 命令强制请求登记。
    :returns: 身份和本次登记结果；未请求登记时结果为空。
    """
    token = settings.enrollment_token_file.read_text(encoding="utf-8").strip() if settings.enrollment_token_file is not None else os.environ.get("RUNBRIDGE_ENROLLMENT_TOKEN")
    register = require_registration or settings.enrollment_token_file is not None or bool(token)
    if register and not token:
        raise ClientError("登记需要 enrollment_token_file 或 RUNBRIDGE_ENROLLMENT_TOKEN")
    if settings.identity_file.exists():
        identity = NodeConfig.load(path=settings.identity_file)
        if settings.hub_url is not None and identity.hub_url != settings.hub_url:
            raise ClientError("现有身份属于其他 Hub；请使用另一个身份文件")
    else:
        if settings.hub_url is None or not register:
            raise ClientError("首次启动需要 hub_url 和登记令牌；已有节点请检查 identity_file")
        identity = NodeConfig(hub_url=settings.hub_url, node_id=f"node_{uuid4().hex}", name=settings.name, node_token=secrets.token_urlsafe(48))
        identity.save(path=settings.identity_file)
    result = await NodeClient(config=identity).register(enrollment_token=token) if register else None
    return identity, result
