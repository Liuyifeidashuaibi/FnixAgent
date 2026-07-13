/**
 * AgentProcessPanel — Agent 进程管理面板
 *
 * 功能:
 *   1. 进程列表: POST /api/v1/agentos/ps (JWT 鉴权,失败则显示 mock 数据)
 *   2. 进程详情(展开): 父进程 PID、Capabilities、创建时间、内存使用、Kill 按钮
 *   3. 生成新进程: 名称、优先级下拉、Capabilities 多选
 *   4. 自动刷新: 每 5 秒轮询,面板不可见时停止
 *   5. 状态徽章: running=绿, completed=蓝, failed=红
 *
 * 可同时用于:
 *   - Sidebar 左侧面板(260px)
 *   - StudioLayout 右侧 Agent 面板(320px)
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { auth } from '@officeagent/sdk';
import { API_BASE } from './apiConfig';

const AGENT_API = `${API_BASE}/api/v1/agentos`;

/* ================================================
   Types
   ================================================ */

interface AgentProcess {
  pid: string;
  name: string;
  status: 'running' | 'completed' | 'failed';
  priority: 'low' | 'normal' | 'high' | 'critical';
  uptime: number; // 秒
  parent_pid: string | null;
  capabilities: string[];
  created_at: string;
  memory_mb: number;
}

interface AgentProcessPanelProps {
  onOpenFile?: (path: string, name: string) => void;
}

/* ================================================
   Mock Data
   ================================================ */

const MOCK_PROCESSES: AgentProcess[] = [
  {
    pid: '1001',
    name: 'code-reviewer',
    status: 'running',
    priority: 'high',
    uptime: 3720,
    parent_pid: null,
    capabilities: ['code_analysis', 'linting', 'suggestion'],
    created_at: '2026-07-13T08:30:00Z',
    memory_mb: 128.5,
  },
  {
    pid: '1002',
    name: 'doc-generator',
    status: 'completed',
    priority: 'normal',
    uptime: 540,
    parent_pid: '1001',
    capabilities: ['documentation', 'markdown'],
    created_at: '2026-07-13T09:00:00Z',
    memory_mb: 64.2,
  },
  {
    pid: '1003',
    name: 'test-runner',
    status: 'failed',
    priority: 'critical',
    uptime: 120,
    parent_pid: null,
    capabilities: ['testing', 'coverage'],
    created_at: '2026-07-13T09:15:00Z',
    memory_mb: 256.0,
  },
  {
    pid: '1004',
    name: 'file-indexer',
    status: 'running',
    priority: 'low',
    uptime: 9000,
    parent_pid: null,
    capabilities: ['file_watch', 'indexing', 'search'],
    created_at: '2026-07-13T05:00:00Z',
    memory_mb: 512.3,
  },
];

