import { useEffect, useState } from 'react';
import { sdk, type ModerationConfig, type DashboardModerationStats } from '@fnixagent/sdk';

/**
 * 内容审核配置页面(Phase 4.5)
 *
 * 功能:
 *   - 查看审核服务统计
 *   - 热更新审核配置(总开关/输入/输出/脱敏/仅高风险)
 */
export function ModerationConfigPage() {
  const [config, setConfig] = useState<ModerationConfig | null>(null);
  const [stats, setStats] = useState<DashboardModerationStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await sdk.dashboard.moderation();
      if (resp.success && resp.data) {
        setConfig({
          enabled: resp.data.enabled,
          input_enabled: resp.data.input_enabled,
          output_enabled: resp.data.output_enabled,
          auto_sanitize: resp.data.auto_sanitize,
          block_high_risk_only: resp.data.block_high_risk_only,
          high_risk_threshold: resp.data.high_risk_threshold,
        });
        setStats({
          total_input: resp.data.total_input,
          total_output: resp.data.total_output,
          blocked_input: resp.data.blocked_input,
          blocked_output: resp.data.blocked_output,
          sanitized: resp.data.sanitized,
          avg_duration_ms: resp.data.avg_duration_ms,
          category_counts: resp.data.category_counts,
        });
      } else {
        setError('加载失败');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '网络错误');
    } finally {
      setLoading(false);
    }
  }

  async function updateConfig(patch: Partial<ModerationConfig>) {
    if (!config) return;
    setSaving(true);
    try {
      const resp = await sdk.dashboard.updateModerationConfig(patch);
      if (resp.success && resp.data) {
        setConfig(resp.data.current_config);
      }
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
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

  if (!config) return null;

  return (
    <div className="space-y-6">
      {/* 统计概览 */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <StatCard label="输入审核次数" value={stats.total_input} />
          <StatCard label="输出审核次数" value={stats.total_output} />
          <StatCard label="拦截输入" value={stats.blocked_input} tone="danger" />
          <StatCard label="拦截输出" value={stats.blocked_output} tone="danger" />
        </div>
      )}

      {/* 配置开关 */}
      <div className="card">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-medium">审核配置</h3>
          {saving && <span className="text-xs text-muted-foreground">保存中...</span>}
        </div>

        <div className="space-y-1">
          <ToggleRow
            label="启用内容审核"
            description="总开关,关闭后所有审核逻辑跳过"
            checked={config.enabled}
            onChange={(v) => updateConfig({ enabled: v })}
          />
          <ToggleRow
            label="输入审核"
            description="对用户输入做违规检测(敏感词/有害内容/PII)"
            checked={config.input_enabled}
            disabled={!config.enabled}
            onChange={(v) => updateConfig({ input_enabled: v })}
          />
          <ToggleRow
            label="输出审核"
            description="对 LLM 输出做违规检测 + PII 脱敏"
            checked={config.output_enabled}
            disabled={!config.enabled}
            onChange={(v) => updateConfig({ output_enabled: v })}
          />
          <ToggleRow
            label="自动脱敏"
            description="检测到 PII 时自动脱敏(手机号/邮箱/身份证/银行卡)"
            checked={config.auto_sanitize}
            disabled={!config.enabled}
            onChange={(v) => updateConfig({ auto_sanitize: v })}
          />
          <ToggleRow
            label="仅拦截高风险"
            description="仅 risk_score >= 阈值 时拦截,低风险放行"
            checked={config.block_high_risk_only}
            disabled={!config.enabled}
            onChange={(v) => updateConfig({ block_high_risk_only: v })}
          />
        </div>

        {config.block_high_risk_only && (
          <div className="mt-4 flex items-center gap-3 border-t border-border pt-4">
            <label className="text-xs text-muted-foreground">高风险阈值</label>
            <input
              type="range"
              min="10"
              max="100"
              step="10"
              value={config.high_risk_threshold}
              onChange={(e) => updateConfig({ high_risk_threshold: Number(e.target.value) })}
              className="flex-1"
            />
            <span className="w-10 text-right text-xs font-medium">
              {config.high_risk_threshold}
            </span>
          </div>
        )}
      </div>

      {/* 类别分布 */}
      {stats && Object.keys(stats.category_counts).length > 0 && (
        <div className="card">
          <h3 className="mb-3 text-sm font-medium">违规类别分布</h3>
          <div className="space-y-2">
            {Object.entries(stats.category_counts)
              .sort(([, a], [, b]) => b - a)
              .map(([cat, count]) => {
                const total = Math.max(1, stats.blocked_input + stats.blocked_output);
                const pct = (count / total) * 100;
                return (
                  <div key={cat} className="flex items-center gap-3">
                    <span className="w-32 text-xs">{CATEGORY_LABELS[cat] || cat}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
                      <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="w-10 text-right text-xs font-medium">{count}</span>
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}

const CATEGORY_LABELS: Record<string, string> = {
  self_harm: '自伤/自杀',
  violence: '暴力/武器',
  pornography: '色情/低俗',
  political: '政治/极端',
  fraud: '诈骗/违法',
  pii: 'PII 泄露',
  sensitive_word: '敏感词',
};

function StatCard({
  label,
  value,
  tone = 'info',
}: {
  label: string;
  value: number;
  tone?: 'info' | 'danger' | 'success';
}) {
  const toneClass = {
    info: 'text-primary',
    danger: 'text-destructive',
    success: 'text-success',
  }[tone];
  return (
    <div className="card">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-1 text-xl font-bold ${toneClass}`}>{value.toLocaleString()}</div>
    </div>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between py-2.5">
      <div className="flex-1 pr-4">
        <div className="text-sm font-medium">{label}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">{description}</div>
      </div>
      <button
        onClick={() => onChange(!checked)}
        disabled={disabled}
        className={`relative h-5 w-9 rounded-full transition-colors disabled:opacity-50 ${
          checked ? 'bg-primary' : 'bg-surface-2'
        }`}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
            checked ? 'translate-x-4' : 'translate-x-0.5'
          }`}
        />
      </button>
    </div>
  );
}
