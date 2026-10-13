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
  write({ type: 'ready', version, node_version: process.version, endpoint: server.wsEndpoint(), browser_pid: server.process().pid });
  if (closing) await close();
  await finished;
} catch {
  write({ type: 'failed', code: 'PLAYWRIGHT_START_FAILED' });
  process.exitCode = 1;
  await close();
} finally {
  lines.close();
}
