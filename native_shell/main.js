const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const http = require('http');
const path = require('path');

const APP_ID = 'com.pepertranslator.desktop';
const EXPECTED_BUILD = 'phase83-deterministic-lexical-fallback-v1';
const BACKEND_PORT = 8000;
const FRONTEND_PORT = 31337;
const EXPECTED_NATIVE_PROTOCOL = 2;
let mainWindow = null;
let backendProcess = null;
let frontendProcess = null;
let quitting = false;

app.setAppUserModelId(APP_ID);

function runtimeRoot() {
  if (app.isPackaged) return path.join(path.dirname(process.execPath), 'runtime');
  return path.resolve(__dirname, '..', 'runtime');
}

function log(message) {
  try {
    const root = path.join(process.env.LOCALAPPDATA || app.getPath('userData'), 'PeperTranslator', 'logs');
    fs.mkdirSync(root, { recursive: true });
    fs.appendFileSync(path.join(root, 'native-shell.log'), `${new Date().toISOString()} ${message}\n`, 'utf8');
  } catch (_) {}
}

function requestJson(url, timeoutMs = 1800) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        try { resolve(JSON.parse(body)); } catch (_) { resolve(null); }
      });
    });
    req.on('timeout', () => { req.destroy(); resolve(null); });
    req.on('error', () => resolve(null));
  });
}

function requestOk(url, timeoutMs = 1800) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on('timeout', () => { req.destroy(); resolve(false); });
    req.on('error', () => resolve(false));
  });
}

async function waitFor(check, attempts, delayMs) {
  for (let i = 0; i < attempts; i += 1) {
    if (await check()) return true;
    await new Promise((r) => setTimeout(r, delayMs));
  }
  return false;
}

function killTree(child) {
  if (!child || !child.pid) return;
  try {
    spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
  } catch (_) {}
}

async function ensureBackend(root) {
  const existing = await requestJson(`http://127.0.0.1:${BACKEND_PORT}/`);
  if (existing && existing.build === EXPECTED_BUILD && existing.native_protocol === EXPECTED_NATIVE_PROTOCOL) {
    log('Reusing verified Phase83 native-compatible backend.');
    return;
  }
  if (existing && existing.message === 'Paper Translator backend is running') {
    throw new Error(`An older PeperTranslator backend is still using port ${BACKEND_PORT}. Run RESET_NATIVE_PORTS.cmd once, then start PeperTranslator again.`);
  }
  if (existing) {
    throw new Error(`Port ${BACKEND_PORT} is already used by a different backend. Close the other service and try again.`);
  }

  const python = path.join(root, 'backend_env', 'Scripts', 'python.exe');
  if (!fs.existsSync(python)) throw new Error(`Backend runtime not found: ${python}`);

  const env = {
    ...process.env,
    TRANSLATION_MODEL: 'qwen2.5:14b',
    OLLAMA_MODEL: 'qwen2.5:14b',
    PYTHONUTF8: '1',
  };
  backendProcess = spawn(python, ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)], {
    cwd: root,
    env,
    windowsHide: true,
    stdio: 'ignore',
  });
  backendProcess.on('exit', (code) => log(`Backend exited: ${code}`));

  const ready = await waitFor(async () => {
    const data = await requestJson(`http://127.0.0.1:${BACKEND_PORT}/`);
    return Boolean(data && data.build === EXPECTED_BUILD && data.native_protocol === EXPECTED_NATIVE_PROTOCOL);
  }, 70, 500);
  if (!ready) throw new Error('Phase83 backend did not become ready. Check Ollama/Python and the native-shell log.');
}

async function ensureFrontend(root) {
  const server = path.join(root, 'frontend_server', 'server.js');
  if (!fs.existsSync(server)) throw new Error(`Frontend runtime not found: ${server}`);

  frontendProcess = spawn(process.execPath, [server], {
    cwd: path.dirname(server),
    windowsHide: true,
    stdio: 'ignore',
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: '1',
      NODE_ENV: 'production',
      HOSTNAME: '127.0.0.1',
      PORT: String(FRONTEND_PORT),
    },
  });
  frontendProcess.on('exit', (code) => log(`Frontend exited: ${code}`));

  const ready = await waitFor(() => requestOk(`http://127.0.0.1:${FRONTEND_PORT}/`), 70, 500);
  if (!ready) throw new Error('Frontend did not become ready. See the native-shell log.');
}

async function verifyRendererBackendBridge(win) {
  try {
    const result = await win.webContents.executeJavaScript(`
      fetch('http://127.0.0.1:${BACKEND_PORT}/', { cache: 'no-store' })
        .then(async (response) => ({ ok: response.ok, data: await response.json() }))
        .catch((error) => ({ ok: false, error: String(error) }))
    `, true);
    if (!result || !result.ok || !result.data || result.data.build !== EXPECTED_BUILD || result.data.native_protocol !== EXPECTED_NATIVE_PROTOCOL) {
      const detail = result && result.error ? result.error : JSON.stringify(result);
      throw new Error(`Frontend/backend bridge check failed: ${detail}`);
    }
    log('Renderer/backend bridge verified.');
  } catch (error) {
    throw new Error(`Native renderer cannot reach Phase83 backend: ${error && error.message ? error.message : error}`);
  }
}

function createWindow() {
  const icon = path.join(__dirname, 'assets', 'PeperTranslator.ico');
  mainWindow = new BrowserWindow({
    title: 'PeperTranslator',
    width: 1600,
    height: 980,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: '#09090b',
    show: false,
    autoHideMenuBar: true,
    icon,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      devTools: false,
    },
  });
  mainWindow.setMenuBarVisibility(false);
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(`http://127.0.0.1:${FRONTEND_PORT}`) || url.startsWith('http://127.0.0.1:8000')) {
      return { action: 'allow' };
    }
    shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(`http://127.0.0.1:${FRONTEND_PORT}`)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
  mainWindow.once('ready-to-show', () => mainWindow.show());
  return mainWindow;
}

async function boot() {
  const root = runtimeRoot();
  log(`Runtime root: ${root}`);
  const win = createWindow();
  await win.loadFile(path.join(__dirname, 'loading.html'));
  win.show();
  await ensureBackend(root);
  await ensureFrontend(root);
  await win.loadURL(`http://127.0.0.1:${FRONTEND_PORT}/`);
  await verifyRendererBackendBridge(win);
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    try {
      await boot();
    } catch (error) {
      log(`Startup error: ${error && error.stack ? error.stack : error}`);
      dialog.showErrorBox('PeperTranslator startup failed', String(error && error.message ? error.message : error));
      app.quit();
    }
  });
}

app.on('before-quit', () => {
  if (quitting) return;
  quitting = true;
  killTree(frontendProcess);
  killTree(backendProcess);
});

app.on('window-all-closed', () => app.quit());
