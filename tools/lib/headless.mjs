/* Headless Chrome over the built site, for the checks that need a real browser (#53).
 *
 * serve() answers from public/ the way the Workers asset server does, on a free
 * localhost port. browser() launches Chrome and drives one tab over the DevTools
 * protocol with Node's built-in WebSocket; no dependencies. Map tiles and the
 * analytics beacon are blocked, so a run requests nothing it does not need (Leaflet
 * still comes from cdnjs, as it does on the site).
 *
 * Chrome is found at $CHROME, else the usual macOS and Linux paths.
 */
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { readFileSync, existsSync, statSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, join, extname } from 'node:path';

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const PUBLIC = join(ROOT, 'public');

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.xml': 'application/xml', '.txt': 'text/plain',
};

const isFile = p => existsSync(p) && statSync(p).isFile();

export function serve() {
  const server = createServer((req, res) => {
    const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    const f = join(PUBLIC, path);
    const file = !f.startsWith(PUBLIC) ? null
      : path.endsWith('/') ? (isFile(join(f, 'index.html')) ? join(f, 'index.html') : null)
      : [f, f + '.html', join(f, 'index.html')].find(isFile);
    if (!file) { res.writeHead(404, { 'Content-Type': TYPES['.html'] }); return res.end(readFileSync(join(PUBLIC, '404.html'))); }
    res.writeHead(200, { 'Content-Type': TYPES[extname(file)] || 'application/octet-stream' });
    res.end(readFileSync(file));
  });
  return new Promise(ok => server.listen(0, '127.0.0.1', () =>
    ok({ origin: `http://127.0.0.1:${server.address().port}`, close: () => server.close() })));
}

function chromePath() {
  const tries = [process.env.CHROME, '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
  const found = tries.find(p => p && existsSync(p));
  if (!found) throw new Error('Chrome not found; set $CHROME to its binary');
  return found;
}

export async function browser() {
  const profile = mkdtempSync(join(tmpdir(), 'mzh-chrome-'));
  const args = ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--window-size=1280,900'];
  if (process.env.CI) args.push('--no-sandbox');
  const proc = spawn(chromePath(), [...args, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  const wsUrl = await new Promise((ok, fail) => {
    let err = '';
    const t = setTimeout(() => fail(new Error('Chrome did not start:\n' + err)), 20000);
    proc.stderr.on('data', d => {
      err += d;
      const m = err.match(/DevTools listening on (ws:\/\/\S+)/);
      if (m) { clearTimeout(t); ok(m[1]); }
    });
  });

  // One page target; talk to it directly.
  const port = new URL(wsUrl).port;
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const ws = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail; });

  let seq = 0;
  const pending = new Map(), listeners = [], errors = [];
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) {
      const { ok, fail } = pending.get(m.id); pending.delete(m.id);
      m.error ? fail(new Error(m.error.message)) : ok(m.result);
    } else if (m.method) listeners.forEach(l => l(m));
  };
  const send = (method, params = {}) => new Promise((ok, fail) => {
    const id = ++seq; pending.set(id, { ok, fail }); ws.send(JSON.stringify({ id, method, params }));
  });
  listeners.push(m => {
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  });

  await send('Page.enable');
  await send('Runtime.enable');
  await send('Network.enable');
  await send('Network.setBlockedURLs', { urls: ['*basemap.nationalmap.gov*', '*static.cloudflareinsights.com*'] });

  // Evaluate an expression in the page; promises are awaited, the value comes back as JSON.
  async function evaluate(expression) {
    const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  }

  async function waitFor(expression, what, ms = 15000) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      if (await evaluate(`!!(${expression})`).catch(() => false)) return;
      await new Promise(r => setTimeout(r, 100));
    }
    throw new Error(`timed out waiting for ${what}`);
  }

  async function goto(url) {
    const loaded = new Promise(ok => listeners.push(function l(m) {
      if (m.method === 'Page.loadEventFired') { listeners.splice(listeners.indexOf(l), 1); ok(); }
    }));
    await send('Page.navigate', { url });
    await loaded;
  }

  async function close() {
    ws.close();
    if (proc.exitCode === null) { const gone = new Promise(r => proc.once('exit', r)); proc.kill(); await gone; }
    // Chrome's helper processes can still be writing the profile for a moment after the
    // browser exits. The profile is a temp dir, so tidying it must never fail a check.
    try { rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 }); } catch {}
  }

  return { evaluate, waitFor, goto, close, errors };
}
