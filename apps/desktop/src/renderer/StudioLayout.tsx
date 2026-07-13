/**
 * StudioLayout — Cursor/Codex 风格主布局
 *
 * 全屏布局结构：
 *   TopBar (32px)
 *   ┌──────┬──────────┬─────────────────────┬──────────┐
 *   │Activ.│ Sidebar  │ CenterArea          │ Agent    │
 *   │Bar   │ 260px    │  TabBar + Editor/   │ Panel    │
 *   │48px  │          │  Chat + CommandInput │ 320px    │
 *   └──────┴──────────┴─────────────────────┴──────────┘
 *
 * 状态管理全部通过 useState 完成，无需外部状态库。
 */
import React, { useState, useCallback, useEffect } from 'react';
import { TopBar } from './TopBar';
import { ActivityBar } from './ActivityBar';
import { Sidebar } from './Sidebar';
import { EditorPanel } from './EditorPanel';
import { ComposerPanel } from './ComposerPanel';

/* ================================================
   Types
   ================================================ */

interface StudioLayoutProps {
  onLogout: () => void;
}

type Activity = 'files' | 'search' | 'agent' | 'git' | 'settings';

interface OpenFile {
  path: string;
  name: string;
  isDirty: boolean;
}

/* ================================================
   StudioLayout
   ================================================ */

