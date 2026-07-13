/**
 * AgentOS 综合面板
 * 对标 Cursor 右侧 Agent 面板，展示内核状态、进程、记忆、Shell、策略
 */
import { useState, useEffect, useCallback } from 'react';
import { ProcessesPanel } from './ProcessesPanel';
import { MemoryPanel } from './MemoryPanel';
import { TerminalPanel } from './TerminalPanel';
import { PolicyPanel } from './PolicyPanel';

interface AgentPanelProps {
  visible: boolean;
}

type Tab = 'processes' | 'memory' | 'terminal' | 'policy';

import { API_BASE } from './apiConfig';

const AGENT_API = `${API_BASE}/api/v1/agentos`;

const tabs: { key: Tab; label: string; icon: string }[] = [
  { key: 'processes', label: '进程', icon: '🤖' },
  { key: 'memory', label: '记忆', icon: '🧠' },
  { key: 'terminal', label: 'Shell', icon: '⌨️' },
  { key: 'policy', label: '策略', icon: '🛡️' },
];

export function AgentPanel({ visible }: AgentPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>('processes');
  const [booted, setBooted] = useState(false);
  const [bootLoading, setBootLoading] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  // 检查内核状态
  const checkBootStatus = useCallback(async () => {
    try {
      const resp = await fetch(`${AGENT_API}/stats`);
      if (resp.ok) {
        setBooted(true);
      } else {
        setBooted(false);
      }
    } catch {
      setBooted(false);
    }
  }, []);

  useEffect(() => {
    if (visible) {
      checkBootStatus();
    }
  }, [visible, checkBootStatus]);

  async function handleBoot() {
    setBootLoading(true);
    try {
      const resp = await fetch(`${AGENT_API}/boot`, { method: 'POST' });
      if (resp.ok) {
        setBooted(true);
      }
    } catch {
      // 忽略
    } finally {
      setBootLoading(false);
    }
  }

  async function handleShutdown() {
    setBootLoading(true);
    try {
      const resp = await fetch(`${AGENT_API}/shutdown`, { method: 'POST' });
      if (resp.ok) {
        setBooted(false);
      }
    } catch {
      // 忽略
    } finally {
      setBootLoading(false);
    }
  }

  if (!visible) return null;

  if (collapsed) {
    return (
      <div style={s.collapsed}>
        <button style={s.expandBtn} onClick={() => setCollapsed(false)} title="展开 AgentOS">
          ◀
        </button>
        <div style={s.collapsedTabs}>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              style={{
                ...s.collapsedTab,
                ...(activeTab === tab.key ? s.collapsedTabActive : {}),
              }}
              onClick={() => setCollapsed(false)}
              title={tab.label}
            >
              {tab.icon}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={s.container}>
      {/* 标题栏 */}
      <div style={s.header}>
        <div style={s.headerLeft}>
          <span style={s.title}>AgentOS</span>
          <span style={s.subtitle}>内核控制台</span>
        </div>
        <button style={s.collapseBtn} onClick={() => setCollapsed(true)} title="折叠面板">
          ▶
        </button>
      </div>

      {/* 内核状态卡片 */}
      <div style={s.statusCard}>
        <div style={s.statusRow}>
          <span
            style={{
              ...s.statusDot,
              background: booted ? '#22c55e' : '#dc2626',
            }}
          />
          <span style={s.statusLabel}>内核状态</span>
          <span style={booted ? s.statusBooted : s.statusStopped}>
            {booted ? '已启动' : '未启动'}
          </span>
        </div>
        <div style={s.statusActions}>
          <button
            style={booted ? s.bootBtnDisabled : s.bootBtn}
            onClick={handleBoot}
            disabled={booted || bootLoading}
          >
            {bootLoading ? '...' : '启动'}
          </button>
          <button
            style={!booted ? s.shutdownBtnDisabled : s.shutdownBtn}
            onClick={handleShutdown}
            disabled={!booted || bootLoading}
          >
            {bootLoading ? '...' : '关闭'}
          </button>
        </div>
      </div>

      {/* Tab 导航 */}
      <div style={s.tabBar}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            style={{
              ...s.tab,
              ...(activeTab === tab.key ? s.tabActive : {}),
            }}
            onClick={() => setActiveTab(tab.key)}
          >
            <span style={s.tabIcon}>{tab.icon}</span>
            <span style={s.tabLabel}>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab 内容 */}
      <div style={s.content}>
        {activeTab === 'processes' && <ProcessesPanel />}
        {activeTab === 'memory' && <MemoryPanel />}
        {activeTab === 'terminal' && <TerminalPanel />}
        {activeTab === 'policy' && <PolicyPanel />}
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    width: 340,
    background: '#f4f5f7',
    borderLeft: '1px solid #e4e4e7',
    fontFamily: '"Inter", -apple-system, sans-serif',
  },
  // 折叠状态
  collapsed: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    height: '100%',
    width: 44,
    background: '#f4f5f7',
    borderLeft: '1px solid #e4e4e7',
    padding: '8px 0',
    gap: 8,
  },
  expandBtn: {
    background: 'transparent',
    border: 'none',
    color: '#6b7280',
    cursor: 'pointer',
    fontSize: 11,
    padding: '4px 6px',
    borderRadius: 4,
  },
  collapsedTabs: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    alignItems: 'center',
  },
  collapsedTab: {
    background: 'transparent',
    border: 'none',
    cursor: 'pointer',
    fontSize: 16,
    padding: '6px 8px',
    borderRadius: 6,
    opacity: 0.5,
  },
  collapsedTabActive: {
    opacity: 1,
    background: 'rgba(0, 102, 184, 0.08)',
  },
  // 标题栏
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 12px',
    background: '#ffffff',
    borderBottom: '1px solid #e4e4e7',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  title: {
    fontSize: 13,
    fontWeight: 700,
    color: '#28282c',
  },
  subtitle: {
    fontSize: 10,
    color: '#9ca3af',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  collapseBtn: {
    background: 'transparent',
    border: 'none',
    color: '#6b7280',
    cursor: 'pointer',
    fontSize: 11,
    padding: '4px 6px',
    borderRadius: 4,
  },
  // 内核状态卡片
  statusCard: {
    margin: 8,
    padding: 10,
    background: '#ffffff',
    border: '1px solid #e4e4e7',
    borderRadius: 8,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  statusRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    flexShrink: 0,
  },
  statusLabel: {
    fontSize: 12,
    color: '#6b7280',
    flex: 1,
  },
  statusBooted: {
    fontSize: 11,
    fontWeight: 600,
    color: '#22c55e',
  },
  statusStopped: {
    fontSize: 11,
    fontWeight: 600,
    color: '#dc2626',
  },
  statusActions: {
    display: 'flex',
    gap: 8,
  },
  bootBtn: {
    flex: 1,
    padding: '6px 12px',
    background: '#0066b8',
    color: '#ffffff',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 500,
  },
  bootBtnDisabled: {
    flex: 1,
    padding: '6px 12px',
    background: '#ebecee',
    color: '#9ca3af',
    border: 'none',
    borderRadius: 6,
    cursor: 'not-allowed',
    fontSize: 12,
    fontWeight: 500,
  },
  shutdownBtn: {
    flex: 1,
    padding: '6px 12px',
    background: 'transparent',
    color: '#dc2626',
    border: '1px solid #fecaca',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 500,
  },
  shutdownBtnDisabled: {
    flex: 1,
    padding: '6px 12px',
    background: 'transparent',
    color: '#9ca3af',
    border: '1px solid #e4e4e7',
    borderRadius: 6,
    cursor: 'not-allowed',
    fontSize: 12,
    fontWeight: 500,
  },
  // Tab 导航
  tabBar: {
    display: 'flex',
    padding: '0 8px',
    gap: 2,
    background: '#f4f5f7',
    borderBottom: '1px solid #e4e4e7',
  },
  tab: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 2,
    padding: '8px 4px 6px',
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid transparent',
    cursor: 'pointer',
    borderRadius: '6px 6px 0 0',
    transition: 'background 0.15s',
  },
  tabActive: {
    background: 'rgba(0, 102, 184, 0.06)',
    borderBottom: '2px solid #0066b8',
  },
  tabIcon: {
    fontSize: 14,
    lineHeight: 1,
  },
  tabLabel: {
    fontSize: 10,
    fontWeight: 500,
    color: '#6b7280',
  },
  // 内容区
  content: {
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
  },
};