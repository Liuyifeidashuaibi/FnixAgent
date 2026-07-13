import { useCallback, useEffect, useMemo, useState } from 'react';
import { sdk } from '@officeagent/sdk';
import type { AgentOSResponse } from '@officeagent/sdk';
import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  ScrollArea,
  Spinner,
  cn,
} from '@officeagent/ui';

/**
 * ProcessesPanel — Agent 进程监视器
 *
 * 对接 sdk.agentos.ps / info / kill / spawn
 * 功能:
 *   - 顶部统计: 总进程数 / 运行中 / 阻塞
 *   - 列表: 进程名 + PID(mono) + 状态徽标 + token 用量 + Kill 按钮
 *   - 点击展开: 详情(priority/capabilities/created_at/cpu_time)
 *   - Spawn: 弹 Dialog 输入 进程名 + 优先级 + 能力
 */

type ProcessStatus = 'READY' | 'RUNNING' | 'BLOCKED' | 'TERMINATED' | 'SUSPENDED';

interface AgentProcessInfo {
  pid: string;
  name: string;
  status: ProcessStatus;
  priority?: number;
  capabilities?: string[];
  created_at?: string;
  cpu_time?: number;
  token_usage?: number;
}

// 从响应中提取进程列表
function extractProcesses(resp: AgentOSResponse): AgentProcessInfo[] {
  const data = resp.data;
  const arr: unknown[] = Array.isArray(data)
    ? data
    : data && typeof data === 'object'
      ? (() => {
          const o = data as Record<string, unknown>;
          return (
            (Array.isArray(o.processes) ? o.processes : null) ??
            (Array.isArray(o.items) ? o.items : null) ??
            (Array.isArray(o.list) ? o.list : null) ??
            []
          );
        })()
      : [];
  return arr.map((raw) => {
    const o = (raw ?? {}) as Record<string, unknown>;
    return {
      pid: String(o.pid ?? o.id ?? ''),
      name: String(o.name ?? 'unnamed'),
      status: (typeof o.status === 'string' ? o.status : 'READY') as ProcessStatus,
      priority: typeof o.priority === 'number' ? o.priority : undefined,
      capabilities: Array.isArray(o.capabilities) ? (o.capabilities as string[]) : undefined,
      created_at: typeof o.created_at === 'string' ? o.created_at : undefined,
      cpu_time: typeof o.cpu_time === 'number' ? o.cpu_time : undefined,
      token_usage: typeof o.token_usage === 'number' ? o.token_usage : undefined,
    } satisfies AgentProcessInfo;
  });
}

// 状态 → Badge variant
function statusVariant(status: ProcessStatus) {
  switch (status) {
    case 'READY':
      return 'secondary' as const;
    case 'RUNNING':
      return 'success' as const;
    case 'BLOCKED':
      return 'warning' as const;
    case 'TERMINATED':
      return 'destructive' as const;
    case 'SUSPENDED':
      return 'outline' as const;
    default:
      return 'secondary' as const;
  }
}

export function ProcessesPanel() {
  const [processes, setProcesses] = useState<AgentProcessInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedPid, setExpandedPid] = useState<string | null>(null);
  const [killing, setKilling] = useState<string | null>(null);
  const [spawnOpen, setSpawnOpen] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await sdk.agentos.ps();
      setProcesses(extractProcesses(resp));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleKill = useCallback(
    async (pid: string) => {
      setKilling(pid);
      try {
        await sdk.agentos.kill({ pid });
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setKilling(null);
      }
    },
    [refresh],
  );

  const stats = useMemo(() => {
    const total = processes.length;
    const running = processes.filter((p) => p.status === 'RUNNING').length;
    const blocked = processes.filter((p) => p.status === 'BLOCKED').length;
    return { total, running, blocked };
  }, [processes]);

  return (
    <div className="flex h-full flex-col bg-background">
      {/* 顶部:标题 + 刷新 + Spawn */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2 shrink-0">
        <h2 className="text-sm font-semibold">Agent 进程</h2>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => void refresh()} disabled={loading}>
            {loading ? <Spinner size="sm" /> : <RefreshIcon />}
          </Button>
          <Button size="sm" onClick={() => setSpawnOpen(true)}>
            <PlusIcon /> Spawn
          </Button>
        </div>
      </div>

      {/* 统计条 */}
      <div className="grid grid-cols-3 gap-2 border-b border-border bg-secondary/40 px-3 py-2 shrink-0 text-xs">
        <Stat label="总进程" value={stats.total} />
        <Stat label="运行中" value={stats.running} tone="success" />
        <Stat label="阻塞" value={stats.blocked} tone="warning" />
      </div>

      {/* 错误 */}
      {error && (
        <div className="shrink-0 px-3 py-1.5 text-xs text-destructive">⚠️ {error}</div>
      )}

      {/* 进程列表 */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-2">
          {loading && processes.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Spinner size="sm" className="mr-2" /> 加载中...
            </div>
          ) : processes.length === 0 ? (
            <div className="px-3 py-8 text-center text-xs text-muted-foreground">
              暂无进程,点击 Spawn 启动
            </div>
          ) : (
            <ul className="space-y-1">
              {processes.map((p) => (
                <ProcessRow
                  key={p.pid}
                  proc={p}
                  expanded={expandedPid === p.pid}
                  killing={killing === p.pid}
                  onToggle={() => setExpandedPid(expandedPid === p.pid ? null : p.pid)}
                  onKill={() => void handleKill(p.pid)}
                />
              ))}
            </ul>
          )}
        </div>
      </ScrollArea>

      {/* Spawn 弹窗 */}
      {spawnOpen && (
        <SpawnDialog
          onClose={() => setSpawnOpen(false)}
          onSpawned={() => {
            setSpawnOpen(false);
            void refresh();
          }}
        />
      )}
    </div>
  );
}

