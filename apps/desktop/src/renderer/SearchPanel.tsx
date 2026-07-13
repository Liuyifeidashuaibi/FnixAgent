/**
 * SearchPanel — 语义代码搜索面板
 *
 * 调用 @fnixagent/sdk 的 sdk.code.search({ query, top_k }) 命名空间,
 * 对接后端 /api/v1/coding/search(包装 IDEServer 的语义检索能力)。
 *
 * 功能:
 *   1. 搜索框(Enter 触发)+ top_k 选择器(5/10/20/50)
 *   2. 结果列表:文件路径 + 行号区间 + 代码片段 + 相似度
 *   3. 点击结果回调 onOpenFile,由编辑器层跳转到对应文件
 *   4. 状态:idle / loading / results / empty / error
 *   5. 浅色主题,样式与 index.css 的 CSS 变量对齐
 */
import { useState, type CSSProperties, type FormEvent } from 'react';
import { sdk } from '@fnixagent/sdk';

/* ================================================================
   Props
   ================================================================ */

export interface SearchPanelProps {
  /** 点击搜索结果时触发(打开文件) */
  onOpenFile?: (path: string, name: string) => void;
}

/* ================================================================
   结果类型(防御性解析后端返回)
   ================================================================ */

interface CodeSearchHit {
  /** 文件绝对/相对路径 */
  file: string;
  /** 文件名(由 path 推导) */
  name: string;
  /** 起始行(1-based,可选) */
  startLine?: number;
  /** 结束行(可选) */
  endLine?: number;
  /** 代码片段 */
  snippet?: string;
  /** 相似度分数(0~1,可选) */
  score?: number;
  [key: string]: unknown;
}

/* ================================================================
   主组件
   ================================================================ */

