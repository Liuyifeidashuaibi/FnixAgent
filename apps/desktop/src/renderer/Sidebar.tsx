/**
 * Sidebar — 上下文侧边栏
 *
 * 根据 activeActivity 切换内容:
 *   files  → FilesPanel(懒加载文件树 + Open Editors + 右键菜单 + 拖拽)
 *   search → SearchPanel(sdk.code.search 语义代码搜索)
 *   agent  → 进程列表(占位)
 *   git    → GitPanel(源代码管理面板)
 *
 * 260px 宽,border-right。
 */
import React from 'react';
import { FilesPanel, type OpenEditorEntry } from './FilesPanel';
import { SearchPanel } from './SearchPanel';
import { GitPanel } from './GitPanel';
import { AgentProcessPanel } from './AgentProcessPanel';

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
      return <AgentProcessPanel onOpenFile={onOpenFile} />;
    case 'git':
      return <GitPanel workspacePath={workspacePath} onOpenFile={onOpenFile} />;
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