// ============ 统计单元 ============

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: 'success' | 'warning';
}) {
  return (
    <div className="flex items-center justify-between rounded bg-background/60 px-2 py-1">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={cn(
          'font-mono font-semibold',
          tone === 'success' && 'text-emerald-600',
          tone === 'warning' && 'text-amber-600',
        )}
      >
        {value}
      </span>
    </div>
  );
}

// ============ 进程行 ============

function ProcessRow({
  proc,
  expanded,
  killing,
  onToggle,
  onKill,
}: {
  proc: AgentProcessInfo;
  expanded: boolean;
  killing: boolean;
  onToggle: () => void;
  onKill: () => void;
}) {
  return (
    <li className="rounded-md border border-border bg-background shadow-sm">
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle();
          }
        }}
        className="flex items-center gap-2 px-2.5 py-2 cursor-pointer hover:bg-accent"
      >
        {/* 左:名称 + PID */}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{proc.name}</div>
          <div className="font-mono text-[10px] text-muted-foreground">PID {proc.pid}</div>
        </div>
        {/* 中:状态徽标 */}
        <Badge variant={statusVariant(proc.status)}>{proc.status}</Badge>
        {/* 右:token + Kill */}
        {proc.token_usage != null && (
          <span className="text-[10px] text-muted-foreground">
            {proc.token_usage.toLocaleString()} tok
          </span>
        )}
        <button
          type="button"
          title="Kill"
          disabled={killing}
          onClick={(e) => {
            e.stopPropagation();
            onKill();
          }}
          className="rounded p-1 text-destructive hover:bg-destructive/10 disabled:opacity-50"
        >
          {killing ? <Spinner size="sm" /> : <CloseIcon />}
        </button>
      </div>

      {/* 展开详情 */}
      {expanded && (
        <div className="border-t border-border bg-muted/30 px-3 py-2 text-xs space-y-1 animate-fade-in">
          <DetailRow label="优先级" value={proc.priority != null ? String(proc.priority) : '-'} />
          <DetailRow
            label="能力"
            value={proc.capabilities && proc.capabilities.length > 0 ? proc.capabilities.join(', ') : '-'}
          />
          <DetailRow
            label="创建时间"
            value={proc.created_at ? new Date(proc.created_at).toLocaleString() : '-'}
          />
          <DetailRow
            label="CPU 时间"
            value={proc.cpu_time != null ? `${proc.cpu_time} ms` : '-'}
          />
        </div>
      )}
    </li>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono truncate text-right">{value}</span>
    </div>
  );
}

// ============ Spawn 弹窗 ============

function SpawnDialog({
  onClose,
  onSpawned,
}: {
  onClose: () => void;
  onSpawned: () => void;
}) {
  const [name, setName] = useState('');
  const [priority, setPriority] = useState('5');
  const [capabilities, setCapabilities] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      const caps = capabilities
        .split(',')
        .map((c) => c.trim())
        .filter(Boolean);
      await sdk.agentos.spawn({
        name: name.trim(),
        priority: Number(priority) || undefined,
        capabilities: caps.length > 0 ? caps : undefined,
      });
      onSpawned();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Spawn Agent 进程</DialogTitle>
          <DialogDescription>启动一个新的 AgentOS 进程</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">进程名</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              placeholder="agent-worker"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">优先级 (0-10)</label>
            <Input
              type="number"
              min={0}
              max={10}
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">能力 (逗号分隔)</label>
            <Input
              value={capabilities}
              onChange={(e) => setCapabilities(e.target.value)}
              placeholder="code,search,fs"
            />
          </div>
        </div>

        {err && <p className="text-xs text-destructive">⚠️ {err}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            取消
          </Button>
          <Button onClick={() => void submit()} disabled={busy || !name.trim()}>
            {busy ? '启动中...' : 'Spawn'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============ 小图标 ============

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true" className="mr-1">
      <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M13 8a5 5 0 1 1-1.46-3.54M13 3v3h-3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