/* ================================================
   Helpers
   ================================================ */

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function formatMemory(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb.toFixed(1)} MB`;
}

const STATUS_BADGE: Record<string, { bg: string; color: string; label: string }> = {
  running: { bg: '#dcfce7', color: '#166534', label: '运行中' },
  completed: { bg: '#dbeafe', color: '#1e40af', label: '已完成' },
  failed: { bg: '#fee2e2', color: '#991b1b', label: '失败' },
};

const PRIORITY_COLORS: Record<string, string> = {
  low: '#6b7280',
  normal: '#2563eb',
  high: '#f59e0b',
  critical: '#dc2626',
};

const ALL_CAPABILITIES = [
  'code_analysis',
  'linting',
  'suggestion',
  'documentation',
  'markdown',
  'testing',
  'coverage',
  'file_watch',
  'indexing',
  'search',
  'refactoring',
  'debugging',
];

/* ================================================
   AgentProcessPanel Component
   ================================================ */

export const AgentProcessPanel: React.FC<AgentProcessPanelProps> = ({ onOpenFile: _onOpenFile }) => {
  const [processes, setProcesses] = useState<AgentProcess[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedPid, setExpandedPid] = useState<string | null>(null);
  const [showSpawnForm, setShowSpawnForm] = useState(false);
  const [usingMock, setUsingMock] = useState(false);
  const [killing, setKilling] = useState<string | null>(null);

  /* ---- Spawn form state ---- */
  const [spawnName, setSpawnName] = useState('');
  const [spawnPriority, setSpawnPriority] = useState<string>('normal');
  const [spawnCapabilities, setSpawnCapabilities] = useState<string[]>([]);
  const [spawning, setSpawning] = useState(false);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  /* ---- Fetch processes ---- */
  const fetchProcesses = useCallback(async () => {
    try {
      const token = await auth.getAccessToken();
      if (!token) {
        /* 未登录 → mock */
        setProcesses(MOCK_PROCESSES);
        setUsingMock(true);
        setError(null);
        setLoading(false);
        return;
      }

      const resp = await fetch(`${AGENT_API}/ps`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      });

      if (!resp.ok) {
        if (resp.status === 401 || resp.status === 403) {
          setProcesses(MOCK_PROCESSES);
          setUsingMock(true);
        } else {
          setError(`HTTP ${resp.status}`);
        }
        setLoading(false);
        return;
      }

      const data = await resp.json();
      const list: AgentProcess[] = Array.isArray(data)
        ? data
        : data.processes ?? data.data ?? [];

      setProcesses(list);
      setUsingMock(false);
      setError(null);
    } catch {
      setProcesses(MOCK_PROCESSES);
      setUsingMock(true);
      setError(null);
    } finally {
      setLoading(false);
    }
  }, []);

  /* ---- Auto-refresh with visibility check ---- */
  useEffect(() => {
    fetchProcesses();

    intervalRef.current = setInterval(() => {
      /* 简易可见性检测: DOM 中且未 display:none */
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          fetchProcesses();
        }
      }
    }, 5000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchProcesses]);

  /* ---- Kill process ---- */
  const handleKill = useCallback(
    async (pid: string) => {
      setKilling(pid);
      try {
        const token = await auth.getAccessToken();
        if (!token) {
          setError('需要登录才能终止进程');
          setKilling(null);
          return;
        }

        const resp = await fetch(`${AGENT_API}/kill`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ pid, reason: '手动终止' }),
        });

        if (!resp.ok) {
          setError(`终止进程失败: HTTP ${resp.status}`);
        } else {
          setProcesses((prev) => prev.filter((p) => p.pid !== pid));
          if (expandedPid === pid) setExpandedPid(null);
        }
      } catch {
        setError('终止进程失败: 网络错误');
      } finally {
        setKilling(null);
      }
    },
    [expandedPid],
  );

  /* ---- Spawn process ---- */
  const handleSpawn = useCallback(async () => {
    if (!spawnName.trim()) return;
    setSpawning(true);
    try {
      const token = await auth.getAccessToken();
      if (!token) {
        setError('需要登录才能生成进程');
        setSpawning(false);
        return;
      }

      const resp = await fetch(`${AGENT_API}/spawn`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: spawnName.trim(),
          priority: spawnPriority,
          capabilities: spawnCapabilities,
        }),
      });

      if (!resp.ok) {
        setError(`生成进程失败: HTTP ${resp.status}`);
      } else {
        setSpawnName('');
        setSpawnPriority('normal');
        setSpawnCapabilities([]);
        setShowSpawnForm(false);
        await fetchProcesses();
      }
    } catch {
      setError('生成进程失败: 网络错误');
    } finally {
      setSpawning(false);
    }
  }, [spawnName, spawnPriority, spawnCapabilities, fetchProcesses]);

  /* ---- Toggle capability ---- */
  const toggleCapability = useCallback((cap: string) => {
    setSpawnCapabilities((prev) =>
      prev.includes(cap) ? prev.filter((c) => c !== cap) : [...prev, cap],
    );
  }, []);

  /* ---- Render ---- */
  return (
    <div ref={containerRef} style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.title}>进程</span>
          {usingMock && <span style={styles.mockBadge}>DEMO</span>}
        </div>
        <div style={styles.headerActions}>
          <button
            style={styles.headerBtn}
            onClick={fetchProcesses}
            title="刷新"
          >
            ↻
          </button>
          <button
            style={{
              ...styles.headerBtn,
              ...(showSpawnForm ? styles.headerBtnActive : {}),
            }}
            onClick={() => setShowSpawnForm((v) => !v)}
            title="生成进程"
          >
            +
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={styles.errorBar}>
          <span>{error}</span>
          <button style={styles.errorClose} onClick={() => setError(null)}>
            ×
          </button>
        </div>
      )}

      {/* Spawn Form */}
      {showSpawnForm && (
        <div style={styles.spawnForm}>
          <input
            style={styles.input}
            placeholder="进程名称"
            value={spawnName}
            onChange={(e) => setSpawnName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSpawn();
            }}
          />
          <div style={styles.spawnRow}>
            <label style={styles.spawnLabel}>优先级</label>
            <select
              style={styles.select}
              value={spawnPriority}
              onChange={(e) => setSpawnPriority(e.target.value)}
            >
              <option value="low">低</option>
              <option value="normal">普通</option>
              <option value="high">高</option>
              <option value="critical">紧急</option>
            </select>
          </div>
          <div style={styles.spawnCapSection}>
            <label style={styles.spawnLabel}>Capabilities</label>
            <div style={styles.capGrid}>
              {ALL_CAPABILITIES.map((cap) => (
                <button
                  key={cap}
                  style={{
                    ...styles.capChip,
                    ...(spawnCapabilities.includes(cap)
                      ? styles.capChipActive
                      : {}),
                  }}
                  onClick={() => toggleCapability(cap)}
                >
                  {cap}
                </button>
              ))}
            </div>
          </div>
          <div style={styles.spawnActions}>
            <button
              style={styles.cancelBtn}
              onClick={() => {
                setShowSpawnForm(false);
                setSpawnName('');
                setSpawnCapabilities([]);
              }}
            >
              取消
            </button>
            <button
              style={styles.spawnBtn}
              onClick={handleSpawn}
              disabled={!spawnName.trim() || spawning}
            >
              {spawning ? '...' : '生成'}
            </button>
          </div>
        </div>
      )}

      {/* Process List */}
      <div style={styles.list}>
        {loading && processes.length === 0 ? (
          <div style={styles.emptyState}>
            <p style={styles.emptyText}>加载中...</p>
          </div>
        ) : processes.length === 0 ? (
          <div style={styles.emptyState}>
            <p style={styles.emptyText}>暂无活跃进程</p>
            <p style={styles.hint}>点击 + 生成新进程</p>
          </div>
        ) : (
          processes.map((proc) => {
            const badge = STATUS_BADGE[proc.status] ?? {
              bg: '#f3f4f6',
              color: '#6b7280',
              label: '未知',
            };
            const isExpanded = expandedPid === proc.pid;

            return (
              <div key={proc.pid} style={styles.processCard}>
                {/* Summary Row */}
                <div
                  style={styles.processRow}
                  onClick={() =>
                    setExpandedPid(isExpanded ? null : proc.pid)
                  }
                >
                  <div style={styles.processMain}>
                    <span style={styles.processName}>{proc.name}</span>
                    <span style={styles.processPid}>PID {proc.pid}</span>
                  </div>
                  <div style={styles.processMeta}>
                    <span
                      style={{
                        ...styles.statusBadge,
                        background: badge.bg,
                        color: badge.color,
                      }}
                    >
                      {badge.label}
                    </span>
                    <span
                      style={{
                        ...styles.priorityTag,
                        color: PRIORITY_COLORS[proc.priority] ?? '#6b7280',
                      }}
                    >
                      {proc.priority}
                    </span>
                    <span style={styles.uptime}>
                      {proc.status === 'running'
                        ? formatUptime(proc.uptime)
                        : formatTime(proc.created_at)}
                    </span>
                    <span style={styles.expandIcon}>
                      {isExpanded ? '▾' : '▸'}
                    </span>
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div style={styles.details}>
                    <div style={styles.detailGrid}>
                      {proc.parent_pid && (
                        <div style={styles.detailItem}>
                          <span style={styles.detailLabel}>父进程</span>
                          <span style={styles.detailValue}>
                            PID {proc.parent_pid}
                          </span>
                        </div>
                      )}
                      <div style={styles.detailItem}>
                        <span style={styles.detailLabel}>创建时间</span>
                        <span style={styles.detailValue}>
                          {formatTime(proc.created_at)}
                        </span>
                      </div>
                      <div style={styles.detailItem}>
                        <span style={styles.detailLabel}>内存</span>
                        <span style={styles.detailValue}>
                          {formatMemory(proc.memory_mb)}
                        </span>
                      </div>
                    </div>
                    {proc.capabilities.length > 0 && (
                      <div style={styles.detailCaps}>
                        <span style={styles.detailLabel}>Capabilities</span>
                        <div style={styles.detailCapList}>
                          {proc.capabilities.map((cap) => (
                            <span key={cap} style={styles.detailCapChip}>
                              {cap}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    <button
                      style={styles.killBtn}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleKill(proc.pid);
                      }}
                      disabled={killing === proc.pid}
                    >
                      {killing === proc.pid ? '终止中...' : '终止进程'}
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

/* ================================================
   Styles
   ================================================ */

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: 'var(--bg-secondary)',
    userSelect: 'none',
    fontFamily: 'var(--font-sans)',
  },
  /* Header */
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 12px',
    flexShrink: 0,
    borderBottom: '1px solid var(--border-color)',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  title: {
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  mockBadge: {
    fontSize: 9,
    fontWeight: 600,
    padding: '1px 5px',
    borderRadius: 3,
    background: '#fef3c7',
    color: '#92400e',
    letterSpacing: 0.3,
  },
  headerActions: {
    display: 'flex',
    gap: 2,
  },
  headerBtn: {
    background: 'transparent',
    border: 'none',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    fontSize: 14,
    padding: '2px 6px',
    borderRadius: 4,
    lineHeight: 1,
    transition: 'background 0.1s',
  },
  headerBtnActive: {
    background: 'var(--accent-light)',
    color: 'var(--accent)',
  },
  /* Error */
  errorBar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 10px',
    fontSize: 11,
    color: 'var(--error)',
    background: '#fef2f2',
    borderBottom: '1px solid #fecaca',
    flexShrink: 0,
  },
  errorClose: {
    background: 'transparent',
    border: 'none',
    color: 'var(--error)',
    cursor: 'pointer',
    fontSize: 14,
    padding: '0 2px',
    lineHeight: 1,
  },
  /* Spawn Form */
  spawnForm: {
    padding: '10px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    borderBottom: '1px solid var(--border-color)',
    background: 'var(--bg-primary)',
    flexShrink: 0,
  },
  input: {
    padding: '5px 8px',
    fontSize: 12,
    border: '1px solid var(--border-color)',
    borderRadius: 4,
    background: 'var(--bg-secondary)',
    color: 'var(--text-primary)',
    outline: 'none',
    fontFamily: 'var(--font-sans)',
  },
  spawnRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  spawnLabel: {
    fontSize: 11,
    color: 'var(--text-secondary)',
    flexShrink: 0,
    minWidth: 56,
  },
  select: {
    padding: '4px 6px',
    fontSize: 11,
    border: '1px solid var(--border-color)',
    borderRadius: 4,
    background: 'var(--bg-secondary)',
    color: 'var(--text-primary)',
    outline: 'none',
    flex: 1,
    fontFamily: 'var(--font-sans)',
  },
  spawnCapSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  capGrid: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 4,
  },
  capChip: {
    padding: '2px 7px',
    fontSize: 10,
    border: '1px solid var(--border-color)',
    borderRadius: 10,
    background: 'var(--bg-secondary)',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
    transition: 'background 0.1s, color 0.1s, border-color 0.1s',
  },
  capChipActive: {
    background: 'var(--accent-light)',
    color: 'var(--accent)',
    borderColor: 'var(--accent)',
  },
  spawnActions: {
    display: 'flex',
    gap: 6,
    justifyContent: 'flex-end',
  },
  cancelBtn: {
    padding: '4px 12px',
    fontSize: 11,
    background: 'transparent',
    border: '1px solid var(--border-color)',
    borderRadius: 4,
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    fontFamily: 'var(--font-sans)',
  },
  spawnBtn: {
    padding: '4px 12px',
    fontSize: 11,
    fontWeight: 500,
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontFamily: 'var(--font-sans)',
  },
  /* List */
  list: {
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    padding: '4px 0',
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
  /* Process Card */
  processCard: {
    borderBottom: '1px solid var(--border-color)',
    cursor: 'pointer',
    transition: 'background 0.1s',
  },
  processRow: {
    display: 'flex',
    flexDirection: 'column',
    padding: '8px 12px',
    gap: 4,
  },
  processMain: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  processName: {
    fontSize: 12,
    fontWeight: 600,
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
  },
  processPid: {
    fontSize: 10,
    color: 'var(--text-tertiary)',
    fontFamily: 'var(--font-mono)',
  },
  processMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  statusBadge: {
    fontSize: 10,
    fontWeight: 600,
    padding: '1px 6px',
    borderRadius: 10,
    lineHeight: '16px',
  },
  priorityTag: {
    fontSize: 10,
    fontWeight: 500,
    fontFamily: 'var(--font-mono)',
    textTransform: 'uppercase',
  },
  uptime: {
    fontSize: 10,
    color: 'var(--text-tertiary)',
    fontFamily: 'var(--font-mono)',
    marginLeft: 'auto',
  },
  expandIcon: {
    fontSize: 10,
    color: 'var(--text-tertiary)',
  },
  /* Details */
  details: {
    padding: '8px 12px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    background: 'var(--bg-primary)',
    borderTop: '1px solid var(--border-color)',
  },
  detailGrid: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '6px 16px',
  },
  detailItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: 1,
  },
  detailLabel: {
    fontSize: 9,
    fontWeight: 600,
    textTransform: 'uppercase',
    color: 'var(--text-tertiary)',
    letterSpacing: 0.3,
  },
  detailValue: {
    fontSize: 11,
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
  },
  detailCaps: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  detailCapList: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 4,
  },
  detailCapChip: {
    padding: '1px 7px',
    fontSize: 10,
    border: '1px solid var(--border-color)',
    borderRadius: 10,
    background: 'var(--bg-secondary)',
    color: 'var(--text-secondary)',
    fontFamily: 'var(--font-mono)',
  },
  killBtn: {
    alignSelf: 'flex-start',
    padding: '3px 10px',
    fontSize: 10,
    fontWeight: 600,
    background: 'transparent',
    border: '1px solid #fecaca',
    color: 'var(--error)',
    borderRadius: 4,
    cursor: 'pointer',
    fontFamily: 'var(--font-sans)',
    transition: 'background 0.1s',
  },
};