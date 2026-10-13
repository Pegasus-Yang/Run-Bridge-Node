// 使用公开 launchServer API；Python 负责身份、资源和隧道管理。
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { createInterface } from 'node:readline';

const runtime = process.argv[2];
const requireRuntime = createRequire(join(runtime, 'package.json'));
let server;
let closing = false;
let resolveFinished;
const finished = new Promise(resolve => { resolveFinished = resolve; });
const lines = createInterface({ input: process.stdin });

const write = value => process.stdout.write(`${JSON.stringify(value)}\n`);
const close = async () => {
  closing = true;
  if (!server) return;
  try {
    await server.close();
    write({ type: 'closed', cleanup: 'COMPLETE' });
  } catch {
    write({ type: 'closed', cleanup: 'UNKNOWN' });
    process.exitCode = 1;
  }
  resolveFinished();
};
lines.once('close', close);
process.once('SIGTERM', close);
process.once('SIGINT', close);

try {
  const options = await new Promise(resolve => lines.once('line', line => resolve(JSON.parse(line))));
  const { chromium } = requireRuntime('playwright');
  const version = requireRuntime('playwright/package.json').version;
  server = await chromium.launchServer({ timeout: 20000, ...options, host: '127.0.0.1', port: 0, handleSIGINT: false, handleSIGTERM: false, handleSIGHUP: false });
  server.once('close', () => { if (!closing) close(); });
  // 使用本次服务的专用探测页，确认公开 CDP 截图可用；不观察其他客户端的页。
  let managedVisual = false;
  let probe;
  try {
    probe = await chromium.connect(server.wsEndpoint(), { timeout: 5000 });
    const context = await probe.newContext();
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    const screenshot = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    managedVisual = Buffer.from(screenshot.data, 'base64').subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
    await cdp.detach();
    await context.close();
  } catch {
    managedVisual = false;
  } finally {
    if (probe) await probe.close().catch(() => {});
  }
  write({ type: 'ready', version, node_version: process.version, endpoint: server.wsEndpoint(), browser_pid: server.process().pid, managed_visual: managedVisual });
  if (closing) await close();
  await finished;
} catch {
  write({ type: 'failed', code: 'PLAYWRIGHT_START_FAILED' });
  process.exitCode = 1;
  await close();
} finally {
  lines.close();
}
