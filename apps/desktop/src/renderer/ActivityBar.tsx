/**
 * ActivityBar — 左侧活动栏
 *
 * 48px 宽，竖向排列活动图标按钮。
 * 对标 Cursor 风格：每个图标 48×48，hover 时圆角浅灰背景。
 * 底部设置按钮通过 margin-top: auto 推到底部。
 */
import React from 'react';

interface ActivityBarProps {
  active: string;
  onSelect: (id: string) => void;
  sidebarVisible: boolean;
  onToggleSidebar: () => void;
}

interface ActivityItem {
  id: string;
  icon: string;
  label: string;
}

const activities: ActivityItem[] = [
  { id: 'files',   icon: '📁', label: '文件资源管理器' },
  { id: 'search',  icon: '🔍', label: '搜索' },
  { id: 'chat',    icon: '💬', label: '对话' },
  { id: 'agent',   icon: '🤖', label: 'Agent' },
  { id: 'git',     icon: '⊿',  label: '源代码管理' },
];

export const ActivityBar: React.FC<ActivityBarProps> = ({
  active,
  onSelect,
  sidebarVisible,
  onToggleSidebar,
}) => {
  function handleClick(id: string) {
    if (id === active && sidebarVisible) {
      // 如果点击已激活的项且侧边栏可见，则收起侧边栏
      onToggleSidebar();
    } else {
      onSelect(id);
    }
  }

  return (
    <nav style={s.container}>
      <div style={s.items}>
        {activities.map((item) => {
          const isActive = active === item.id;
          return (
            <button
              key={item.id}
              style={{
                ...s.item,
                color: isActive ? 'var(--accent)' : 'var(--text-tertiary)',
              }}
              onClick={() => handleClick(item.id)}
              title={item.label}
              aria-label={item.label}
              aria-pressed={isActive}
            >
              <span style={s.icon}>{item.icon}</span>
              {isActive && <span style={s.activeIndicator} />}
            </button>
          );
        })}
      </div>

      {/* 底部：设置 */}
      <div style={s.bottom}>
        <button
          style={{
            ...s.item,
            color: active === 'settings' ? 'var(--accent)' : 'var(--text-tertiary)',
          }}
          onClick={() => onSelect('settings')}
          title="设置"
          aria-label="设置"
        >
          <span style={s.icon}>⚙</span>
          {active === 'settings' && <span style={s.activeIndicator} />}
        </button>
      </div>
    </nav>
  );
};

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    width: 'var(--activity-bar-width)',
    height: '100%',
    background: 'var(--bg-secondary)',
    borderRight: '1px solid var(--border-color)',
    flexShrink: 0,
    userSelect: 'none',
  },
  items: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    paddingTop: 4,
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    width: 48,
    height: 48,
    background: 'transparent',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 20,
    transition: 'background 0.12s, color 0.12s',
  },
  icon: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 36,
    height: 36,
    borderRadius: 6,
    transition: 'background 0.12s',
  },
  activeIndicator: {
    position: 'absolute',
    left: 0,
    top: '50%',
    transform: 'translateY(-50%)',
    width: 2,
    height: 24,
    background: 'var(--accent)',
    borderRadius: '0 2px 2px 0',
  },
  bottom: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    marginTop: 'auto',
    paddingBottom: 4,
  },
};