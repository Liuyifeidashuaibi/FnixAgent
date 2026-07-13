/**
 * AgentOS 策略面板
 * 嵌入在 AgentPanel 中，展示策略规则、护栏和审计日志
 */
import { useEffect, useState } from 'react';

interface Policy {
  action?: string;
  effect?: string;
  subject?: string;
  priority?: number;
  [key: string]: unknown;
}

interface Guardrail {
  name?: string;
  description?: string;
  [key: string]: unknown;
}

interface AuditLog {
  timestamp?: string;
  action?: string;
  detail?: string;
  [key: string]: unknown;
}

import { API_BASE } from './apiConfig';

const AGENT_API = `${API_BASE}/api/v1/agentos`;

export function PolicyPanel() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [guardrails, setGuardrails] = useState<Guardrail[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    policies: true,
    guardrails: false,
    audit: false,
  });

  useEffect(() => {
    void (async () => {
      try {
        const [policyResp, guardResp, auditResp] = await Promise.all([
          fetch(`${AGENT_API}/policy/list`),
          fetch(`${AGENT_API}/guardrail/list`),
          fetch(`${AGENT_API}/audit?limit=20`),
        ]);

        const parse = async (resp: Response) => {
          if (!resp.ok) return [];
          const data = await resp.json();
          return Array.isArray(data) ? data : data.items ?? data.policies ?? data.guardrails ?? data.logs ?? [];
        };

        setPolicies(await parse(policyResp));
        setGuardrails(await parse(guardResp));
        setAuditLogs(await parse(auditResp));
      } catch (err) {
        console.error('加载策略数据失败', err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function toggleSection(section: string) {
    setExpanded((prev) => ({ ...prev, [section]: !prev[section] }));
  }

  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = `
      .policy-section-toggle:hover { background: rgba(0, 102, 184, 0.04) !important; }
      .policy-history-item:hover { background: rgba(0, 102, 184, 0.04) !important; }
    `;
    document.head.appendChild(style);
    return () => { document.head.removeChild(style); };
  }, []);

  if (loading) {
    return <div style={s.loading}>加载策略数据...</div>;
  }

  return (
    <div style={s.container}>
      {/* 策略规则 */}
      <div style={s.section}>
        <div
          style={s.sectionHeader}
          onClick={() => toggleSection('policies')}
          className="policy-section-toggle"
        >
          <span style={s.sectionTitle}>📋 策略规则</span>
          <span style={s.sectionCount}>{policies.length}</span>
          <span style={s.toggleArrow}>{expanded.policies ? '▾' : '▸'}</span>
        </div>
        {expanded.policies && (
          <div style={s.sectionContent}>
            {policies.length === 0 ? (
              <div style={s.empty}>暂无策略规则</div>
            ) : (
              policies.map((p, idx) => (
                <div key={p.action ?? idx} style={s.policyCard}>
                  <div style={s.policyRow}>
                    {p.action && <span style={s.policyAction}>{p.action}</span>}
                    {p.effect && (
                      <span style={p.effect === 'allow' ? s.effectAllow : s.effectDeny}>
                        {p.effect}
                      </span>
                    )}
                    {p.priority != null && (
                      <span style={s.priority}>P{p.priority}</span>
                    )}
                  </div>
                  {p.subject && <div style={s.policySubject}>{p.subject}</div>}
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* 护栏 */}
      <div style={s.section}>
        <div
          style={s.sectionHeader}
          onClick={() => toggleSection('guardrails')}
          className="policy-section-toggle"
        >
          <span style={s.sectionTitle}>🛡️ 护栏</span>
          <span style={s.sectionCount}>{guardrails.length}</span>
          <span style={s.toggleArrow}>{expanded.guardrails ? '▾' : '▸'}</span>
        </div>
        {expanded.guardrails && (
          <div style={s.sectionContent}>
            {guardrails.length === 0 ? (
              <div style={s.empty}>暂无护栏规则</div>
            ) : (
              guardrails.map((g, idx) => (
                <div key={g.name ?? idx} style={s.guardrailCard}>
                  <div style={s.guardrailName}>{g.name ?? '未命名'}</div>
                  {g.description && (
                    <div style={s.guardrailDesc}>{g.description}</div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* 审计日志 */}
      <div style={s.section}>
        <div
          style={s.sectionHeader}
          onClick={() => toggleSection('audit')}
          className="policy-section-toggle"
        >
          <span style={s.sectionTitle}>📜 审计日志</span>
          <span style={s.sectionCount}>{auditLogs.length}</span>
          <span style={s.toggleArrow}>{expanded.audit ? '▾' : '▸'}</span>
        </div>
        {expanded.audit && (
          <div style={s.sectionContent}>
            {auditLogs.length === 0 ? (
              <div style={s.empty}>暂无审计日志</div>
            ) : (
              auditLogs.map((log, idx) => (
                <div
                  key={idx}
                  style={s.auditItem}
                  className="policy-history-item"
                >
                  <div style={s.auditRow}>
                    <span style={s.auditTime}>
                      {log.timestamp
                        ? new Date(log.timestamp).toLocaleString('zh-CN')
                        : '-'}
                    </span>
                    {log.action && <span style={s.auditAction}>{log.action}</span>}
                  </div>
                  {log.detail && <div style={s.auditDetail}>{log.detail}</div>}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    padding: 8,
    overflowY: 'auto',
  },
  loading: {
    padding: 16,
    fontSize: 12,
    color: '#6b7280',
    textAlign: 'center',
  },
  section: {
    border: '1px solid #e4e4e7',
    borderRadius: 8,
    background: '#ffffff',
    overflow: 'hidden',
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 10px',
    cursor: 'pointer',
    userSelect: 'none',
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: 600,
    color: '#28282c',
    flex: 1,
  },
  sectionCount: {
    fontSize: 10,
    color: '#9ca3af',
    background: '#f4f5f7',
    padding: '1px 6px',
    borderRadius: 10,
  },
  toggleArrow: {
    fontSize: 11,
    color: '#6b7280',
    width: 14,
    textAlign: 'center',
  },
  sectionContent: {
    padding: '0 10px 10px',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  empty: {
    padding: 8,
    fontSize: 12,
    color: '#9ca3af',
    textAlign: 'center',
  },
  // 策略卡片
  policyCard: {
    padding: 8,
    background: '#f4f5f7',
    borderRadius: 6,
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  policyRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    flexWrap: 'wrap',
  },
  policyAction: {
    fontSize: 12,
    fontWeight: 600,
    color: '#28282c',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
  },
  effectAllow: {
    fontSize: 10,
    fontWeight: 600,
    padding: '1px 6px',
    borderRadius: 10,
    background: '#dcfce7',
    color: '#166534',
  },
  effectDeny: {
    fontSize: 10,
    fontWeight: 600,
    padding: '1px 6px',
    borderRadius: 10,
    background: '#fef2f2',
    color: '#dc2626',
  },
  priority: {
    fontSize: 10,
    fontWeight: 600,
    color: '#0066b8',
    background: 'rgba(0, 102, 184, 0.08)',
    padding: '1px 6px',
    borderRadius: 10,
  },
  policySubject: {
    fontSize: 11,
    color: '#6b7280',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
  },
  // 护栏
  guardrailCard: {
    padding: 8,
    background: '#f4f5f7',
    borderRadius: 6,
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  guardrailName: {
    fontSize: 12,
    fontWeight: 600,
    color: '#28282c',
  },
  guardrailDesc: {
    fontSize: 11,
    color: '#6b7280',
    lineHeight: 1.4,
  },
  // 审计
  auditItem: {
    padding: '6px 8px',
    borderRadius: 4,
    cursor: 'default',
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  auditRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  auditTime: {
    fontSize: 10,
    color: '#9ca3af',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
    whiteSpace: 'nowrap',
  },
  auditAction: {
    fontSize: 11,
    fontWeight: 600,
    color: '#28282c',
  },
  auditDetail: {
    fontSize: 11,
    color: '#6b7280',
    lineHeight: 1.4,
  },
};