export function SearchPanel({ onOpenFile }: SearchPanelProps) {
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(10);
  const [results, setResults] = useState<CodeSearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const resp = await sdk.code.search({ query: q, top_k: topK });
      // CodingResponse: { success, message?, data? }
      const data = (resp as { data?: unknown }).data;
      const list = normalizeHits(data);
      setResults(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : '搜索失败');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  function handleOpen(hit: CodeSearchHit) {
    onOpenFile?.(hit.file, hit.name);
  }

  return (
    <div style={s.container}>
      {/* 标题栏 */}
      <div style={s.header}>
        <span style={s.title}>搜索</span>
      </div>

      {/* 搜索表单 */}
      <form style={s.form} onSubmit={handleSearch}>
        <input
          style={s.input}
          type="text"
          placeholder="语义搜索代码…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={loading}
          autoFocus
        />
        <select
          style={s.select}
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
          disabled={loading}
          title="返回结果数量"
        >
          <option value={5}>5</option>
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
        </select>
        <button
          type="submit"
          style={loading || !query.trim() ? s.btnDisabled : s.btn}
          disabled={loading || !query.trim()}
        >
          {loading ? '搜索中…' : '搜索'}
        </button>
      </form>

      {/* 结果区 */}
      <div style={s.resultArea}>
        {error ? (
          <div style={s.stateBox}>
            <span style={s.stateIcon} aria-hidden="true">⚠</span>
            <span style={s.stateText}>搜索失败:{error}</span>
          </div>
        ) : loading ? (
          <div style={s.stateBox}>
            <span style={s.spinner} aria-hidden="true" />
            <span style={s.stateText}>正在检索…</span>
          </div>
        ) : results.length === 0 ? (
          <div style={s.stateBox}>
            <span style={s.stateIcon} aria-hidden="true">⌕</span>
            <span style={s.stateText}>
              {hasSearched ? '未找到匹配的代码' : '输入关键词开始语义搜索'}
            </span>
          </div>
        ) : (
          <>
            <div style={s.resultMeta}>
              共 {results.length} 条结果
            </div>
            {results.map((hit, idx) => (
              <ResultCard key={`${hit.file}-${idx}`} hit={hit} onOpen={handleOpen} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

/* ================================================================
   结果卡片
   ================================================================ */

function ResultCard({ hit, onOpen }: { hit: CodeSearchHit; onOpen: (h: CodeSearchHit) => void }) {
  const lineLabel =
    hit.startLine != null
      ? hit.endLine != null && hit.endLine !== hit.startLine
        ? `L${hit.startLine}-${hit.endLine}`
        : `L${hit.startLine}`
      : null;

  const scorePct =
    typeof hit.score === 'number' && hit.score >= 0 && hit.score <= 1
      ? `${(hit.score * 100).toFixed(1)}%`
      : null;

  return (
    <div
      style={s.card}
      onClick={() => onOpen(hit)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(hit);
        }
      }}
    >
      <div style={s.cardHead}>
        <span style={s.fileName} title={hit.file}>
          {hit.name}
        </span>
        {lineLabel && <span style={s.lineBadge}>{lineLabel}</span>}
        {scorePct && <span style={s.scoreBadge}>{scorePct}</span>}
      </div>
      {hit.file !== hit.name && (
        <div style={s.filePath} title={hit.file}>
          {hit.file}
        </div>
      )}
      {hit.snippet && (
        <pre style={s.snippet}>
          {truncate(hit.snippet, 240)}
        </pre>
      )}
    </div>
  );
}

/* ================================================================
   工具函数
   ================================================================ */

/** 从后端 data 中防御性提取搜索结果数组 */
function normalizeHits(data: unknown): CodeSearchHit[] {
  if (!data) return [];
  // 直接数组
  if (Array.isArray(data)) return data.map(normalizeHit);
  // { results: [...] } / { hits: [...] } / { matches: [...] }
  if (typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    const arr = obj.results ?? obj.hits ?? obj.matches ?? obj.items;
    if (Array.isArray(arr)) return arr.map(normalizeHit);
  }
  return [];
}

/** 将任意对象映射为 CodeSearchHit(容错多种字段名) */
function normalizeHit(raw: unknown): CodeSearchHit {
  if (typeof raw !== 'object' || raw === null) {
    return { file: '', name: '' };
  }
  const o = raw as Record<string, unknown>;
  const file = String(
    o.file ?? o.path ?? o.filename ?? o.file_path ?? o.doc ?? '',
  );
  const name = file ? file.split(/[\\/]/).pop() ?? file : '';
  const startLine = toNumber(o.start_line ?? o.startLine ?? o.line ?? o.lineno);
  const endLine = toNumber(o.end_line ?? o.endLine ?? o.line_end);
  const snippet = String(o.snippet ?? o.content ?? o.text ?? o.code ?? '');
  const score = toNumber(o.score ?? o.similarity);
  return { file, name, startLine, endLine, snippet, score };
}

function toNumber(v: unknown): number | undefined {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string') {
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

function truncate(text: string, max: number): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  return clean.length > max ? clean.slice(0, max) + '…' : clean;
}

/* ================================================================
   样式
   ================================================================ */

const s: Record<string, CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: 'var(--bg-secondary)',
    userSelect: 'none',
    overflow: 'hidden',
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
  form: {
    display: 'flex',
    gap: 6,
    padding: '0 12px 8px',
    flexShrink: 0,
  },
  input: {
    flex: 1,
    height: 28,
    padding: '0 8px',
    border: '1px solid var(--border-color)',
    borderRadius: 4,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 12,
    fontFamily: 'var(--font-sans)',
    outline: 'none',
    transition: 'border-color 0.12s',
  },
  select: {
    height: 28,
    padding: '0 4px',
    border: '1px solid var(--border-color)',
    borderRadius: 4,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 12,
    cursor: 'pointer',
  },
  btn: {
    height: 28,
    padding: '0 12px',
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 500,
    transition: 'background 0.12s',
  },
  btnDisabled: {
    height: 28,
    padding: '0 12px',
    background: 'var(--bg-tertiary)',
    color: 'var(--text-tertiary)',
    border: 'none',
    borderRadius: 4,
    cursor: 'not-allowed',
    fontSize: 12,
    fontWeight: 500,
  },
  resultArea: {
    flex: 1,
    overflow: 'auto',
    padding: '0 12px 12px',
  },
  resultMeta: {
    fontSize: 11,
    color: 'var(--text-tertiary)',
    padding: '4px 0 8px',
    borderBottom: '1px solid var(--border-color)',
    marginBottom: 8,
  },
  card: {
    padding: '8px 10px',
    marginBottom: 6,
    background: 'var(--bg-primary)',
    border: '1px solid var(--border-color)',
    borderRadius: 6,
    cursor: 'pointer',
    transition: 'border-color 0.12s, background 0.12s',
  },
  cardHead: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    marginBottom: 2,
  },
  fileName: {
    fontSize: 12,
    fontWeight: 600,
    color: 'var(--accent)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    flex: 1,
    minWidth: 0,
  },
  lineBadge: {
    fontSize: 10,
    padding: '1px 6px',
    background: 'var(--bg-tertiary)',
    color: 'var(--text-secondary)',
    borderRadius: 3,
    flexShrink: 0,
    fontFamily: 'var(--font-mono)',
  },
  scoreBadge: {
    fontSize: 10,
    padding: '1px 6px',
    background: 'var(--accent-light)',
    color: 'var(--accent)',
    borderRadius: 3,
    flexShrink: 0,
  },
  filePath: {
    fontSize: 10,
    color: 'var(--text-tertiary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    marginBottom: 4,
  },
  snippet: {
    margin: 0,
    padding: '6px 8px',
    background: 'var(--bg-secondary)',
    borderRadius: 4,
    fontSize: 11,
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-primary)',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    lineHeight: 1.5,
    maxHeight: 80,
    overflow: 'hidden',
  },
  stateBox: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
    textAlign: 'center',
    gap: 10,
  },
  stateIcon: {
    fontSize: 28,
    color: 'var(--text-tertiary)',
    opacity: 0.6,
  },
  stateText: {
    color: 'var(--text-secondary)',
    fontSize: 12,
  },
  spinner: {
    width: 18,
    height: 18,
    border: '2px solid var(--border-color)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    display: 'inline-block',
    animation: 'search-spin 0.8s linear infinite',
  },
};

export default SearchPanel;
