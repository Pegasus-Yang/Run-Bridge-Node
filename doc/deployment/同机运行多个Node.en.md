# Multiple Nodes on one machine

[简体中文](同机运行多个Node.md) · English

Each Node **0.8.2** process provides one configured Playwright resource. Multiple processes can run on the same device, but every instance needs a distinct identity. Sharing identity makes Hub treat a new connection as a reconnect and replace the old one.

The simplest arrangement is one deployment directory and `.venv` per instance, installed using [deployment](部署与运行.en.md), with separate YAML. A shared installed CLI can also start multiple YAML files by absolute path; upgrading that environment affects all of them, so stop all affected instances first.

```text
~/runbridge-node-a/node.yaml -> .runbridge/node.json (identity A)
~/runbridge-node-b/node.yaml -> .runbridge/node.json (identity B)
```

Relative identity paths resolve from each YAML directory, so the two files differ. Set names such as `office-a` / `office-b`. Both may use resource ID `chromium` because `node_id + resource_id` identifies a resource.

```bash
# Use separate terminals; both directories must already be prepared.
cd ~/runbridge-node-a
.venv/bin/runbridge-node run --settings node.yaml
```

Start the second from directory b. Hand off two distinct Node IDs; clients claim each Node independently. A read-only browser installation cache can be shared. Managed sessions have independent workers, short temporary directories, and profiles; identities, activity records, and browser objects are not shared.

Borrowed instances should authorize different Chrome/profile instances. Two Nodes pointing to the same Chrome can modify the same pages; that is not two isolated resources, and RunBridge does not guarantee page exclusivity across them.

Stop only the intended instance normally. One Node resource accepts one active session at a time; independent instances provide same-machine task concurrency.
