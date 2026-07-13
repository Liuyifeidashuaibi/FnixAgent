/**
 * Electron Preload 脚本
 *
 * 运行在隔离的上下文中,作为主进程与渲染进程之间的桥梁。
 * 通过 contextBridge 暴露安全的 API 给渲染进程,渲染进程无法直接访问 Node API。
 */
import { contextBridge, ipcRenderer } from 'electron';

// 暴露给渲染进程的安全 API
const api = {
  /** 后端健康检查(通过主进程代理) */
  backend: {
    health: () => ipcRenderer.invoke('backend:health'),
  },

  /** 安全存储(基于 OS 密钥链) */
  secure: {
    set: (key: string, value: string) => ipcRenderer.invoke('secure:set', key, value),
    get: (encrypted: string) => ipcRenderer.invoke('secure:get', encrypted),
  },

  /** 应用信息 */
  app: {
    version: process.env.npm_package_version || '1.0.0',
    platform: process.platform,
  },

  /**
   * 在系统默认浏览器中打开 URL(用于 OAuth 跳转)。
   * 桌面应用本身不参与浏览器渲染,仅触发外部浏览器。
   */
  shell: {
    openExternal: (url: string) => ipcRenderer.invoke('shell:openExternal', url),
  },

  /**
   * 本地文件系统操作(Phase 3.1)
   * 通过 IPC 调用主进程的 fs 模块,渲染进程无法直接访问文件系统。
   */
  fs: {
    /** 打开文件夹选择对话框,返回选中路径(取消则返回 null) */
    openFolder: () => ipcRenderer.invoke('fs:openFolder') as Promise<string | null>,
    /** 读取目录树(递归) */
    readTree: (dirPath: string) =>
      ipcRenderer.invoke('fs:readTree', dirPath) as Promise<unknown[]>,
    /** 读取单层目录(非递归,懒加载用) */
    readDir: (dirPath: string) =>
      ipcRenderer.invoke('fs:readDir', dirPath) as Promise<unknown[]>,
    /** 读取文件内容 */
    readFile: (filePath: string) =>
      ipcRenderer.invoke('fs:readFile', filePath) as Promise<
        { ok: true; content: string } | { ok: false; error: string }
      >,
    /** 写入文件内容(覆盖) */
    writeFile: (filePath: string, content: string) =>
      ipcRenderer.invoke('fs:writeFile', filePath, content) as Promise<
        { ok: true } | { ok: false; error: string }
      >,
    /** 创建新文件 */
    createFile: (filePath: string, content = '') =>
      ipcRenderer.invoke('fs:createFile', filePath, content) as Promise<
        { ok: true } | { ok: false; error: string }
      >,
    /** 创建目录(递归) */
    createDir: (dirPath: string) =>
      ipcRenderer.invoke('fs:createDir', dirPath) as Promise<
        { ok: true } | { ok: false; error: string }
      >,
    /** 删除文件或目录(目录递归删除) */
    delete: (targetPath: string) =>
      ipcRenderer.invoke('fs:delete', targetPath) as Promise<
        { ok: true } | { ok: false; error: string }
      >,
    /** 重命名 / 移动 */
    rename: (oldPath: string, newPath: string) =>
      ipcRenderer.invoke('fs:rename', oldPath, newPath) as Promise<
        { ok: true } | { ok: false; error: string }
      >,
  },

  /**
   * OAuth 回调监听(Phase 3.0)
   * 主进程注册了自定义协议 officeagent://oauth/callback,
   * 当浏览器跳转回该协议时,主进程解析 query 并通过此事件推送给渲染进程。
   */
  oauth: {
    onCallback: (
      callback: (data: { provider_code: string; code: string; state?: string }) => void,
    ) => {
      const handler = (
        _event: unknown,
        data: { provider_code: string; code: string; state?: string },
      ) => callback(data);
      ipcRenderer.on('oauth:callback', handler);
      return () => ipcRenderer.removeListener('oauth:callback', handler);
    },
  },

  /** 自动更新(Phase 1.9) */
  updater: {
    /** 手动检查更新 */
    check: () => ipcRenderer.invoke('updater:check'),
    /** 立即安装并重启 */
    install: () => ipcRenderer.invoke('updater:install'),
    /** 订阅状态变化 */
    onStatus: (callback: (status: unknown) => void) => {
      const handler = (_event: unknown, data: unknown) => callback(data);
      ipcRenderer.on('updater:status', handler);
      return () => ipcRenderer.removeListener('updater:status', handler);
    },
    /** 订阅下载进度 */
    onProgress: (callback: (progress: unknown) => void) => {
      const handler = (_event: unknown, data: unknown) => callback(data);
      ipcRenderer.on('updater:progress', handler);
      return () => ipcRenderer.removeListener('updater:progress', handler);
    },
  },
} as const;

// 通过 contextBridge 暴露 API(渲染进程通过 window.electron 访问)
contextBridge.exposeInMainWorld('electron', api);

// 类型定义(供渲染进程使用)
export type ElectronAPI = typeof api;
