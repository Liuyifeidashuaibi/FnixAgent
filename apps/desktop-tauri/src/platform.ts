/**
 * Tauri 2 平台桥 — 安装与 Electron preload 兼容的 window.electron API
 */
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import type { FileTreeNode } from '@/global';

type OkResult = { ok: true } | { ok: false; error: string };
type ReadResult = { ok: true; content: string } | { ok: false; error: string };

export function isTauriShell(): boolean {
  return typeof window !== 'undefined' && !(window as Window & { electron?: unknown }).electron;
}

export async function bootstrapRuntime(): Promise<void> {
  if (typeof window === 'undefined') return;
  try {
    await invoke('runtime_bootstrap');
  } catch {
    /* 外部 dev:all 已托管进程 */
  }
}

export function installTauriPlatform(): void {
  if (typeof window === 'undefined') return;
  if (window.electron) return;

  const noopUnsub = () => {};

  window.electron = {
    backend: {
      health: () => invoke('backend_health'),
    },
    secure: {
      set: (key: string, value: string) => invoke<string>('secure_set', { key, value }),
      get: (key: string) => invoke<string>('secure_get', { key }),
      delete: (key: string) => invoke('secure_delete', { key }),
    },
    app: {
      version: '1.0.0',
      platform: navigator.platform.toLowerCase().includes('win')
        ? 'win32'
        : navigator.platform.toLowerCase().includes('mac')
          ? 'darwin'
          : 'linux',
    },
    shell: {
      openExternal: (url: string) => invoke<boolean>('shell_open_external', { url }),
      openPath: (targetPath: string) =>
        invoke<{ ok: true } | { ok: false; error: string }>('shell_open_path', { targetPath }),
      exec: (command: string, cwd?: string, timeoutMs?: number) =>
        invoke<{ ok: boolean; code: number; stdout: string; stderr: string; error?: string }>(
          'shell_exec',
          { command, cwd, timeoutMs },
        ),
    },
    fs: {
      openFolder: () => invoke<string | null>('fs_open_folder'),
      openFiles: () => invoke<string[]>('fs_open_files'),
      readTree: (dirPath: string) => invoke<FileTreeNode[]>('fs_read_tree', { dirPath }),
      readDir: (dirPath: string) => invoke<FileTreeNode[]>('fs_read_dir', { dirPath }),
      readFile: (filePath: string) => invoke<ReadResult>('fs_read_file', { filePath }),
      writeFile: (filePath: string, content: string) =>
        invoke<OkResult>('fs_write_file', { filePath, content }),
      createFile: (filePath: string, content = '') =>
        invoke<OkResult>('fs_create_file', { filePath, content }),
      createDir: (dirPath: string) => invoke<OkResult>('fs_create_dir', { dirPath }),
      delete: (targetPath: string) => invoke<OkResult>('fs_delete', { targetPath }),
      rename: (oldPath: string, newPath: string) =>
        invoke<OkResult>('fs_rename', { oldPath, newPath }),
    },
    oauth: {
      onCallback: () => noopUnsub,
    },
    runtime: {
      getConfig: () =>
        invoke<{ apiBase: string; sidecarUrl: string; packaged: boolean }>('runtime_get_config'),
      bootstrap: () =>
        invoke<{ apiBase: string; sidecarUrl: string; packaged: boolean }>('runtime_bootstrap'),
    },
    pty: {
      spawn: (cwd?: string | null, cols?: number, rows?: number) =>
        invoke<string>('pty_spawn', { cwd: cwd ?? null, cols, rows }),
      write: (id: string, data: string) => invoke('pty_write', { id, data }),
      resize: (id: string, cols: number, rows: number) =>
        invoke('pty_resize', { id, cols, rows }),
      kill: (id: string) => invoke('pty_kill', { id }),
      onOutput: (handler: (id: string, data: string) => void) => {
        let unlisten: UnlistenFn | null = null;
        void listen<{ id: string; data: string }>('pty-output', (event) => {
          handler(event.payload.id, event.payload.data);
        }).then((fn) => {
          unlisten = fn;
        });
        return () => {
          void unlisten?.();
        };
      },
      onExit: (handler: (id: string) => void) => {
        let unlisten: UnlistenFn | null = null;
        void listen<{ id: string }>('pty-exit', (event) => {
          handler(event.payload.id);
        }).then((fn) => {
          unlisten = fn;
        });
        return () => {
          void unlisten?.();
        };
      },
    },
    updater: {
      check: async () => ({ ok: false, reason: 'tauri-updater-not-configured' }),
      install: async () => false,
      onStatus: () => noopUnsub,
      onProgress: () => noopUnsub,
    },
  };
}
