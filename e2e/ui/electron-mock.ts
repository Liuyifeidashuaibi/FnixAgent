/** Playwright 启动前注入 Tauri/Electron 平台 mock */
export const electronMock = `
(() => {
  if (window.electron) return;
  const listeners = new Map();
  window.electron = {
    backend: {
      health: async () => ({ ok: true, runtime: 'mock' }),
    },
    secure: {
      set: async () => 'ok',
      get: async () => '',
      delete: async () => {},
    },
    app: { version: '1.0.0-e2e', platform: 'web' },
    shell: {
      openExternal: async () => true,
      openPath: async () => ({ ok: true }),
      exec: async () => ({ ok: true, code: 0, stdout: '', stderr: '' }),
    },
    fs: {
      openFolder: async () => null,
      openFiles: async () => [],
      readTree: async () => [],
      readDir: async () => [],
      readFile: async () => ({ ok: true, content: '' }),
      writeFile: async () => ({ ok: true }),
      createFile: async () => ({ ok: true }),
      createDir: async () => ({ ok: true }),
      delete: async () => ({ ok: true }),
      rename: async () => ({ ok: true }),
    },
    oauth: { onCallback: () => () => {} },
    runtime: {
      getConfig: async () => ({
        apiBase: 'http://127.0.0.1:8000',
        sidecarUrl: 'http://127.0.0.1:8710',
        packaged: false,
      }),
      bootstrap: async () => ({
        apiBase: 'http://127.0.0.1:8000',
        sidecarUrl: 'http://127.0.0.1:8710',
        packaged: false,
      }),
    },
    pty: undefined,
    updater: {
      check: async () => ({}),
      install: async () => ({}),
      onStatus: () => () => {},
      onProgress: () => () => {},
    },
  };
})();
`;
