"""节点身份与对接许可的私有文件。"""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from pydantic import AwareDatetime, Field, SecretStr, field_validator

from runbridge_node.protocol import Identifier, Model


def validate_hub_url(*, value: str) -> str:
    """验证无秘密的 HTTP 服务基址。

    :param value: Hub 基址。
    :returns: 移除末尾斜线的基址。
    """
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Hub 地址须为不含用户信息、查询或片段的 HTTP/HTTPS 基址")
    return value.rstrip("/")


class NodeConfig(Model):
    """保存稳定节点 ID 和专属身份凭据。"""

    config_version: int = Field(default=1, ge=1, le=1)
    hub_url: str
    node_id: Identifier
    name: str = Field(min_length=1, max_length=128)
    node_token: SecretStr = Field(min_length=32, max_length=256)

    @field_validator("hub_url")
    @classmethod
    def hub_address(cls, value: str) -> str:
        """验证 Hub 地址。

        :returns: 规范基址。
        """
        return validate_hub_url(value=value)

    @classmethod
    def load(cls, *, path: Path):
        """读取已有身份。

        :param path: 配置路径。
        :returns: 节点配置。
        """
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, *, path: Path) -> None:
        """首次保存身份，拒绝覆盖已存在文件。

        :param path: 配置路径。
        """
        values = self.model_dump(mode="json")
        values["node_token"] = self.node_token.get_secret_value()
        write_private_json(path=path, values=values)


class AccessConfig(Model):
    """调用方独立使用的对接许可，不含节点身份秘密。"""

    hub_url: str
    node_id: Identifier
    grant_id: Identifier
    access_token: SecretStr
    expires_at: AwareDatetime | None = None

    @classmethod
    def load(cls, *, path: Path):
        """读取 Hub 导出的五字段 JSON 或 YAML，不猜测设备身份。"""
        try:
            values = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            raise ValueError("访问文件格式无效，输入内容已隐藏") from None
        return cls.model_validate(values)

    @field_validator("hub_url")
    @classmethod
    def hub_address(cls, value: str) -> str:
        """验证 Hub 地址。

        :returns: 规范基址。
        """
        return validate_hub_url(value=value)

    def save(self, *, path: Path) -> None:
        """保存一次性交付的对接码。

        :param path: 私有输出文件。
        """
        values = self.model_dump(mode="json")
        values["access_token"] = self.access_token.get_secret_value()
        write_private_json(path=path, values=values)


def write_private_json(*, path: Path, values: dict) -> None:
    """用排他创建和私有权限写入凭据文件。

    :param path: 文件路径。
    :param values: 写入内容；调用方不得打印。
    """
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(json.dumps(values, ensure_ascii=False, indent=2) + "\n")
        output.flush()
        os.fsync(output.fileno())
