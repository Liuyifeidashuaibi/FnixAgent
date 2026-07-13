/**
 * Electron 主进程入口
 *
 * 职责:
 *   1. 创建 BrowserWindow 并加载渲染进程
 *   2. 注册 IPC 处理器(文件操作 / Agent 调用 / safeStorage)
 *   3. 通过 HTTP 调用后端 API(/api/v1/health 等)
 *   4. 严格沙箱:渲染进程无法直接 require Node 模块
 *   5. Phase 3.0:注册 officeagent:// 自定义协议,处理 OAuth 回调
 *   6. Phase 3.1:本地文件系统 IPC(打开文件夹 / 读写文件 / 文件树)
 */
import { app, BrowserWindow, dialog, ipcMain, safeStorage, shell } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { initAutoUpdater } from './updater';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// 后端 API 地址(可通过环境变量覆盖)
const BACKEND_URL = process.env.OFFICEAGENT_BACKEND_URL || 'http://localhost:8000';

// Phase 3.0: OAuth 自定义协议(用于 Google OAuth 等第三方登录回调)
const OAUTH_PROTOCOL = 'officeagent';
// 已缓存的 OAuth 回调 URL(应用未启动时收到的回调,会在窗口 ready 后回放)
let pendingOAuthUrl: string | null = null;
let mainWindow: BrowserWindow | null = null;

/**
 * 创建主窗口
 */
function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    show: false,
    title: 'OfficeAgent',
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      sandbox: true, // 沙箱模式:渲染进程无法直接 require Node 模块
      contextIsolation: true, // 上下文隔离:preload 与渲染进程环境分离
      nodeIntegration: false, // 禁用 Node 集成
    },
  });

  // 开发模式加载 Vite dev server,生产模式加载打包后的 HTML
  const isDev = !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL('http://localhost:5174');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Phase 1.9: 初始化自动更新(打包后从 GitHub Releases 检查)
  if (!isDev) {
    initAutoUpdater(mainWindow);
  }
}

// ---------------------------------------------------------------------------
// IPC 处理器
// ---------------------------------------------------------------------------

/**
 * 健康检查 — 主进程通过 HTTP 调用后端
 * 渲染进程通过 IPC 间接调用,无法直接 fetch 后端(沙箱隔离)
 */
ipcMain.handle('backend:health', async () => {
  try {
    const resp = await fetch(`${BACKEND_URL}/health`);
    if (!resp.ok) return { ok: false, status: resp.status, error: resp.statusText };
    const data = await resp.json();
    return { ok: true, data };
  } catch (err) {
    return {
      ok: false,
      status: 0,
      error: err instanceof Error ? err.message : 'Unknown error',
    };
  }
});

/**
 * safeStorage 加密存储 — 用于存储 Access Token / Refresh Token
 * 使用操作系统级密钥链(macOS Keychain / Windows DPAPI / Linux libsecret)
 */
ipcMain.handle('secure:set', async (_event, _key: string, value: string) => {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('safeStorage 不可用(操作系统不支持加密存储)');
  }
  const encrypted = safeStorage.encryptString(value);
  // 返回加密后的 Base64 字符串(调用方负责持久化到 userData 目录)
  return encrypted.toString('base64');
});

ipcMain.handle('secure:get', async (_event, encryptedBase64: string) => {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('safeStorage 不可用');
  }
  const buffer = Buffer.from(encryptedBase64, 'base64');
  return safeStorage.decryptString(buffer);
});

// ---------------------------------------------------------------------------
// Phase 3.1: 本地文件系统 IPC
// ---------------------------------------------------------------------------

/** 文件树节点(渲染进程用) */
interface FileTreeNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  children?: FileTreeNode[];
}

/** 读取目录树(递归,限制深度避免大型仓库卡死) */
function readDirectoryTree(dirPath: string, maxDepth = 5, currentDepth = 0): FileTreeNode[] {
  if (currentDepth >= maxDepth) return [];
  try {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    const nodes: FileTreeNode[] = [];
    for (const entry of entries) {
      // 跳过隐藏文件 / node_modules / .git
      if (entry.name.startsWith('.') || entry.name === 'node_modules') continue;
      const fullPath = path.join(dirPath, entry.name);
      if (entry.isDirectory()) {
        nodes.push({
          name: entry.name,
          path: fullPath,
          type: 'directory',
          children: readDirectoryTree(fullPath, maxDepth, currentDepth + 1),
        });
      } else {
        try {
          const stat = fs.statSync(fullPath);
          nodes.push({
            name: entry.name,
            path: fullPath,
            type: 'file',
            size: stat.size,
          });
        } catch {
          nodes.push({ name: entry.name, path: fullPath, type: 'file' });
        }
      }
    }
    // 目录在前,文件在后,各自按名称排序
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    return nodes;
  } catch {
    return [];
  }
}

/** 打开文件夹选择对话框 */
ipcMain.handle('fs:openFolder', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory'],
    title: '选择工作区文件夹',
  });
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0];
});

/** 读取目录树 */
ipcMain.handle('fs:readTree', async (_event, dirPath: string) => {
  if (!dirPath || !fs.existsSync(dirPath)) return [];
  return readDirectoryTree(dirPath);
});

/**
 * 读取单层目录(非递归)— 用于文件树懒加载。
 * 返回的目录节点不含 children,展开时由渲染进程再次调用本接口获取下一层。
 */
