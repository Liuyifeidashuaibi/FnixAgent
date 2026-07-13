import { useCallback, useEffect, useState } from 'react';
import { sdk, type AuditLog, type AuditVerifyResult } from '@fnixagent/sdk';

/**
 * 审计日志页(Phase 2.5)— 查询 / 导出 / 哈希链校验
 *
 * 功能:
 *  1. 多维筛选(用户 ID / 操作类型 / 时间范围 / IP)
 *  2. 分页浏览
 *  3. 导出 JSON / CSV(导出操作本身会被记录到审计日志)
 *  4. 哈希链完整性校验(检测日志是否被篡改)
 *  5. 操作类型下拉框(从后端动态拉取 ALL_AUDIT_ACTIONS)
 */
export function AuditLogs() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actions, setActions] = useState<string[]>([]);
  const [filters, setFilters] = useState({
    user_id: '',
    action: '',
    start: '',
    end: '',
    ip_address: '',
  });
  const [page, setPage] = useState(0);
  const pageSize = 30;

  // 导出/校验状态
  const [exporting, setExporting] = useState(false);
  const [verifyResult, setVerifyResult] = useState<AuditVerifyResult | null>(null);
  const [verifying, setVerifying] = useState(false);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await sdk.audit.list({
        limit: pageSize,
        offset: page * pageSize,
        user_id: filters.user_id ? Number(filters.user_id) : undefined,
        action: filters.action || undefined,
        start: filters.start || undefined,
        end: filters.end || undefined,
        ip_address: filters.ip_address || undefined,
      });
      if (resp.success) {
        setLogs(resp.data.items);
        setTotal(resp.data.total);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [page, filters]);

  const fetchActions = useCallback(async () => {
    try {
      const resp = await sdk.audit.listActions();
      if (resp.success) {
        setActions(resp.data.items);
      }
    } catch {
      /* 拉取动作列表失败不阻塞主流程 */
    }
  }, []);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    fetchActions();
  }, [fetchActions]);

  const totalPages = Math.ceil(total / pageSize);
  /** 构造导出用的筛选参数(与查询一致) */
  function buildExportParams() {
    return {
      user_id: filters.user_id ? Number(filters.user_id) : undefined,
      action: filters.action || undefined,
      start: filters.start || undefined,
      end: filters.end || undefined,
    };
  }

  /** 导出为 JSON 文件(浏览器端触发下载) */
  async function handleExportJson() {
    setExporting(true);
    setError(null);
    try {
      const text = await sdk.audit.export({
        format: 'json',
        ...buildExportParams(),
        limit: 10000,
      });
      downloadTextFile(text, 'audit_logs.json', 'application/json');
    } catch (err) {
      setError(err instanceof Error ? err.message : '导出失败');
    } finally {
      setExporting(false);
    }
  }

  /** 导出为 CSV 文件 */
  async function handleExportCsv() {
    setExporting(true);
    setError(null);
    try {
      const text = await sdk.audit.export({
        format: 'csv',
        ...buildExportParams(),
        limit: 10000,
      });
      downloadTextFile(text, 'audit_logs.csv', 'text/csv');
    } catch (err) {
      setError(err instanceof Error ? err.message : '导出失败');
    } finally {
      setExporting(false);
    }
  }

  /** 校验哈希链完整性 */
  async function handleVerify() {
    setVerifying(true);
    setError(null);
    try {
      const resp = await sdk.audit.verify();
      if (resp.success) {
        setVerifyResult(resp.data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '校验失败');
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">审计日志 ({total})</h2>
        <div className="flex items-center gap-2">
          <button
            onClick={handleVerify}
            disabled={verifying}
            className="rounded border border-border px-3 py-1 text-sm hover:bg-muted disabled:opacity-50"
            title="校验审计日志哈希链是否被篡改"
          >
            {verifying ? '校验中...' : '🔗 校验哈希链'}
          </button>
          <button
            onClick={handleExportJson}
            disabled={exporting}
            className="rounded border border-border px-3 py-1 text-sm hover:bg-muted disabled:opacity-50"
          >
            {exporting ? '导出中...' : '⬇ 导出 JSON'}
          </button>
          <button
            onClick={handleExportCsv}
            disabled={exporting}
            className="rounded border border-border px-3 py-1 text-sm hover:bg-muted disabled:opacity-50"
          >
            {exporting ? '导出中...' : '⬇ 导出 CSV'}
          </button>
        </div>
      </div>

      {/* 哈希链校验结果 */}
      {verifyResult && (
        <div
          className={`rounded-md border p-3 text-sm ${
            verifyResult.is_valid
              ? 'border-green-500/50 bg-green-500/10 text-green-700'
              : 'border-red-500/50 bg-red-500/10 text-red-700'
          }`}
        >
          {verifyResult.is_valid ? '✅ ' : '⚠️ '}
          {verifyResult.message}
        </div>
      )}

      {/* 筛选条 */}
      <div className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-background p-3">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">用户 ID</label>
          <input
            value={filters.user_id}
            onChange={(e) => setFilters({ ...filters, user_id: e.target.value })}
            className="w-24 rounded border border-border px-2 py-1 text-sm"
            placeholder="可选"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">操作类型</label>
          <select
            value={filters.action}
            onChange={(e) => setFilters({ ...filters, action: e.target.value })}
            className="w-48 rounded border border-border px-2 py-1 text-sm"
          >
            <option value="">全部操作</option>
            {actions.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">IP 地址</label>
          <input
            value={filters.ip_address}
            onChange={(e) => setFilters({ ...filters, ip_address: e.target.value })}
            className="w-32 rounded border border-border px-2 py-1 text-sm"
            placeholder="可选"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">起始时间</label>
          <input
            type="datetime-local"
            value={filters.start}
            onChange={(e) => setFilters({ ...filters, start: e.target.value })}
            className="rounded border border-border px-2 py-1 text-sm"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">结束时间</label>
          <input
            type="datetime-local"
            value={filters.end}
            onChange={(e) => setFilters({ ...filters, end: e.target.value })}
            className="rounded border border-border px-2 py-1 text-sm"
          />
        </div>
        <button
          onClick={() => {
            setPage(0);
            fetchLogs();
          }}
          className="rounded border border-border px-3 py-1 text-sm hover:bg-muted"
        >
          查询
        </button>
      </div>

      {error && <p className="text-sm text-red-500">⚠️ {error}</p>}

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-3 py-2 text-left">ID</th>
              <th className="px-3 py-2 text-left">时间</th>
              <th className="px-3 py-2 text-left">用户 ID</th>
              <th className="px-3 py-2 text-left">操作</th>
              <th className="px-3 py-2 text-left">详情</th>
              <th className="px-3 py-2 text-left">IP</th>
              <th className="px-3 py-2 text-left">哈希</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">
                  加载中...
                </td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">
                  暂无日志
                </td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id} className="border-t border-border align-top">
                  <td className="px-3 py-2">{log.id}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {log.created_at ? new Date(log.created_at).toLocaleString() : '-'}
                  </td>
                  <td className="px-3 py-2">{log.user_id ?? '-'}</td>
                  <td className="px-3 py-2">
                    <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                      {log.action}
                    </code>
                  </td>
                  <td className="px-3 py-2 text-xs">
                    <pre className="max-w-md overflow-auto text-muted-foreground">
                      {JSON.stringify(log.detail, null, 2)}
                    </pre>
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {log.ip_address ?? '-'}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground" title={log.entry_hash ?? ''}>
                    {log.entry_hash ? `${log.entry_hash.slice(0, 8)}…` : '-'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            第 {page + 1} / {totalPages} 页
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="rounded border border-border px-3 py-1 disabled:opacity-50"
            >
              上一页
            </button>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="rounded border border-border px-3 py-1 disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** 浏览器端触发文本文件下载 */
function downloadTextFile(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
