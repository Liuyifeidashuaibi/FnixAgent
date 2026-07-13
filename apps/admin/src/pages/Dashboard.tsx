import { useEffect, useState } from 'react';
import { sdk, type DashboardOverview, type DashboardTrendItem } from '@officeagent/sdk';

/**
 * 后台控制面板(Phase 4.4)
 *
 * 一屏总览:
 *   - 顶部 4 个核心指标卡片(用户/今日新增/审计/拦截)
 *   - 中部 系统信息 + 审核配置
 *   - 底部 7 天趋势图(纯 CSS 柱状图)
 */
export function Dashboard() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [trends, setTrends] = useState<DashboardTrendItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [ovResp, trendResp] = await Promise.all([
        sdk.dashboard.overview(),
        sdk.dashboard.trends(7),
      ]);
      if (ovResp.success && ovResp.data) setOverview(ovResp.data);
      else setError('加载失败');
      if (trendResp.success && trendResp.data) setTrends(trendResp.data.trends);
    } catch (e) {
      setError(e instanceof Error ? e.message : '网络错误');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        <span className="mr-2 h-2 w-2 animate-pulse rounded-full bg-primary" />
        加载中...
      </div>
    );
  }

  if (error) {
    return (
      <div className="card flex flex-col items-center gap-3 py-12">
        <span className="text-destructive">⚠</span>
        <p className="text-sm text-muted-foreground">{error}</p>
        <button onClick={load} className="btn-secondary">重试</button>
      </div>
    );
  }

  if (!overview) return null;

  return (
    <div className="space-y-6">
      {/* 顶部指标卡片 */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard
          label="用户总数"
          value={overview.users.total}
          hint={`活跃 ${overview.users.active} · 禁用 ${overview.users.disabled}`}
          tone="info"
        />
        <MetricCard
          label="今日新增"
          value={overview.users.today_new}
          hint={`待注销 ${overview.users.pending_deletion}`}
          tone="success"
        />
        <MetricCard
          label="近 24h 审计"
          value={overview.audit.last_24h_count}
          hint={overview.audit.top_action ? `Top: ${overview.audit.top_action}` : '无事件'}
          tone="info"
        />
        <MetricCard
          label="审核拦截"
          value={overview.moderation.blocked_input + overview.moderation.blocked_output}
          hint={`输入 ${overview.moderation.blocked_input} · 输出 ${overview.moderation.blocked_output}`}
          tone={overview.moderation.blocked_input + overview.moderation.blocked_output > 0 ? 'danger' : 'success'}
        />
      </div>

      {/* 中部:系统信息 + 审核统计 */}
      <div className="grid grid-cols-3 gap-4">
        {/* 系统信息 */}
        <div className="card">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-medium">系统信息</h3>
            <span className="badge-success">运行中</span>
          </div>
          <dl className="space-y-2 text-xs">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">版本</dt>
              <dd className="font-medium">v{overview.system.version}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">运行时长</dt>
              <dd className="font-medium">{formatUptime(overview.system.uptime_seconds)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">存储模式</dt>
              <dd className="font-medium">{overview.system.storage_mode}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Python</dt>
              <dd className="font-medium">{overview.system.python_version}</dd>
            </div>
          </dl>
        </div>

        {/* 审核统计 */}
        <div className="card col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-medium">内容审核</h3>
            <button onClick={load} className="btn-ghost h-7 px-2 text-xs">刷新</button>
          </div>
          <div className="grid grid-cols-4 gap-3 text-xs">
            <StatItem label="输入审核" value={overview.moderation.total_input} />
            <StatItem label="输出审核" value={overview.moderation.total_output} />
            <StatItem label="已脱敏" value={overview.moderation.sanitized} />
            <StatItem label="平均耗时" value={`${overview.moderation.avg_duration_ms}ms`} />
          </div>
          {Object.keys(overview.moderation.category_counts).length > 0 && (
            <div className="mt-4">
              <div className="mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
                违规类别分布
              </div>
              <div className="space-y-1.5">
                {Object.entries(overview.moderation.category_counts)
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 5)
                  .map(([cat, count]) => (
                    <div key={cat} className="flex items-center gap-2">
                      <span className="w-28 truncate text-xs">{cat}</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{
                            width: `${Math.min(100, (count / Math.max(1, overview.moderation.blocked_input + overview.moderation.blocked_output)) * 100)}%`,
                          }}
                        />
                      </div>
                      <span className="w-8 text-right text-xs font-medium">{count}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 7 天趋势 */}
      <div className="card">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-medium">近 7 天趋势</h3>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-primary" /> 新增用户
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm bg-success" /> 审计事件
            </span>
          </div>
        </div>
        {trends.length > 0 ? (
          <TrendChart trends={trends} />
        ) : (
          <div className="flex h-32 items-center justify-center text-xs text-muted-foreground">
            暂无数据
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function MetricCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: number;
  hint?: string;
  tone: 'info' | 'success' | 'warning' | 'danger';
}) {
  const toneClass = {
    info: 'text-primary',
    success: 'text-success',
    warning: 'text-warning',
    danger: 'text-destructive',
  }[tone];

  return (
    <div className="card-hover">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${toneClass}`}>{value.toLocaleString()}</div>
      {hint && <div className="mt-1 text-[10px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md bg-surface p-2.5">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className="mt-1 text-base font-semibold">{value}</div>
    </div>
  );
}

function TrendChart({ trends }: { trends: DashboardTrendItem[] }) {
  const maxValue = Math.max(
    ...trends.map((t) => Math.max(t.new_users, t.audit_events)),
    1,
  );

  return (
    <div className="flex h-40 items-end justify-between gap-2">
      {trends.map((t) => (
        <div key={t.date} className="flex flex-1 flex-col items-center gap-1.5">
          <div className="flex h-32 w-full items-end justify-center gap-1">
            <div
              className="w-3 rounded-t bg-primary transition-all hover:opacity-80"
              style={{ height: `${(t.new_users / maxValue) * 100}%`, minHeight: '2px' }}
              title={`新增用户: ${t.new_users}`}
            />
            <div
              className="w-3 rounded-t bg-success transition-all hover:opacity-80"
              style={{ height: `${(t.audit_events / maxValue) * 100}%`, minHeight: '2px' }}
              title={`审计事件: ${t.audit_events}`}
            />
          </div>
          <div className="text-[10px] text-muted-foreground">
            {t.date.slice(5)}
          </div>
        </div>
      ))}
    </div>
  );
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}