ipcMain.handle('fs:readDir', async (_event, dirPath: string) => {
  if (!dirPath || !fs.existsSync(dirPath)) return [];
  try {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    const nodes: FileTreeNode[] = [];
    for (const entry of entries) {
      if (entry.name.startsWith('.') || entry.name === 'node_modules') continue;
      const fullPath = path.join(dirPath, entry.name);
      if (entry.isDirectory()) {
        nodes.push({ name: entry.name, path: fullPath, type: 'directory' });
      } else {
        try {
          const stat = fs.statSync(fullPath);
          nodes.push({ name: entry.name, path: fullPath, type: 'file', size: stat.size });
        } catch {
          nodes.push({ name: entry.name, path: fullPath, type: 'file' });
        }
      }
    }
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    return nodes;
  } catch {
    return [];
  }
});

/** 读取文件内容 */
ipcMain.handle('fs:readFile', async (_event, filePath: string) => {
  try {
    const content = fs.readFileSync(filePath, 'utf-8');
    return { ok: true, content };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : '读取失败' };
  }
});

/** 写入文件内容 */
ipcMain.handle('fs:writeFile', async (_event, filePath: string, content: string) => {
  try {
    fs.writeFileSync(filePath, content, 'utf-8');
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : '写入失败' };
  }
});

/** 创建新文件 */
ipcMain.handle('fs:createFile', async (_event, filePath: string, content = '') => {
  try {
    fs.writeFileSync(filePath, content, 'utf-8');
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : '创建失败' };
  }
});

/** 创建目录 */
ipcMain.handle('fs:createDir', async (_event, dirPath: string) => {
  try {
    fs.mkdirSync(dirPath, { recursive: true });
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : '创建失败' };
  }
});

/** 删除文件或目录 */
ipcMain.handle('fs:delete', async (_event, targetPath: string) => {
  try {
    const stat = fs.statSync(targetPath);
    if (stat.isDirectory()) {
      fs.rmSync(targetPath, { recursive: true, force: true });
    } else {
      fs.unlinkSync(targetPath);
    }
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : '删除失败' };
  }
});

/** 重命名 / 移动 */
ipcMain.handle('fs:rename', async (_event, oldPath: string, newPath: string) => {
  try {
    fs.renameSync(oldPath, newPath);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : '重命名失败' };
  }
});

// ---------------------------------------------------------------------------
// Phase 3.0: OAuth 自定义协议 + 外部浏览器
// ---------------------------------------------------------------------------

/**
 * 在系统默认浏览器中打开 URL(用于 OAuth 跳转)。
 * 桌面应用不直接渲染 OAuth 页面,而是交给系统浏览器。
 */
ipcMain.handle('shell:openExternal', async (_event, url: string) => {
  await shell.openExternal(url);
  return true;
});

/**
 * 解析 OAuth 回调 URL,提取 provider_code / code / state。
 *
 * URL 形如:
 *   officeagent://oauth/callback?provider=google&code=xxx&state=yyy
 */
function parseOAuthCallback(url: string): {
  provider_code: string;
  code: string;
  state?: string;
} | null {
  try {
    const parsed = new URL(url);
    const params = parsed.searchParams;
    const provider = params.get('provider') || params.get('provider_code');
    const code = params.get('code');
    if (!provider || !code) return null;
    return {
      provider_code: provider,
      code,
      state: params.get('state') ?? undefined,
    };
  } catch {
    return null;
  }
}

/**
 * 将 OAuth 回调推送给渲染进程(若窗口已就绪),否则缓存等待窗口 ready。
 */
function dispatchOAuthCallback(url: string): void {
  const data = parseOAuthCallback(url);
  if (!data) return;
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('oauth:callback', data);
  } else {
    pendingOAuthUrl = url;
  }
}

/**
 * 注册 officeagent:// 自定义协议。
 *
 * macOS:通过 app.on('open-url') 事件接收(系统将 URL 转发给应用)。
 * Windows:通过 app.on('second-instance') 事件接收(第二个实例启动时传入 URL)。
 *
 * 必须在 app.whenReady() 之前调用 setAsDefaultProtocolClient。
 */
app.setAsDefaultProtocolClient(OAUTH_PROTOCOL);

// macOS:系统直接把 URL 转发给已运行的应用实例
app.on('open-url', (_event, url) => {
  if (url.startsWith(`${OAUTH_PROTOCOL}://`)) {
    dispatchOAuthCallback(url);
  }
});

// Windows:第二个实例启动时,命令行参数中携带 URL
app.on('second-instance', (_event, argv) => {
  const oauthUrl = argv.find((arg) => arg.startsWith(`${OAUTH_PROTOCOL}://`));
  if (oauthUrl) {
    dispatchOAuthCallback(oauthUrl);
  }
});

// ---------------------------------------------------------------------------
// 应用生命周期
// ---------------------------------------------------------------------------

// Windows:申请单实例锁(确保 second-instance 事件能触发)
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}

app.whenReady().then(() => {
  createWindow();
  // 若应用启动前就收到了 OAuth 回调,窗口 ready 后回放
  if (pendingOAuthUrl && mainWindow) {
    mainWindow.webContents.once('did-finish-load', () => {
      if (pendingOAuthUrl) {
        dispatchOAuthCallback(pendingOAuthUrl);
        pendingOAuthUrl = null;
      }
    });
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
