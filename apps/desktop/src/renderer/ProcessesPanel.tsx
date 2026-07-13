/**
 * AgentOS 进程面板
 * 嵌入在 AgentPanel 中，展示进程列表，支持 Kill 操作
 */
import { useEffect, useState, useCallback } from 'react';

interface Process {
  name: string;
  pid: number;
  state: string;
  priority: number;
  cpu_time?: number;
  [key: string]: unknown;
}

import { API_BASE } from './apiConfig';

const AGENT_API = `${API_BASE}/api/v1/agentos`;

export function ProcessesPanel() {
  const [processes, setProcesses] = useState<Process[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProcesses = useCallback(async () => {
    try {
      const resp = await fetch(`${AGENT_API}/ps`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const list = Array.isArray(data) ? data : data.processes ?? [];
      setProcesses(list);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取进程列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProcesses();
    const timer = setInterval(fetchProcesses, 3000);
    return () => clearInterval(timer);
  }, [fetchProcesses]);

  async function handleKill(pid: number) {
    try {
      const resp = await fetch(`${AGENT_API}/kill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid, reason: '手动终止' }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      await fetchProcesses();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Kill 失败');
    }
  }

  const stateBadge: Record<string, { bg: string; color: string; label: string }> = {
    RUNNING: { bg: '#dcfce7', color: '#166534', label: '运行中' },
    BLOCKED: { bg: '#fff7ed', color: '#9a3412', label: '阻塞' },
    TERMINATED: { bg: '#f3f4f6', color: '#6b7280', label: '已终止' },
    default: { bg: '#f3f4f6', color: '#6b7280', label: '未知' },
  };

  if (loading && processes.length === 0) {
    return <div style={s.loading}>加载进程列表...</div>;
  }

  return (
    <div style={s.container}>
      {error && <div style={s.error}>{error}</div>}

      {processes.length === 0 ? (
        <div style={s.empty}>
          <span style={s.emptyIcon}>🤖</span>
          <span>没有运行中的 Agent</span>
        </div>
      ) : (
        processes.map((proc) => {
          const badge = stateBadge[proc.state] ?? stateBadge.default;
          return (
            <div key={proc.pid} style={s.card}>
              <div style={s.cardRow}>
                <span style={s.name}>{proc.name}</span>
                <span style={s.pid}>PID {proc.pid}</span>
              </div>
              <div style={s.cardRow}>
                <span style={{ ...s.badge, background: badge.bg, color: badge.color }}>
                  {badge.label}
                </span>
                <span style={s.meta}>优先级 {proc.priority}</span>
                {proc.cpu_time != null && (
                  <span style={s.meta}>CPU {proc.cpu_time}s</span>
                )}
              </div>
              <div style={s.cardRow}>
                <button
                  style={s.killBtn}
                  onClick={() => handleKill(proc.pid)}
                  title={`终止进程 ${proc.pid}`}
                >
                  Kill
                </button>
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    padding: 8,
  },
  loading: {
    padding: 16,
    fontSize: 12,
    color: '#6b7280',
    textAlign: 'center',
  },
  error: {
    padding: '8px 10px',
    fontSize: 12,
    color: '#dc2626',
    background: '#fef2f2',
    border: '1px solid #fecaca',
    borderRadius: 6,
  },
  empty: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 8,
    padding: 24,
    fontSize: 13,
    color: '#9ca3af',
  },
  emptyIcon: { fontSize: 32, opacity: 0.5 },
  card: {
    padding: 10,
    background: '#ffffff',
    border: '1px solid #e4e4e7',
    borderRadius: 8,
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  cardRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
  },
  name: {
    fontSize: 13,
    fontWeight: 600,
    color: '#28282c',
  },
  pid: {
    fontSize: 11,
    color: '#9ca3af',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
  },
  badge: {
    fontSize: 10,
    fontWeight: 600,
    padding: '1px 6px',
    borderRadius: 10,
  },
  meta: {
    fontSize: 11,
    color: '#6b7280',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
  },
  killBtn: {
    background: 'transparent',
    border: '1px solid #fecaca',
    color: '#dc2626',
    fontSize: 10,
    fontWeight: 600,
    padding: '2px 8px',
    borderRadius: 4,
    cursor: 'pointer',
  },
};