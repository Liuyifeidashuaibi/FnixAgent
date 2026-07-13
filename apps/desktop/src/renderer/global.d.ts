/**
 * Electron 渲染进程全局类型声明
 * OfficeAgent Desktop — 浅色主题布局层
 */

export interface FileTreeNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  children?: FileTreeNode[];
}

declare global {
  interface Window {
    electron: {
      backend: { health: () => Promise<unknown> };
      secure: { set: (k: string, v: string) => Promise<string>; get: (e: string) => Promise<string> };
      app: { version: string; platform: string };
      shell: { openExternal: (url: string) => Promise<boolean> };
      fs: {
        openFolder: () => Promise<string | null>;
        readTree: (dirPath: string) => Promise<FileTreeNode[]>;
        readDir: (dirPath: string) => Promise<FileTreeNode[]>;
        readFile: (filePath: string) => Promise<{ ok: true; content: string } | { ok: false; error: string }>;
        writeFile: (filePath: string, content: string) => Promise<{ ok: true } | { ok: false; error: string }>;
        createFile: (filePath: string, content?: string) => Promise<{ ok: true } | { ok: false; error: string }>;
        createDir: (dirPath: string) => Promise<{ ok: true } | { ok: false; error: string }>;
        delete: (targetPath: string) => Promise<{ ok: true } | { ok: false; error: string }>;
        rename: (oldPath: string, newPath: string) => Promise<{ ok: true } | { ok: false; error: string }>;
      };
      oauth: { onCallback: (cb: (d: { provider_code: string; code: string; state?: string }) => void) => () => void };
      updater: {
        check: () => Promise<unknown>;
        install: () => Promise<unknown>;
        onStatus: (cb: (s: unknown) => void) => () => void;
        onProgress: (cb: (p: unknown) => void) => () => void;
      };
    };
  }
}