/**
 * Sidebar — 上下文侧边栏
 *
 * 根据 activeActivity 切换内容:
 *   files  → FilesPanel(懒加载文件树 + Open Editors + 右键菜单 + 拖拽)
 *   search → SearchPanel(sdk.code.search 语义代码搜索)
 *   agent  → 进程列表(占位)
 *   git    → Git 状态(占位)
 *
 * 260px 宽,border-right。
 */
import React from 'react';
import { FilesPanel, type OpenEditorEntry } from './FilesPanel';
import { SearchPanel } from './SearchPanel';

/* ================================================
   Props
   ================================================ */

interface SidebarProps {
  activeActivity: string;
  workspacePath: string | null;
  activeFile: string | null;
  /** 已打开文件列表(传递给 FilesPanel 的 Open Editors 区) */
  openFiles: OpenEditorEntry[];
  /** 打开文件回调 */
  onOpenFile: (path: string, name: string) => void;
  /** 关闭已打开文件回调(Open Editors 区的 × 按钮) */
  onCloseOpenEditor: (path: string) => void;
  /** 点击「打开文件夹」按钮 */
  onSelectFolder: () => void;
}

/* ================================================
   Sidebar 主组件
   ================================================ */

export const Sidebar: React.FC<SidebarProps> = ({
  activeActivity,
  workspacePath,
  activeFile,
  openFiles,
  onOpenFile,
  onCloseOpenEditor,
  onSelectFolder,
}) => {
  switch (activeActivity) {
    case 'files':
      return (
        <FilesPanel
          workspacePath={workspacePath}
          activeFile={activeFile}
          openFiles={openFiles}
          onOpenFile={onOpenFile}
          onCloseOpenEditor={onCloseOpenEditor}
          onSelectFolder={onSelectFolder}
        />
      );
    case 'search':
      return <SearchPanel onOpenFile={onOpenFile} />;
    case 'agent':
      return <AgentListPanel />;
    case 'git':
      return <GitPanel />;
    default:
      return (
        <FilesPanel
          workspacePath={workspacePath}
          activeFile={activeFile}
          openFiles={openFiles}
          onOpenFile={onOpenFile}
          onCloseOpenEditor={onCloseOpenEditor}
          onSelectFolder={onSelectFolder}
        />
      );
  }
};

/* ================================================
   AgentListPanel(占位 — AgentPanel 已在右侧呈现完整版)
   ================================================ */

const AgentListPanel: React.FC = () => {
  return (
    <div style={panel.container}>
      <div style={panel.header}>
        <span style={panel.title}>进程</span>
      </div>
      <div style={panel.emptyState}>
        <p style={panel.emptyText}>暂无活跃进程</p>
        <p style={panel.hint}>Agent 对话中创建的进程将显示在此处</p>
      </div>
    </div>
  );
};

/* ================================================
   GitPanel(占位)
   ================================================ */

const GitPanel: React.FC = () => {
  return (
    <div style={panel.container}>
      <div style={panel.header}>
        <span style={panel.title}>源代码管理</span>
      </div>
      <div style={panel.emptyState}>
        <p style={panel.emptyText}>暂无 Git 仓库</p>
        <p style={panel.hint}>打开包含 Git 仓库的文件夹以查看变更</p>
      </div>
    </div>
  );
};

/* ================================================
   样式
   ================================================ */

const panel: Record<string, React.CSSProperties> = {
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
  },
  title: {
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  emptyState: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    textAlign: 'center',
  },
  emptyText: {
    color: 'var(--text-secondary)',
    fontSize: 13,
    margin: 0,
  },
  hint: {
    color: 'var(--text-tertiary)',
    fontSize: 11,
    margin: '4px 0 0',
  },
};
