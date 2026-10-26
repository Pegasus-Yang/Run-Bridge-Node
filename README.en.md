# RunBridge Node

**Make a local browser available to remote programs and agents.**

[简体中文](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/README.md) · English · [Quick start](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/README.en.md#quick-start) · [Documentation](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/README.en.md) · [Changelog (Chinese)](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/project/%E7%89%88%E6%9C%AC%E5%8F%91%E5%B8%83%E8%AE%B0%E5%BD%95.md) · [Issues](https://github.com/Pegasus-Yang/Run-Bridge-Node/issues)

[![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white)](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/pyproject.toml) [![MIT](https://img.shields.io/badge/License-MIT-16a34a?style=flat-square)](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/LICENSE)

RunBridge Node is the browser execution component of RunBridge. It runs on the browser device, connects to [RunBridge Hub](https://github.com/Pegasus-Yang/Run-Bridge-Hub/blob/main/README.en.md), executes Playwright operations in an independent Python worker, and sends results and page frames back to Hub.

Use it to provide an isolated browser test environment, or to reuse an existing Chrome instance's pages and login state with its owner's authorization. Programs and agents access the device through Hub's HTTP / MCP interface; Node manages browser processes, endpoints, and page objects locally.

## Highlights

| Capability | What you can do |
| --- | --- |
| Managed browser sessions | Launch Chromium for a session and clean up its processes and temporary profile afterward |
| Existing Chrome reuse | Connect to an authorized local instance and retain its original pages and login state when disconnecting |
| One YAML file | Configure Hub, identity, and browser options; automatically enroll, probe, and connect on first startup |
| Central lease allocation | Let Hub manage claims, renewals, and release while Node handles capabilities and execution |
| Multiple instances per device | Provide separate Nodes with independent configurations, identities, and browser resources |
| Frames and cleanup status | Observe the actual page, report cleanup, and quarantine resources when cleanup cannot be confirmed |

## How it works and which mode to choose

![RunBridge Node architecture](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/architecture/assets/node-overview.en.svg?raw=true)

| Choice | managed: isolated browser | borrowed: existing Chrome |
| --- | --- | --- |
| Typical use | Automated tests, independent tasks, agent MCP | Existing login state or a specific browser environment |
| Browser source | Chromium launched by Node for the session | Local Chrome instance explicitly authorized by its owner |
| Session end | Remove this session's browser and temporary profile | Disconnect; retain original pages and login state |
| Page streaming | Capture the managed page directly | Install the optional `visual` extra when needed |
| Client entry | Hub HTTP / MCP | Hub HTTP |
| Guide | [Managed Chromium](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/user-guide/Playwright%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.en.md) | [Existing Chrome](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/user-guide/Chrome%E5%A4%8D%E7%94%A8%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.en.md) |

Inspect online status, occupancy, and capabilities in the [Hub dashboard](https://github.com/Pegasus-Yang/Run-Bridge-Hub/blob/main/doc/user-guide/节点总览.en.md). Managed mode is headless by default; subscribe to page frames through Hub. Node does not have a separate web management UI.

## Quick start

### Install from PyPI after this version is published

Prepare Python 3.14, uv, and Hub enrollment material as described below. Until upload, use the source route. With this installation, continue at step 2.

```bash
mkdir -p ~/runbridge-node
cd ~/runbridge-node
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python "runbridge-node[playwright]==0.8.2" -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
.venv/bin/python -m playwright install chromium
```

### 1. Install Node and prepare Chromium

On the **Node device**, prepare Git, Python **3.14.x**, and [uv](https://docs.astral.sh/uv/getting-started/installation/). First obtain a reachable Hub base URL and the original `enrollment.token` from the [Hub deployer](https://github.com/Pegasus-Yang/Run-Bridge-Hub/blob/main/README.en.md#quick-start). Save the token file to `~/Downloads/`.

These commands use a macOS / Linux shell and install managed Chromium support:

```bash
git clone https://github.com/Pegasus-Yang/Run-Bridge-Node.git
cd Run-Bridge-Node
uv sync --locked --no-dev --extra playwright -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
.venv/bin/python -m playwright install chromium
```

`uv` creates `.venv` at the repository root. Linux also needs the browser's system libraries; see the [Playwright browser guide](https://playwright.dev/python/docs/browsers). For installation from a wheel in a separate directory, see [deployment](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/deployment/%E9%83%A8%E7%BD%B2%E4%B8%8E%E8%BF%90%E8%A1%8C.en.md).

### 2. Save enrollment material and configuration

```bash
umask 077
mkdir -p .runbridge
cp -n ~/Downloads/enrollment.token .runbridge/enrollment.token
chmod 600 .runbridge/enrollment.token
```

Create `node.yaml` in the current installation directory, replacing `hub_url` with the actual Hub base URL:

```yaml
hub_url: http://hub.example:8787
enrollment_token_file: .runbridge/enrollment.token
tools:
  playwright: {}
```

This uses managed, headless Chromium, resource ID `chromium`, and identity file `.runbridge/node.json`. Relative paths resolve from the **YAML file's directory**.

### 3. Connect and hand off the resource

```bash
.venv/bin/runbridge-node run --settings node.yaml
```

Leave the terminal running. First startup enrolls, probes the browser, and connects; later starts reuse the identity. A separate `register` command is unnecessary.

Give the logged `node_id`, resource ID, and mode to the Hub deployer or client. Confirm **ONLINE**, fresh capabilities, and resource **READY / FREE** in Hub's dashboard. Follow the [Hub client guide](https://github.com/Pegasus-Yang/Run-Bridge-Hub/blob/main/doc/user-guide/调用方对接与使用.en.md) to claim Node, operate the page, close the session, and return Node. First startup needs neither a client access file nor Hub's claim credential in the Node process.

## Supported scope

- Current Node: **0.8.2**, paired with Hub **0.9.3**. Python **3.14.x** and matching Python Playwright are required. No separate Node.js/npm deployment or Playwright BrowserServer is needed.
- **33 project methods** are explicitly implemented; see the [Hub method reference](https://github.com/Pegasus-Yang/Run-Bridge-Hub/blob/main/doc/reference/Playwright方法表.en.md). Hub provides HTTP / MCP; Node performs local execution.
- A Node browser resource accepts one active session at a time. Use independent Node instances for concurrent tasks on the same machine.
- Borrowed authorization covers the entire browser instance. Completed page operations persist; releasing resources does not undo business changes.
- Browser sessions and Node leases are released separately. Return Node at batch end; a maintainer reviews unknown cleanup.
- Some CLI messages and Hub dashboard labels remain Chinese. Browser locale defaults are unchanged by the English documentation.

## Documentation and help

| Start here | Contents |
| --- | --- |
| [Documentation index](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/README.en.md) | Reading paths for device maintainers, client handoff, and troubleshooting |
| [Quick start](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/user-guide/%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.en.md) · [Deployment](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/deployment/%E9%83%A8%E7%BD%B2%E4%B8%8E%E8%BF%90%E8%A1%8C.en.md) | Installation, enrollment, connection, handoff, restarts, and long-term operation |
| [Parameters](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/reference/%E5%8F%82%E6%95%B0%E8%AF%A6%E8%A7%A3.en.md) · [Annotated YAML](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/reference/examples/Node%E5%90%AF%E5%8A%A8%E9%85%8D%E7%BD%AE.en.yaml) | CLI, defaults, paths, and browser options |
| [Managed Chromium](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/user-guide/Playwright%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.en.md) · [Existing Chrome](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/user-guide/Chrome%E5%A4%8D%E7%94%A8%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.en.md) | New browsers or an existing login environment |
| [Multiple Nodes](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/deployment/%E5%90%8C%E6%9C%BA%E8%BF%90%E8%A1%8C%E5%A4%9A%E4%B8%AANode.en.md) | Independent identities and concurrent tasks |
| [Page capture](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/user-guide/%E6%B5%8F%E8%A7%88%E5%99%A8%E7%94%BB%E9%9D%A2%E9%87%87%E9%9B%86.en.md) · [MCP preparation](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/user-guide/MCP%E5%AF%B9%E6%8E%A5%E5%87%86%E5%A4%87.en.md) | Frame support and agent resources |
| [Browser credentials and test data](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/deployment/%E6%B5%8F%E8%A7%88%E5%99%A8%E5%87%AD%E6%8D%AE%E4%B8%8E%E6%B5%8B%E8%AF%95%E6%95%B0%E6%8D%AE.en.md) · [Operations](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/doc/deployment/%E8%BF%90%E8%A1%8C%E4%B8%8E%E6%8E%92%E9%9A%9C.en.md) | Credential prompts, private data, disconnections, cleanup, and upgrades |

## Development and contributions

Use [Issues](https://github.com/Pegasus-Yang/Run-Bridge-Node/issues) or submit a Pull Request. Include both component versions, OS, browser version and mode, reproduction steps, and redacted errors.

Development uses the root `.venv`. The [contribution guide](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/CONTRIBUTING.en.md) covers setup and validation and links to the detailed development manual in Chinese. Maintained by [Pegasus-Yang](https://github.com/Pegasus-Yang).

## License

This project uses the [MIT License](https://github.com/Pegasus-Yang/Run-Bridge-Node/blob/main/LICENSE). Third-party dependencies retain their respective licenses.
