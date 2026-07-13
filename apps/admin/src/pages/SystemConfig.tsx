import { useEffect, useState } from 'react';
import { sdk } from '@fnixagent/sdk';

/**
 * 系统配置页 — 查看 settings.yaml 可热更新项,支持编辑后写回(即时生效)
 */
export function SystemConfig() {
  const [keys, setKeys] = useState<string[]>([]);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function loadConfig() {
    setLoading(true);
    setError(null);
    try {
      const resp = await sdk.admin.getConfig();
      if (resp.success) {
        setKeys(resp.data.hot_reloadable_keys);
        setValues(resp.data.current_values);
        setEdits({});
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadConfig();
  }, []);

  async function handleSave() {
    const updates: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(edits)) {
      // 尝试解析为数字/布尔/字符串
      if (v === 'true') updates[k] = true;
      else if (v === 'false') updates[k] = false;
      else if (/^-?\d+$/.test(v)) updates[k] = Number(v);
      else if (/^-?\d+\.\d+$/.test(v)) updates[k] = Number(v);
      else updates[k] = v;
    }
    if (Object.keys(updates).length === 0) {
      setMsg('无修改');
      return;
    }
    setLoading(true);
    setMsg(null);
    try {
      const resp = await sdk.admin.updateConfig(updates);
      if (resp.success) {
        setMsg(`已更新 ${Object.keys(updates).length} 项配置,即时生效`);
        setEdits({});
        await loadConfig();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">系统配置(可热更新)</h2>
        <div className="flex gap-2">
          <button
            onClick={loadConfig}
            disabled={loading}
            className="rounded border border-border px-3 py-1.5 text-sm hover:bg-muted"
          >
            刷新
          </button>
          <button
            onClick={handleSave}
            disabled={loading || Object.keys(edits).length === 0}
            className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            保存修改 {Object.keys(edits).length > 0 && `(${Object.keys(edits).length})`}
          </button>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">
        仅以下白名单内的配置项可在运行时修改,写回 settings.yaml 后即时生效(无需重启服务)。
      </p>

      {error && <p className="text-sm text-red-500">⚠️ {error}</p>}
      {msg && <p className="text-sm text-green-600">✓ {msg}</p>}

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-3 py-2 text-left">配置键</th>
              <th className="px-3 py-2 text-left">当前值</th>
              <th className="px-3 py-2 text-left">修改为</th>
            </tr>
          </thead>
          <tbody>
            {loading && keys.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-3 py-8 text-center text-muted-foreground">
                  加载中...
                </td>
              </tr>
            ) : (
              keys.map((k) => {
                const current = values[k];
                const currentStr =
                  current === undefined || current === null
                    ? '(未设置)'
                    : typeof current === 'object'
                      ? JSON.stringify(current)
                      : String(current);
                return (
                  <tr key={k} className="border-t border-border">
                    <td className="px-3 py-2 font-mono text-xs">{k}</td>
                    <td className="px-3 py-2 text-muted-foreground">{currentStr}</td>
                    <td className="px-3 py-2">
                      <input
                        value={edits[k] ?? ''}
                        onChange={(e) => {
                          const next = { ...edits };
                          if (e.target.value === '') delete next[k];
                          else next[k] = e.target.value;
                          setEdits(next);
                        }}
                        placeholder="留空则不修改"
                        className="w-full rounded border border-border bg-background px-2 py-1 text-sm"
                      />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
