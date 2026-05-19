/**
 * Electron Main Process  –  V2
 * Handles IPC, file dialogs, and native OS integration.
 */

const { app, BrowserWindow, Menu, ipcMain, dialog, shell } = require('electron');
const path  = require('path');
const fs    = require('fs');
const http  = require('http');
const { pathToFileURL } = require('url');

let mainWindow;
const API_URL = 'http://127.0.0.1:8000';
const isDev   = process.env.NODE_ENV === 'development' || process.argv.includes('--dev');

// ── Window ─────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width:  1280,
    height: 860,
    minWidth:  900,
    minHeight: 600,
    backgroundColor: '#0a0f1e',
    titleBarStyle: 'hidden',
    frame: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
      plugins: true,
    },
    icon: path.join(__dirname, '../../public/icon.png'),
  });

  const startUrl = isDev
    ? 'http://localhost:3000'
    : pathToFileURL(path.join(__dirname, '../../build/index.html')).href;

  mainWindow.loadURL(startUrl);

  if (isDev) {
    mainWindow.webContents.openDevTools({ mode: 'right' });
  }

  mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
    console.log(`[Electron Console] [Level ${level}] ${message} (Source: ${sourceId}:${line})`);
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

app.whenReady().then(() => {
  createWindow();
  buildMenu();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
  if (!mainWindow) createWindow();
});

// ── Helper: fetch with node:http ───────────────────────────
function nodeFetch(url, options = {}) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const reqOptions = {
      hostname: urlObj.hostname,
      port:     urlObj.port || 80,
      path:     urlObj.pathname + urlObj.search,
      method:   options.method || 'GET',
      headers:  options.headers || {},
    };

    const req = http.request(reqOptions, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        const body = Buffer.concat(chunks);
        resolve({ status: res.statusCode, headers: res.headers, body });
      });
    });

    req.on('error', reject);
    if (options.body) req.write(options.body);
    req.end();
  });
}

// ── IPC: Window Controls ───────────────────────────────────
ipcMain.handle('win:minimize', () => {
  if (mainWindow) mainWindow.minimize();
});
ipcMain.handle('win:maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});
ipcMain.handle('win:close', () => {
  if (mainWindow) mainWindow.close();
});
ipcMain.handle('win:reload', () => {
  if (mainWindow) mainWindow.webContents.reload();
});
ipcMain.handle('win:restart', () => {
  app.relaunch();
  app.exit(0);
});
ipcMain.handle('win:confirm', async (event, options) => {
  const result = await dialog.showMessageBox(mainWindow, {
    type: 'question',
    buttons: options.buttons || ['OK', 'Cancel'],
    defaultId: 0,
    cancelId: 1,
    title: options.title || 'Onroku AI',
    message: options.message,
    detail: options.detail || '',
  });
  return result.response === 0;
});

// ── IPC: API ───────────────────────────────────────────────

ipcMain.handle('api:health', async () => {
  const r = await nodeFetch(`${API_URL}/health`);
  return JSON.parse(r.body.toString());
});

ipcMain.handle('api:hardware', async () => {
  const r = await nodeFetch(`${API_URL}/hardware`);
  return JSON.parse(r.body.toString());
});

ipcMain.handle('api:upload', async (event, filePath, language = 'ja', model = 'auto', speakerCount = 'auto', chunkSeconds = 'auto', diarizationMode = 'accurate', performanceMode = 'auto', speakerRange = 'normal') => {
  // Build multipart/form-data manually
  const boundary = `----FormBoundary${Date.now()}`;
  const filename  = path.basename(filePath);
  const fileData  = fs.readFileSync(filePath);

  const header = Buffer.from(
    `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${filename}"\r\nContent-Type: application/octet-stream\r\n\r\n`
  );
  const footer = Buffer.from(`\r\n--${boundary}--\r\n`);
  const body   = Buffer.concat([header, fileData, footer]);

  const queryParams = new URLSearchParams({
    language,
    model,
    diarization_mode: diarizationMode,
    performance_mode: performanceMode,
    speaker_range: speakerRange
  });
  if (speakerCount && speakerCount !== 'auto') {
    queryParams.append('speaker_count', speakerCount);
  }
  if (chunkSeconds && chunkSeconds !== 'auto') {
    queryParams.append('chunk_seconds', chunkSeconds);
  }

  const r = await nodeFetch(`${API_URL}/upload?${queryParams.toString()}`, {
    method: 'POST',
    headers: {
      'Content-Type': `multipart/form-data; boundary=${boundary}`,
      'Content-Length': body.length,
    },
    body,
  });

  if (r.status !== 200) throw new Error(`Upload failed: HTTP ${r.status}`);
  return JSON.parse(r.body.toString());
});

ipcMain.handle('api:get-job', async (event, jobId) => {
  const r = await nodeFetch(`${API_URL}/job/${jobId}`);
  return JSON.parse(r.body.toString());
});

ipcMain.handle('api:list-jobs', async (event, skip = 0, limit = 30) => {
  const r = await nodeFetch(`${API_URL}/jobs?skip=${skip}&limit=${limit}`);
  return JSON.parse(r.body.toString());
});

ipcMain.handle('api:export', async (event, jobId, format) => {
  const r = await nodeFetch(`${API_URL}/export/${jobId}?format=${format}`, { method: 'POST' });
  if (r.status !== 200) throw new Error(`Export failed: HTTP ${r.status}`);
  return r.body; // Returns raw Buffer for saving
});

ipcMain.handle('api:cancel-job', async (event, jobId) => {
  const r = await nodeFetch(`${API_URL}/cancel/${jobId}`, { method: 'POST' });
  return JSON.parse(r.body.toString());
});

ipcMain.handle('api:pause-job', async (event, jobId) => {
  const r = await nodeFetch(`${API_URL}/pause/${jobId}`, { method: 'POST' });
  return JSON.parse(r.body.toString());
});

ipcMain.handle('api:resume-job', async (event, jobId) => {
  const r = await nodeFetch(`${API_URL}/resume/${jobId}`, { method: 'POST' });
  return JSON.parse(r.body.toString());
});

ipcMain.handle('api:delete-job', async (event, jobId) => {
  const r = await nodeFetch(`${API_URL}/job/${jobId}`, { method: 'DELETE' });
  return JSON.parse(r.body.toString());
});

function scanDirectory(dirPath) {
  let results = [];
  try {
    const list = fs.readdirSync(dirPath);
    const supported = ['.mp3','.wav','.flac','.m4a','.ogg','.aac','.wma','.opus','.mp4','.mov','.mkv','.avi','.flv','.webm'];
    list.forEach((file) => {
      const fullPath = path.join(dirPath, file);
      try {
        const stat = fs.statSync(fullPath);
        if (stat && stat.isDirectory()) {
          results = results.concat(scanDirectory(fullPath));
        } else {
          const ext = path.extname(file).toLowerCase();
          if (supported.includes(ext)) {
            results.push(fullPath);
          }
        }
      } catch (e) {
        // Skip inaccessible files/folders gracefully
      }
    });
  } catch (e) {
    // Skip read errors gracefully
  }
  return results;
}

ipcMain.handle('file:open-directory-dialog', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'フォルダを選択 / Select Folder',
    properties: ['openDirectory'],
  });
  if (result.canceled || result.filePaths.length === 0) return null;
  const dirPath = result.filePaths[0];
  try {
    return scanDirectory(dirPath);
  } catch (err) {
    console.error(err);
    return [];
  }
});

