/**
 * DiffView.tsx — 代码变更对比视图
 *
 * 功能：
 *   - 使用 Monaco DiffEditor 左右对比原始/修改后代码
 *   - 行级差异高亮（删除红、新增绿）
 *   - 文件路径 + 变更统计
 *   - Accept / Reject 按钮
 */
import { DiffEditor } from '@monaco-editor/react';

export interface DiffViewProps {
  original: string;
  modified: string;
  filePath: string;
  onAccept: () => void;
  onReject: () => void;
}

const CSS = {
  '--bg-primary': '#ffffff',
  '--bg-secondary': '#f4f5f7',
  '--bg-tertiary': '#ebecee',
  '--text-primary': '#28282c',
  '--text-secondary': '#6b7280',
  '--text-tertiary': '#9ca3af',
  '--border-color': '#e4e4e7',
  '--accent': '#0066b8',
  '--accent-hover': '#005299',
  '--accent-light': 'rgba(0, 102, 184, 0.08)',
  '--success': '#22c55e',
  '--warning': '#f59e0b',
  '--error': '#dc2626',
  '--font-sans': "'Inter', -apple-system, sans-serif",
  '--font-mono': "'JetBrains Mono', Menlo, monospace",
} as const;

export function DiffView({
  original,
  modified,
  filePath,
  onAccept,
  onReject,
}: DiffViewProps) {
  const stats = computeDiffStats(original, modified);

  return (
    <div style={styles.container}>
      {/* 头部 */}
      <div style={styles.header}>
        <div style={styles.fileInfo}>
          <span style={styles.fileIcon}>📄</span>
          <span style={styles.filePath}>{filePath}</span>
        </div>
        <div style={styles.stats}>
          {stats.added > 0 && (
            <span style={styles.statAdded}>+{stats.added}</span>
          )}
          {stats.removed > 0 && (
            <span style={styles.statRemoved}>-{stats.removed}</span>
          )}
          {stats.added === 0 && stats.removed === 0 && (
            <span style={styles.statNoChange}>无变更</span>
          )}
        </div>
      </div>

      {/* Diff 编辑器 */}
      <div style={styles.diffContainer}>
        <DiffEditor
          height="100%"
          theme="light"
          original={original}
          modified={modified}
          language={detectLanguage(filePath)}
          options={{
            readOnly: true,
            minimap: { enabled: false },
            fontSize: 13,
            fontFamily: CSS['--font-mono'],
            renderSideBySide: true,
            lineNumbers: 'on' as const,
            scrollBeyondLastLine: false,
            automaticLayout: true,
            wordWrap: 'on' as const,
            padding: { top: 8 },
            folding: false,
            glyphMargin: false,
            lineDecorationsWidth: 8,
            lineNumbersMinChars: 3,
          }}
        />
      </div>

      {/* 底部操作栏 */}
      <div style={styles.footer}>
        <button style={styles.rejectBtn} onClick={onReject}>
          ✗ Reject
        </button>
        <button style={styles.acceptBtn} onClick={onAccept}>
          ✓ Accept
        </button>
      </div>
    </div>
  );
}

function computeDiffStats(
  original: string,
  modified: string,
): { added: number; removed: number } {
  const origLines = original.split(/\r?\n/);
  const modLines = modified.split(/\r?\n/);

  // 简单的行级逐行对比（基于集合）
  let added = 0;
  let removed = 0;

  const origSet = new Set(origLines);
  const modSet = new Set(modLines);

  // 在 modified 中但不在 original 中的 = 新增
  for (const line of modLines) {
    if (!origSet.has(line)) added++;
  }

  // 在 original 中但不在 modified 中的 = 删除
  for (const line of origLines) {
    if (!modSet.has(line)) removed++;
  }

  return { added, removed };
}

function detectLanguage(filePath: string): string {
  const ext = (filePath.split('.').pop() || '').toLowerCase();
  const langMap: Record<string, string> = {
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    mjs: 'javascript',
    cjs: 'javascript',
    py: 'python',
    pyi: 'python',
    pyx: 'python',
    json: 'json',
    jsonc: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    md: 'markdown',
    mdx: 'markdown',
    html: 'html',
    htm: 'html',
    css: 'css',
    scss: 'scss',
    less: 'less',
    sql: 'sql',
    graphql: 'graphql',
    gql: 'graphql',
    sh: 'shell',
    bash: 'shell',
    zsh: 'shell',
    bat: 'bat',
    ps1: 'powershell',
    xml: 'xml',
    svg: 'xml',
    toml: 'ini',
    ini: 'ini',
    env: 'plaintext',
    txt: 'plaintext',
    gitignore: 'plaintext',
    dockerfile: 'dockerfile',
    makefile: 'makefile',
    rs: 'rust',
    go: 'go',
    java: 'java',
    c: 'c',
    cpp: 'cpp',
    h: 'c',
    hpp: 'cpp',
    rb: 'ruby',
    php: 'php',
    swift: 'swift',
    kt: 'kotlin',
    scala: 'scala',
    r: 'r',
    lua: 'lua',
    pl: 'perl',
    ex: 'elixir',
    exs: 'elixir',
    elm: 'elm',
    vue: 'html',
    svelte: 'html',
    astro: 'html',
    prisma: 'graphql',
  };
  return langMap[ext] || 'plaintext';
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: CSS['--bg-primary'],
    fontFamily: CSS['--font-sans'],
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 40,
    padding: '0 14px',
    borderBottom: `1px solid ${CSS['--border-color']}`,
    background: CSS['--bg-secondary'],
    flexShrink: 0,
  },
  fileInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  fileIcon: {
    fontSize: 14,
  },
  filePath: {
    fontSize: 13,
    color: CSS['--text-primary'],
    fontFamily: CSS['--font-mono'],
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  stats: {
    display: 'flex',
    gap: 10,
    fontSize: 12,
    fontWeight: 600,
  },
  statAdded: {
    color: CSS['--success'],
  },
  statRemoved: {
    color: CSS['--error'],
  },
  statNoChange: {
    color: CSS['--text-tertiary'],
    fontStyle: 'italic',
  },
  diffContainer: {
    flex: 1,
    overflow: 'hidden',
  },
  footer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 8,
    height: 44,
    padding: '0 14px',
    borderTop: `1px solid ${CSS['--border-color']}`,
    background: CSS['--bg-secondary'],
    flexShrink: 0,
  },
  acceptBtn: {
    padding: '6px 18px',
    border: 'none',
    borderRadius: 6,
    background: CSS['--success'],
    color: '#ffffff',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'opacity 0.15s',
  },
  rejectBtn: {
    padding: '6px 18px',
    border: `1px solid ${CSS['--border-color']}`,
    borderRadius: 6,
    background: CSS['--bg-primary'],
    color: CSS['--text-secondary'],
    fontSize: 13,
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
};