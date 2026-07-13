/**
 * 自动更新模块 — Phase 1.9
 *
 * 使用 electron-updater 从 GitHub Releases 检查并安装更新。
 *
 * 流程:
 *   1. 应用启动后 10 秒检查更新
 *   2. 发现新版本后下载(后台)
 *   3. 下载完成提示用户重启
 *   4. 用户确认后 quitAndInstall()
 *
 * 安全:
 *   - 仅从配置的 publish provider(GitHub Releases / 自建 CDN)拉取
 *   - electron-updater 内置签名校验(需代码签名才能启用)
 *   - 开发模式(app.isPackaged === false)跳过更新检查
 */
import { autoUpdater } from 'electron-updater';
import { app, ipcMain, BrowserWindow } from 'electron';

let updateDownloaded = false;

/** 初始化自动更新(仅在打包后生效) */
export function initAutoUpdater(window: BrowserWindow): void {
  // 开发模式跳过(仅打包后检查更新)
  if (!app.isPackaged) return;
  if (process.env.fnixagent_DISABLE_UPDATER === '1') return;

  // 配置
  autoUpdater.autoDownload = true;       // 自动后台下载
  autoUpdater.autoInstallOnAppQuit = true; // 退出时自动安装
  autoUpdater.allowDowngrade = false;

  // 日志
  autoUpdater.logger = console;

  // 事件订阅
  autoUpdater.on('checking-for-update', () => {
    window.webContents.send('updater:status', { status: 'checking' });
  });

  autoUpdater.on('update-available', (info) => {
    window.webContents.send('updater:status', {
      status: 'available',
      version: info.version,
      releaseNotes: info.releaseNotes,
    });
  });

  autoUpdater.on('update-not-available', () => {
    window.webContents.send('updater:status', { status: 'up-to-date' });
  });

  autoUpdater.on('download-progress', (progress) => {
    window.webContents.send('updater:progress', {
      percent: progress.percent,
      transferred: progress.transferred,
      total: progress.total,
    });
  });

  autoUpdater.on('update-downloaded', () => {
    updateDownloaded = true;
    window.webContents.send('updater:status', { status: 'downloaded' });
  });

  autoUpdater.on('error', (err) => {
    window.webContents.send('updater:status', {
      status: 'error',
      message: err?.message || String(err),
    });
  });

  // IPC:手动检查更新
  ipcMain.handle('updater:check', async () => {
    try {
      await autoUpdater.checkForUpdates();
      return { ok: true };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  });

  // IPC:立即安装并重启
  ipcMain.handle('updater:install', () => {
    if (updateDownloaded) {
      autoUpdater.quitAndInstall();
      return { ok: true };
    }
    return { ok: false, error: '更新尚未下载完成' };
  });

  // 启动后 10 秒检查更新
  setTimeout(() => {
    autoUpdater.checkForUpdates().catch(() => {
      /* 忽略启动时的检查失败 */
    });
  }, 10_000);

  // 每 4 小时检查一次
  setInterval(
    () => {
      autoUpdater.checkForUpdates().catch(() => {});
    },
    4 * 60 * 60 * 1000,
  );
}

/** 是否有已下载的更新待安装 */
export function hasPendingUpdate(): boolean {
  return updateDownloaded;
}
