# Contributing

[简体中文](CONTRIBUTING.md) · English

Contributions to RunBridge Node code, documentation, and examples are welcome. Maintained by [Pegasus-Yang](https://github.com/Pegasus-Yang).

## Report an issue or propose a change

Use this repository's [Issues](https://github.com/Pegasus-Yang/Run-Bridge-Node/issues). Include Node and Hub versions, OS, Python and browser versions, mode (`managed` / `borrowed`), minimal steps, expected and actual results, and redacted errors. A request ID helps diagnose execution problems.

Keep enrollment credentials, Node identities, access tokens, real browser profiles, and private test data out of reports. Report Hub authorization, HTTP/MCP, claim, and dashboard problems in the [Hub repository](https://github.com/Pegasus-Yang/Run-Bridge-Hub/issues).

## Prepare a contribution

1. Fork the repository and create a branch. Discuss major behavior or protocol changes in an Issue, including scope and compatibility.
2. Use `uv` and the repository's root `.venv`. From the cloned repository:

```bash
uv sync --extra playwright --extra visual -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
.venv/bin/python -m pytest tests -q
```

3. Keep changes related to the goal. Add a pytest regression that reproduces a bug when fixing one, and update user documentation for behavior changes. Maintain both language versions and their links.
4. Explain the problem, resulting behavior, validation results, and any unperformed checks in the Pull Request.

Real browser tests require explicit opt-in and test-owned profiles. Borrowed tests connect only to explicitly authorized instances. Follow the [development manual (Chinese)](doc/development/本地开发与联调.md) for browser preparation and scoped cleanup.

Check the [Hub implementation](https://github.com/Pegasus-Yang/Run-Bridge-Hub) for method, object, protocol, or lifecycle changes and link any corresponding change. Repository rules are in [AGENTS.md (Chinese)](AGENTS.md); runtime guides are indexed in [English documentation](doc/README.en.md).

PyPI metadata, artifact selection, strict checks, and upload verification are covered in [release preparation](doc/development/PyPI发布准备.en.md).

GitHub Actions checks branch pushes and pull requests, and publishes validated distributions for release tags. See [CI and releases](doc/development/GitHubActions与Release.en.md) for scope and manual backfills.

## License

Contributions are provided under the [MIT License](LICENSE). Identify the source of third-party code or assets and retain their license and copyright notices.
