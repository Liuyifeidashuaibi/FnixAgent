/**
 * AgentOS 记忆面板
 * 嵌入在 AgentPanel 中，提供记忆搜索（recall）功能
 */
import { useState, type FormEvent } from 'react';

interface MemoryResult {
  content: string;
  score: number;
  layer?: string;
  id?: string;
  [key: string]: unknown;
}

const API_BASE = 'http://localhost:8000/api/v1/agentos/mem';

export function MemoryPanel() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MemoryResult[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q || loading) return;

    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/recall`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: q,
          layers: ['working', 'episodic'],
          top_k: 5,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const list = Array.isArray(data) ? data : data.results ?? [];
      setResults(list);
    } catch (err) {
      console.error('记忆搜索失败', err);
    } finally {
      setLoading(false);
    }
  }

  function truncateContent(content: string, maxLen = 120) {
    if (!content) return '';
    return content.length > maxLen ? content.slice(0, maxLen) + '...' : content;
  }

  return (
    <div style={s.container}>
      <form style={s.searchForm} onSubmit={handleSearch}>
        <input
          style={s.searchInput}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索记忆..."
          disabled={loading}
        />
        <button
          type="submit"
          style={loading || !query.trim() ? s.searchBtnDisabled : s.searchBtn}
          disabled={loading || !query.trim()}
        >
          {loading ? '搜索中...' : '搜索'}
        </button>
      </form>

      <div style={s.resultsList}>
        {results.length === 0 ? (
          <div style={s.empty}>
            <span style={s.emptyIcon}>🧠</span>
            <span>{query ? '未找到相关记忆' : '搜索记忆...'}</span>
          </div>
        ) : (
          results.map((result, idx) => (
            <div key={result.id ?? idx} style={s.resultCard}>
              <div style={s.resultContent}>{truncateContent(String(result.content ?? ''))}</div>
              <div style={s.resultMeta}>
                {result.layer && <span style={s.layerBadge}>{result.layer}</span>}
                <span style={s.score}>相似度: {(result.score * 100).toFixed(1)}%</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    padding: 8,
    gap: 12,
  },
  searchForm: {
    display: 'flex',
    gap: 8,
  },
  searchInput: {
    flex: 1,
    padding: '8px 10px',
    background: '#ffffff',
    border: '1px solid #e4e4e7',
    borderRadius: 6,
    fontSize: 13,
    color: '#28282c',
    outline: 'none',
    fontFamily: 'inherit',
  },
  searchBtn: {
    padding: '8px 16px',
    background: '#0066b8',
    color: '#ffffff',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  searchBtnDisabled: {
    padding: '8px 16px',
    background: '#ebecee',
    color: '#9ca3af',
    border: 'none',
    borderRadius: 6,
    cursor: 'not-allowed',
    fontSize: 13,
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  resultsList: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    overflowY: 'auto',
  },
  empty: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 8,
    padding: 32,
    fontSize: 13,
    color: '#9ca3af',
  },
  emptyIcon: { fontSize: 32, opacity: 0.5 },
  resultCard: {
    padding: 10,
    background: '#ffffff',
    border: '1px solid #e4e4e7',
    borderRadius: 8,
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  resultContent: {
    fontSize: 13,
    color: '#28282c',
    lineHeight: 1.5,
  },
  resultMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    paddingTop: 4,
  },
  layerBadge: {
    fontSize: 10,
    fontWeight: 600,
    padding: '1px 6px',
    background: 'rgba(0, 102, 184, 0.08)',
    color: '#0066b8',
    borderRadius: 10,
  },
  score: {
    fontSize: 11,
    color: '#6b7280',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
  },
};