export const StudioLayout: React.FC<StudioLayoutProps> = ({ onLogout: _onLogout }) => {
  /* ---- 核心状态 ---- */
  const [activeActivity, setActiveActivity] = useState<Activity>('files');
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [agentPanelVisible, setAgentPanelVisible] = useState(true);
  const [centerView, setCenterView] = useState<'editor' | 'chat'>('editor');

  /* ---- 工作区 & 文件 ---- */
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [savedContent, setSavedContent] = useState('');
  const [saving, setSaving] = useState(false);

  /* ---- 处理函数 ---- */

  const handleSelectActivity = useCallback((id: string) => {
    setActiveActivity(id as Activity);
    if (id === 'chat') {
      setCenterView('chat');
    }
    if (!sidebarVisible) {
      setSidebarVisible(true);
    }
  }, [sidebarVisible]);

  const handleToggleSidebar = useCallback(() => {
    setSidebarVisible((v) => !v);
  }, []);

  const handleToggleAgentPanel = useCallback(() => {
    setAgentPanelVisible((v) => !v);
  }, []);

  const handleToggleCenterView = useCallback(() => {
    setCenterView((v) => (v === 'editor' ? 'chat' : 'editor'));
  }, []);

  const handleOpenFolder = useCallback(async () => {
    const selected = await window.electron.fs.openFolder();
    if (!selected) return;
    setWorkspacePath(selected);
    setOpenFiles([]);
    setActiveFile(null);
    setFileContent('');
    setSavedContent('');
  }, []);

  const handleOpenFile = useCallback(async (path: string, name: string) => {
    // 如果已打开，直接激活
    const existing = openFiles.find((f) => f.path === path);
    if (existing) {
      setActiveFile(path);
      setFileContent('');
      setSavedContent('');
      return;
    }

    // 读取文件内容
    const result = await window.electron.fs.readFile(path);
    if (!result.ok) {
      alert(`打开文件失败: ${result.error}`);
      return;
    }

    const newFile: OpenFile = { path, name, isDirty: false };
    setOpenFiles((prev) => [...prev, newFile]);
    setActiveFile(path);
    setFileContent(result.content);
    setSavedContent(result.content);
  }, [openFiles]);

  const handleCloseFile = useCallback((path: string) => {
    setOpenFiles((prev) => {
      const filtered = prev.filter((f) => f.path !== path);
      if (activeFile === path) {
        setActiveFile(filtered.length > 0 ? filtered[filtered.length - 1].path : null);
      }
      return filtered;
    });
  }, [activeFile]);

  const handleSelectTab = useCallback(async (path: string) => {
    // 如果编辑器中有未保存内容，先保存到当前文件
    if (activeFile && fileContent !== savedContent) {
      const current = openFiles.find((f) => f.path === activeFile);
      if (current) {
        setOpenFiles((prev) =>
          prev.map((f) => (f.path === activeFile ? { ...f, isDirty: true } : f)),
        );
      }
    }

    setActiveFile(path);

    // 读取目标文件内容
    const result = await window.electron.fs.readFile(path);
    if (result.ok) {
      setFileContent(result.content);
      setSavedContent(result.content);
    }
  }, [activeFile, fileContent, savedContent, openFiles]);

  const handleCloseTab = useCallback((path: string) => {
    setOpenFiles((prev) => prev.filter((f) => f.path !== path));
    if (activeFile === path) {
      const remaining = openFiles.filter((f) => f.path !== path);
      if (remaining.length > 0) {
        void handleSelectTab(remaining[remaining.length - 1].path);
      } else {
        setActiveFile(null);
        setFileContent('');
        setSavedContent('');
      }
    }
  }, [activeFile, openFiles, handleSelectTab]);

  const handleSave = useCallback(async () => {
    if (!activeFile) return;
    setSaving(true);
    try {
      const result = await window.electron.fs.writeFile(activeFile, fileContent);
      if (!result.ok) {
        alert(`保存失败: ${result.error}`);
        return;
      }
      setSavedContent(fileContent);
      setOpenFiles((prev) =>
        prev.map((f) => (f.path === activeFile ? { ...f, isDirty: false } : f)),
      );
    } finally {
      setSaving(false);
    }
  }, [activeFile, fileContent]);

  const handleChangeContent = useCallback((content: string) => {
    setFileContent(content);
    if (activeFile) {
      setOpenFiles((prev) =>
        prev.map((f) =>
          f.path === activeFile ? { ...f, isDirty: content !== savedContent } : f,
        ),
      );
    }
  }, [activeFile, savedContent]);

  /* ---- Ctrl+S 全局保存 ---- */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        if (activeFile) {
          e.preventDefault();
          void handleSave();
        }
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [activeFile, handleSave]);

  /* ---- AgentPanel 内容 ---- */
  const agentPanelContent = activeActivity === 'agent' ? 'agent' : 'default';

  /* ================================================
     Render
     ================================================ */

  return (
    <div style={layout.container}>
      {/* ---- TopBar ---- */}
      <TopBar
        workspacePath={workspacePath}
        centerView={centerView}
        onToggleCenterView={handleToggleCenterView}
        agentPanelVisible={agentPanelVisible}
        onToggleAgentPanel={handleToggleAgentPanel}
      />

      {/* ---- 主区域 ---- */}
      <div style={layout.main}>
        {/* ActivityBar */}
        <ActivityBar
          active={activeActivity}
          onSelect={handleSelectActivity}
          sidebarVisible={sidebarVisible}
          onToggleSidebar={handleToggleSidebar}
        />

        {/* Sidebar */}
        {sidebarVisible && (
          <div style={layout.sidebar}>
            <Sidebar
              activeActivity={activeActivity}
              workspacePath={workspacePath}
              activeFile={activeFile}
              openFiles={openFiles}
              onOpenFile={handleOpenFile}
              onCloseOpenEditor={handleCloseFile}
              onSelectFolder={handleOpenFolder}
            />
          </div>
        )}

        {/* CenterArea */}
        <div style={layout.center}>
          {/* TabBar */}
          {centerView === 'editor' && openFiles.length > 0 && (
            <div style={layout.tabBar}>
              {openFiles.map((file) => (
                <button
                  key={file.path}
                  style={{
                    ...layout.tab,
                    background: activeFile === file.path ? 'var(--bg-primary)' : 'transparent',
                    color: activeFile === file.path ? 'var(--text-primary)' : 'var(--text-secondary)',
                    borderBottom: activeFile === file.path ? '2px solid var(--accent)' : '2px solid transparent',
                  }}
                  onClick={() => void handleSelectTab(file.path)}
                  title={file.path}
                >
                  <span style={layout.tabName}>
                    {file.isDirty && <span style={layout.dirtyDot}>●</span>}
                    {file.name}
                  </span>
                  <span
                    style={layout.tabClose}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCloseFile(file.path);
                    }}
                    title="关闭"
                  >
                    ×
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* 编辑器 / 对话 */}
          <div style={layout.editorArea}>
            {centerView === 'editor' ? (
              <EditorPanel
                openFiles={openFiles}
                activeFile={activeFile}
                fileContent={fileContent}
                onSelectTab={handleSelectTab}
                onCloseTab={handleCloseTab}
                onContentChange={handleChangeContent}
                onSave={handleSave}
              />
            ) : (
              <ComposerPanel visible={true} />
            )}
          </div>

          {/* CommandInput（底部命令栏） */}
          <div style={layout.commandBar}>
            <span style={layout.commandHint}>
              {saving ? '● 保存中...' : activeFile ? 'Ctrl+S 保存' : 'Ctrl+O 打开文件'}
            </span>
            {activeFile && (
              <button
                style={layout.saveBtn}
                onClick={() => void handleSave()}
                disabled={saving}
              >
                {saving ? '...' : '保存'}
              </button>
            )}
          </div>
        </div>

        {/* AgentPanel */}
        {agentPanelVisible && (
          <div style={layout.agentPanel}>
            <AgentPanelContent variant={agentPanelContent} />
          </div>
        )}
      </div>
    </div>
  );
};

/* ================================================
   AgentPanelContent
   ================================================ */

interface AgentPanelContentProps {
  variant: 'agent' | 'default';
}

const AgentPanelContent: React.FC<AgentPanelContentProps> = ({ variant }) => {
  if (variant === 'agent') {
    return (
      <div style={agentStyles.container}>
        <div style={agentStyles.header}>
          <span style={agentStyles.title}>Agent</span>
        </div>
        <div style={agentStyles.empty}>
          <p style={agentStyles.emptyText}>暂无活跃进程</p>
          <p style={agentStyles.hint}>Agent 对话中创建的进程将显示在此处</p>
        </div>
      </div>
    );
  }

  return (
    <div style={agentStyles.container}>
      <div style={agentStyles.header}>
        <span style={agentStyles.title}>辅助面板</span>
      </div>
      <div style={agentStyles.empty}>
        <p style={agentStyles.emptyText}>进程 / 记忆 / Shell / Policy</p>
        <p style={agentStyles.hint}>选择 Agent 活动以查看详情</p>
      </div>
    </div>
  );
};

/* ================================================
   样式
   ================================================ */

const layout: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-sans)',
    overflow: 'hidden',
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'row',
    overflow: 'hidden',
  },
  sidebar: {
    width: 'var(--sidebar-width)',
    flexShrink: 0,
    borderRight: '1px solid var(--border-color)',
    overflow: 'hidden',
  },
  center: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    minWidth: 0,
  },
  tabBar: {
    display: 'flex',
    flexShrink: 0,
    height: 32,
    background: 'var(--bg-secondary)',
    borderBottom: '1px solid var(--border-color)',
    overflowX: 'auto',
    overflowY: 'hidden',
  },
  tab: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    height: '100%',
    padding: '0 12px',
    border: 'none',
    borderBottom: '2px solid transparent',
    background: 'transparent',
    fontSize: 12,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'background 0.1s, color 0.1s',
    flexShrink: 0,
  },
  tabName: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
  },
  dirtyDot: {
    color: 'var(--accent)',
    fontSize: 14,
    lineHeight: 1,
  },
  tabClose: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 16,
    height: 16,
    borderRadius: 3,
    fontSize: 14,
    fontWeight: 400,
    color: 'var(--text-tertiary)',
    transition: 'background 0.1s, color 0.1s',
  },
  editorArea: {
    flex: 1,
    display: 'flex',
    overflow: 'hidden',
  },
  editor: {
    width: '100%',
    height: '100%',
    padding: 16,
    border: 'none',
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontSize: 13,
    lineHeight: 1.7,
    resize: 'none',
    outline: 'none',
    tabSize: 2,
  },
  emptyCenter: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    padding: 40,
    textAlign: 'center',
  },
  emptyIcon: {
    fontSize: 40,
    opacity: 0.3,
    marginBottom: 4,
  },
  emptyText: {
    fontSize: 14,
    fontWeight: 500,
    color: 'var(--text-secondary)',
    margin: 0,
  },
  emptyHint: {
    fontSize: 12,
    color: 'var(--text-tertiary)',
    margin: 0,
  },
  openFolderBtn: {
    marginTop: 8,
    padding: '6px 16px',
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    transition: 'background 0.12s',
  },
  commandBar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 28,
    padding: '0 12px',
    background: 'var(--bg-secondary)',
    borderTop: '1px solid var(--border-color)',
    flexShrink: 0,
  },
  commandHint: {
    fontSize: 11,
    color: 'var(--text-tertiary)',
  },
  saveBtn: {
    padding: '2px 10px',
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 11,
    fontWeight: 500,
    transition: 'background 0.12s',
  },
  agentPanel: {
    width: 320,
    flexShrink: 0,
    borderLeft: '1px solid var(--border-color)',
    overflow: 'hidden',
  },
};

const agentStyles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: 'var(--bg-secondary)',
    userSelect: 'none',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 12px',
    flexShrink: 0,
    borderBottom: '1px solid var(--border-color)',
  },
  title: {
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    textAlign: 'center',
    gap: 4,
  },
  emptyText: {
    fontSize: 13,
    color: 'var(--text-secondary)',
    margin: 0,
  },
  hint: {
    fontSize: 11,
    color: 'var(--text-tertiary)',
    margin: 0,
  },
};