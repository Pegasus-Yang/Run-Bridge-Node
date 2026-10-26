# 贡献指南

简体中文 · [English](CONTRIBUTING.en.md)

欢迎改进 RunBridge Node 的代码、文档与示例。项目由 [Pegasus-Yang（天马）](https://github.com/Pegasus-Yang)维护。

## 反馈问题与建议

通过本仓库的 [Issues](https://github.com/Pegasus-Yang/Run-Bridge-Node/issues)反馈。问题报告请包含：

- Node / Hub 版本、操作系统、Python 和浏览器版本。
- 浏览器模式（managed / borrowed）、最小复现步骤、预期结果与实际结果。
- 已隐藏秘密的配置、错误码及必要日志；执行问题可附原请求 ID。

请勿上传登记凭据、Node 身份、访问令牌、真实浏览器 Profile 或私有测试数据。Hub 的申请、认证、HTTP/MCP 和总览问题可提交到 [Hub 仓库](https://github.com/Pegasus-Yang/Run-Bridge-Hub/issues)。

## 提交修改

1. Fork 本仓库并创建工作分支。较大的行为或协议变更，先通过 Issue 说明目标、影响和兼容方式。
2. 阅读 [AGENTS.md](AGENTS.md) 与[本地开发与联调](doc/development/本地开发与联调.md)，使用 `uv` 和根目录 `.venv` 准备环境。
3. 只修改与目标有关的内容。缺陷修复提供能够复现问题的 pytest 用例；功能变更同步当前中英文使用文档与导航。
4. 按影响运行相关检查。在 Pull Request 中说明问题、最终行为、验证结果，以及尚未执行的验证。

真实浏览器测试需显式启用，使用测试创建的独立 Profile；borrowed 测试仅连接明确授权的实例。准备环境与清理要求见开发手册。

涉及方法、对象、协议或生命周期时，请核对 [Hub 实现与方法表](https://github.com/Pegasus-Yang/Run-Bridge-Hub)，并在 Pull Request 中关联需要配套的修改。

## 授权

提交到本项目的贡献按 [MIT License](LICENSE)提供。引入第三方代码或资源时，注明来源并保留其许可证和版权声明。
