import { useCallback, useState } from 'react';
import { sdk } from '@fnixagent/sdk';
import type { AgentOSResponse } from '@fnixagent/sdk';
import {
  Badge,
  Button,
  Input,
  ScrollArea,
  Spinner,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  cn,
} from '@fnixagent/ui';

/**
 * MemoryPanel — Agent 记忆面板
 *
 * 对接 sdk.agentos.memRecall / memSearch / memStore
 * 功能:
 *   - Tabs: Recall / Search / Store
 *   - Recall: 搜索 + layers 多选 + top_k 滑块;结果卡片(content + layer badge + score + memory_id)
 *   - Search: 搜索 + layer 单选 + top_k;结果卡片
 *   - Store: textarea + layer 选择 + 存储按钮;成功提示
 */

const LAYERS = ['working', 'episodic', 'semantic'] as const;
type Layer = (typeof LAYERS)[number];

interface MemoryItem {
  memory_id: string;
  content: string;
  layer: string;
  score?: number;
}

// 从响应中提取记忆列表
function extractMemories(resp: AgentOSResponse): MemoryItem[] {
  const data = resp.data;
  const arr: unknown[] = Array.isArray(data)
    ? data
    : data && typeof data === 'object'
      ? (() => {
          const o = data as Record<string, unknown>;
          return (
            (Array.isArray(o.memories) ? o.memories : null) ??
            (Array.isArray(o.items) ? o.items : null) ??
            (Array.isArray(o.results) ? o.results : null) ??
            (Array.isArray(o.matches) ? o.matches : null) ??
            []
          );
        })()
      : [];
  return arr.map((raw) => {
    const o = (raw ?? {}) as Record<string, unknown>;
    return {
      memory_id: String(o.memory_id ?? o.id ?? ''),
      content: String(o.content ?? o.text ?? ''),
      layer: String(o.layer ?? 'working'),
      score: typeof o.score === 'number' ? o.score : undefined,
    } satisfies MemoryItem;
  });
}

function layerBadgeVariant(layer: string) {
  switch (layer) {
    case 'working':
      return 'secondary' as const;
    case 'episodic':
      return 'success' as const;
    case 'semantic':
      return 'warning' as const;
    default:
      return 'outline' as const;
  }
}

export function MemoryPanel() {
  const [tab, setTab] = useState<'recall' | 'search' | 'store'>('recall');

  return (
    <div className="flex h-full flex-col bg-background">
      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)} className="flex h-full flex-col">
        <div className="border-b border-border px-2 pt-2 shrink-0">
          <TabsList>
            <TabsTrigger value="recall">Recall</TabsTrigger>
            <TabsTrigger value="search">Search</TabsTrigger>
            <TabsTrigger value="store">Store</TabsTrigger>
          </TabsList>
        </div>
        <div className="flex-1 min-h-0">
          <TabsContent value="recall" className="mt-0 h-full">
            <RecallTab />
          </TabsContent>
          <TabsContent value="search" className="mt-0 h-full">
            <SearchTab />
          </TabsContent>
          <TabsContent value="store" className="mt-0 h-full">
            <StoreTab />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

// ============ Recall Tab ============

function RecallTab() {
  const [query, setQuery] = useState('');
  const [layers, setLayers] = useState<Set<Layer>>(new Set(LAYERS));
  const [topK, setTopK] = useState(5);
  const [results, setResults] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const toggleLayer = (l: Layer) => {
    setLayers((s) => {
      const n = new Set(s);
      if (n.has(l)) n.delete(l);
      else n.add(l);
      return n;
    });
  };

  const run = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const resp = await sdk.agentos.memRecall({
        query: q,
        layers: layers.size > 0 ? Array.from(layers) : undefined,
        top_k: topK,
      });
      setResults(extractMemories(resp));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [query, layers, topK]);

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 border-b border-border px-3 py-2 shrink-0">
        <div className="flex gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void run();
            }}
            placeholder="输入查询..."
            className="h-8 text-xs"
          />
          <Button size="sm" onClick={() => void run()} disabled={loading || !query.trim()}>
            {loading ? <Spinner size="sm" /> : 'Recall'}
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {LAYERS.map((l) => (
            <label key={l} className="flex items-center gap-1 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={layers.has(l)}
                onChange={() => toggleLayer(l)}
                className="accent-[hsl(var(--primary))]"
              />
              {l}
            </label>
          ))}
          <label className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
            top_k
            <input
              type="range"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-20 accent-[hsl(var(--primary))]"
            />
            <span className="font-mono w-5 text-right">{topK}</span>
          </label>
        </div>
      </div>
      <ResultList results={results} loading={loading} error={error} searched={searched} />
    </div>
  );
}

