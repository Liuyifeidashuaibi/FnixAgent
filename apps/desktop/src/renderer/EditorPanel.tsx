/**
 * 编辑器面板 — Monaco 编辑器 + 标签栏（浅色主题）
 *
 * 功能：
 *   - 多 Tab 切换（已打开文件）
 *   - Monaco 代码编辑器（@monaco-editor/react）
 *   - 未保存修改标记（圆点）
 *   - Ctrl+S 保存
 *   - 无文件时显示占位
 */
import { useCallback, useRef } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';

export interface EditorPanelProps {
  openFiles: { path: string; name: string; isDirty: boolean }[];
  activeFile: string | null;
  fileContent: string;
  onSelectTab: (path: string) => void;
  onCloseTab: (path: string) => void;
  onContentChange: (content: string) => void;
  onSave: (path: string) => void;
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
  '--font-sans': "'Inter', -apple-system, sans-serif",
  '--font-mono': "'JetBrains Mono', Menlo, monospace",
} as const;

export function EditorPanel({
  openFiles,
  activeFile,
  fileContent,
  onSelectTab,
  onCloseTab,
  onContentChange,
  onSave,
}: EditorPanelProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleEditorMount: OnMount = useCallback(
    (editor, _monaco) => {
      editorRef.current = editor;
      // Ctrl+S 保存
      editor.addCommand(
        // monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS
        2048 | 49,
        () => {
          if (activeFile) onSave(activeFile);
        },
      );
    },
    [activeFile, onSave],
  );

  const activeTab = openFiles.find((f) => f.path === activeFile);

  return (
    <div ref={containerRef} style={styles.container}>
      {/* Tab 栏 */}
      <div style={styles.tabBar}>
        {openFiles.length === 0 ? (
          <div style={styles.tabBarEmpty}>编辑器</div>
        ) : (
          openFiles.map((f) => {
            const isActive = f.path === activeFile;
            return (
              <div
                key={f.path}
                style={{
                  ...styles.tab,
                  background: isActive ? CSS['--bg-primary'] : 'transparent',
                  borderBottom: isActive
                    ? `2px solid ${CSS['--accent']}`
                    : '2px solid transparent',
                  color: isActive ? CSS['--text-primary'] : CSS['--text-secondary'],
                }}
                data-editor-tab="true"
                onClick={() => onSelectTab(f.path)}
                role="tab"
                tabIndex={0}
                title={f.path}
              >
                <span style={styles.tabName}>
                  {f.name}
                  {f.isDirty && <span style={styles.dirtyDot}>●</span>}
                </span>
                <button
                  data-close-btn="true"
                  style={styles.closeBtn}
                  onClick={(e) => {
                    e.stopPropagation();
                    onCloseTab(f.path);
                  }}
                  title="关闭"
                >
                  ×
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* 编辑器区 */}
      {activeFile ? (
        <div style={styles.editorArea}>
          <Editor
            height="100%"
            theme="light"
            value={fileContent}
            onChange={(value) => onContentChange(value ?? '')}
            onMount={handleEditorMount}
            options={{
              fontSize: 14,
              fontFamily: CSS['--font-mono'],
              minimap: { enabled: true },
              lineNumbers: 'on' as const,
              wordWrap: 'on' as const,
              tabSize: 2,
              renderLineHighlight: 'line' as const,
              scrollBeyondLastLine: false,
              automaticLayout: true,
              padding: { top: 8 },
              folding: true,
              glyphMargin: false,
              lineDecorationsWidth: 8,
              lineNumbersMinChars: 3,
            }}
          />
          {/* 状态栏 */}
          <div style={styles.statusBar}>
            <span style={styles.statusItem}>
              {activeTab?.isDirty ? '● 未保存' : '✓ 已保存'}
            </span>
            <span style={styles.statusItem}>{activeFile}</span>
            <span style={styles.statusItem}>
              {fileContent.split(/\r?\n/).length} 行 · {fileContent.length} 字符
            </span>
          </div>
        </div>
      ) : (
        <div style={styles.emptyState}>
          <div style={styles.emptyIcon}>📝</div>
          <p style={styles.emptyText}>打开文件以开始编辑</p>
          <p style={styles.emptyHint}>Open a file to start editing</p>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    flex: 1,
    height: '100%',
    background: CSS['--bg-primary'],
    overflow: 'hidden',
    fontFamily: CSS['--font-sans'],
  },
  tabBar: {
    display: 'flex',
    alignItems: 'stretch',
    height: 40,
    background: CSS['--bg-secondary'],
    borderBottom: `1px solid ${CSS['--border-color']}`,
    overflowX: 'auto' as const,
    overflowY: 'hidden',
    flexShrink: 0,
    // 隐藏滚动条
    scrollbarWidth: 'none' as const,
  },
  tabBarEmpty: {
    display: 'flex',
    alignItems: 'center',
    padding: '0 16px',
    fontSize: 11,
    color: CSS['--text-tertiary'],
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
  },
  tab: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '0 12px',
    minWidth: 0,
    maxWidth: 180,
    cursor: 'pointer',
    borderRight: `1px solid ${CSS['--border-color']}`,
    fontSize: 13,
    whiteSpace: 'nowrap' as const,
    transition: 'background 0.15s',
    flexShrink: 0,
  },
  tabName: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  dirtyDot: {
    color: CSS['--accent'],
    fontSize: 10,
    marginLeft: 2,
    flexShrink: 0,
  },
  closeBtn: {
    background: 'transparent',
    border: 'none',
    color: CSS['--text-tertiary'],
    cursor: 'pointer',
    fontSize: 16,
    padding: '0 2px',
    borderRadius: 4,
    lineHeight: 1,
    opacity: 0,
    flexShrink: 0,
  },
  editorArea: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  statusBar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '4px 12px',
    height: 24,
    background: CSS['--bg-secondary'],
    borderTop: `1px solid ${CSS['--border-color']}`,
    fontSize: 11,
    color: CSS['--text-tertiary'],
    flexShrink: 0,
  },
  statusItem: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  emptyState: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    color: CSS['--text-tertiary'],
  },
  emptyIcon: { fontSize: 48, marginBottom: 12, opacity: 0.4 },
  emptyText: { margin: '0 0 4px', fontSize: 14, color: CSS['--text-secondary'] },
  emptyHint: { margin: 0, fontSize: 12, color: CSS['--text-tertiary'] },
};

// 添加 hover 时显示关闭按钮的样式（通过全局 style 注入）
const hoverStyleId = 'editor-tab-hover-style';
if (typeof document !== 'undefined' && !document.getElementById(hoverStyleId)) {
  const styleEl = document.createElement('style');
  styleEl.id = hoverStyleId;
  styleEl.textContent = `
    [data-editor-tab]:hover {
      background: ${CSS['--bg-tertiary']} !important;
    }
    [data-editor-tab]:hover [data-close-btn] {
      opacity: 1 !important;
    }
    [data-editor-tab] [data-close-btn]:hover {
      opacity: 1 !important;
      background: ${CSS['--accent-light']} !important;
      color: ${CSS['--text-primary']} !important;
    }
  `;
  document.head.appendChild(styleEl);
}