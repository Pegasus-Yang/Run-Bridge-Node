"""本节点内显式注册的工具适配器，不从远端加载代码。"""


class ToolError(Exception):
    """适配器对通用 worker 暴露的错误，不依赖具体工具库。"""

    def __init__(self, *, code: str, outcome: str = "NOT_STARTED"):
        self.code = code
        self.outcome = outcome
        super().__init__(code)


def create_tool(*, name: str, **kwargs):
    """创建已经安装并声明的本地工具。

    :returns: 工具会话适配器。
    """
    if name == "playwright":
        from runbridge_node.tools.playwright import PlaywrightTool

        return PlaywrightTool(**kwargs)
    raise ValueError("TOOL_UNSUPPORTED")
