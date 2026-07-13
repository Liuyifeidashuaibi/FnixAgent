/**
 * TopBar — 顶部标题栏
 *
 * 32px 高，border-bottom，支持窗口拖拽。
 * 左侧：品牌标识
 * 中间：工作区路径
 * 右侧：IDE/Chat 切换、Agent 面板开关、设置
 */
import React from 'react';

interface TopBarProps {
  workspacePath: string | null;
  centerView: 'editor' | 'chat';
  onToggleCenterView: () => void;
  agentPanelVisible: boolean;
  onToggleAgentPanel: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  workspacePath,
  centerView,
  onToggleCenterView,
  agentPanelVisible,
  onToggleAgentPanel,
}) => {
  return (
    <header style={s.header}>
      {/* 左侧：品牌 */}
      <div style={s.left}>
        <span style={s.brand}>fnixagent</span>
      </div>

      {/* 中间：工作区路径 */}
      <div style={s.center}>
        {workspacePath ? (
          <span style={s.workspacePath} title={workspacePath}>
            {workspacePath}
          </span>
        ) : (
          <span style={s.workspaceHint}>打开文件夹以开始</span>
        )}
      </div>

      {/* 右侧：操作按钮 */}
      <div style={s.right}>
        <button
          style={s.actionBtn}
          onClick={onToggleCenterView}
          title={centerView === 'editor' ? '切换到对话模式' : '切换到编辑器模式'}
        >
          {centerView === 'editor' ? '⇄ 对话' : '⇄ 编辑器'}
        </button>

        <button
          style={{
            ...s.actionBtn,
            background: agentPanelVisible ? 'var(--accent-light)' : 'transparent',
            color: agentPanelVisible ? 'var(--accent)' : 'var(--text-secondary)',
          }}
          onClick={onToggleAgentPanel}
          title={agentPanelVisible ? '收起 Agent 面板' : '展开 Agent 面板'}
        >
          🤖
        </button>

        <button style={s.actionBtn} title="设置">
          ⚙
        </button>
      </div>
    </header>
  );
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type CSS = Record<string, any>;

const s: CSS = {
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 'var(--topbar-height)',
    padding: '0 12px',
    background: 'var(--bg-primary)',
    borderBottom: '1px solid var(--border-color)',
    flexShrink: 0,
    WebkitAppRegion: 'drag',
    webkitAppRegion: 'drag',
    userSelect: 'none',
  },
  left: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    WebkitAppRegion: 'drag',
    webkitAppRegion: 'drag',
  },
  brand: {
    fontSize: 12,
    fontWeight: 700,
    color: 'var(--text-primary)',
    letterSpacing: '-0.2px',
  },
  center: {
    position: 'absolute',
    left: '50%',
    transform: 'translateX(-50%)',
    display: 'flex',
    alignItems: 'center',
    WebkitAppRegion: 'drag',
    webkitAppRegion: 'drag',
  },
  workspacePath: {
    fontSize: 11,
    color: 'var(--text-tertiary)',
    maxWidth: 360,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  workspaceHint: {
    fontSize: 11,
    color: 'var(--text-tertiary)',
    fontStyle: 'italic',
  },
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: 2,
    WebkitAppRegion: 'no-drag',
    webkitAppRegion: 'no-drag',
  },
  actionBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: 24,
    padding: '0 8px',
    background: 'transparent',
    border: 'none',
    borderRadius: 4,
    color: 'var(--text-secondary)',
    fontSize: 12,
    cursor: 'pointer',
    transition: 'background 0.12s, color 0.12s',
  },
};