// ============ Search Tab ============

function SearchTab() {
  const [query, setQuery] = useState('');
  const [layer, setLayer] = useState<Layer>('working');
  const [topK, setTopK] = useState(5);
  const [results, setResults] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const run = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const resp = await sdk.agentos.memSearch({ query: q, layer, top_k: topK });
      setResults(extractMemories(resp));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [query, layer, topK]);

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 border-b border-border px-3 py-2 shrink-0">
        <div className="flex gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void run();
            }}
            placeholder="输入查询..."
            className="h-8 text-xs"
          />
          <Button size="sm" onClick={() => void run()} disabled={loading || !query.trim()}>
            {loading ? <Spinner size="sm" /> : 'Search'}
          </Button>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            layer:
            {LAYERS.map((l) => (
              <label key={l} className="flex items-center gap-1">
                <input
                  type="radio"
                  name="search-layer"
                  checked={layer === l}
                  onChange={() => setLayer(l)}
                  className="accent-[hsl(var(--primary))]"
                />
                {l}
              </label>
            ))}
          </div>
          <label className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
            top_k
            <input
              type="range"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-20 accent-[hsl(var(--primary))]"
            />
            <span className="font-mono w-5 text-right">{topK}</span>
          </label>
        </div>
      </div>
      <ResultList results={results} loading={loading} error={error} searched={searched} />
    </div>
  );
}

// ============ Store Tab ============

function StoreTab() {
  const [content, setContent] = useState('');
  const [layer, setLayer] = useState<Layer>('working');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const submit = useCallback(async () => {
    const c = content.trim();
    if (!c) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await sdk.agentos.memStore({ content: c, layer });
      setSuccess(`已存储到 ${layer} 层`);
      setContent('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [content, layer]);

  return (
    <div className="flex h-full flex-col p-3 space-y-3">
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">内容</label>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="输入要存储的记忆内容..."
          className="min-h-[120px] w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        />
      </div>
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        layer:
        {LAYERS.map((l) => (
          <label key={l} className="flex items-center gap-1">
            <input
              type="radio"
              name="store-layer"
              checked={layer === l}
              onChange={() => setLayer(l)}
              className="accent-[hsl(var(--primary))]"
            />
            {l}
          </label>
        ))}
      </div>

      {error && <p className="text-xs text-destructive">⚠️ {error}</p>}
      {success && (
        <p className="inline-flex items-center gap-1 text-xs text-emerald-600">✓ {success}</p>
      )}

      <div className="mt-auto">
        <Button onClick={() => void submit()} disabled={busy || !content.trim()} className="w-full">
          {busy ? <Spinner size="sm" className="mr-2" /> : null}
          {busy ? '存储中...' : '存储记忆'}
        </Button>
      </div>
    </div>
  );
}

// ============ 结果列表(Recall/Search 共用) ============

function ResultList({
  results,
  loading,
  error,
  searched,
}: {
  results: MemoryItem[];
  loading: boolean;
  error: string | null;
  searched: boolean;
}) {
  return (
    <ScrollArea className="flex-1 min-h-0">
      <div className="p-2">
        {error && <p className="px-2 py-1 text-xs text-destructive">⚠️ {error}</p>}
        {loading ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <Spinner size="sm" className="mr-2" /> 检索中...
          </div>
        ) : results.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs text-muted-foreground">
            {searched ? '无匹配记忆' : '输入查询开始检索'}
          </div>
        ) : (
          <ul className="space-y-2">
            {results.map((m) => (
              <li
                key={m.memory_id || m.content.slice(0, 32)}
                className="rounded-md border border-border bg-background p-2.5 shadow-sm"
              >
                <p className="text-sm whitespace-pre-wrap break-words">{m.content}</p>
                <div className="mt-2 flex items-center gap-2 text-[10px] text-muted-foreground">
                  <Badge variant={layerBadgeVariant(m.layer)}>{m.layer}</Badge>
                  {m.score != null && (
                    <span className="font-mono">score {m.score.toFixed(3)}</span>
                  )}
                  {m.memory_id && (
                    <span className={cn('font-mono truncate ml-auto')}>id {m.memory_id}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </ScrollArea>
  );
}