// ── IPC: File dialogs ──────────────────────────────────────

ipcMain.handle('file:select-directory-path', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: '保存先フォルダを選択 / Select Save Folder',
    properties: ['openDirectory'],
  });
  return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0];
});

ipcMain.handle('file:open-dialog', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: '音声ファイルを選択 / Select Audio Files',
    properties: ['openFile', 'multiSelections'],
    filters: [
      { name: '音声ファイル / Audio', extensions: ['mp3','wav','flac','m4a','ogg','aac','wma','opus'] },
      { name: '動画ファイル / Video',  extensions: ['mp4','mov','mkv','avi','flv','webm'] },
      { name: 'すべてのファイル / All', extensions: ['*'] },
    ],
  });
  return result.canceled ? null : result.filePaths;
});

ipcMain.handle('file:save-dialog', async (event, filename) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath: filename,
    filters: [{ name: 'All Files', extensions: ['*'] }],
  });
  return result.canceled ? null : result.filePath;
});

ipcMain.handle('file:write', async (event, filePath, data) => {
  fs.writeFileSync(filePath, Buffer.from(data));
  return true;
});

ipcMain.handle('shell:open', async (event, filePath) => {
  await shell.openPath(filePath);
});

ipcMain.handle('shell:show-item', async (event, filePath) => {
  shell.showItemInFolder(filePath);
});

// ── Application menu ───────────────────────────────────────
function buildMenu() {
  const template = [
    {
      label: 'File / ファイル',
      submenu: [
        { label: 'Exit / 終了', accelerator: 'Ctrl+Q', click: () => app.quit() },
      ],
    },
    {
      label: 'Edit / 編集',
      submenu: [
        { role: 'undo' }, { role: 'redo' }, { type: 'separator' },
        { role: 'cut'  }, { role: 'copy'  }, { role: 'paste' },
      ],
    },
    {
      label: 'Help / ヘルプ',
      submenu: [
        {
          label: 'About / このアプリについて',
          click: () => dialog.showMessageBox(mainWindow, {
            type: 'info',
            title: 'Onroku AI',
            message: 'Onroku AI V6.0',
            detail: 'Offline Multi-Speaker Transcription V6.0\nPowered by faster-whisper & Pyannote',
          }),
        },
        {
          label: 'Open Backend Logs',
          click: () => shell.openPath(path.join(__dirname, '../../logs')),
        },
      ],
    },
  ];

  if (isDev) {
    template.push({
      label: 'Dev',
      submenu: [
        { role: 'reload' },
        { role: 'toggleDevTools' },
      ],
    });
  }

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}
