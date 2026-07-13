import { useCallback, useEffect, useState } from 'react';
import { sdk, type AdminUser } from '@officeagent/sdk';

/**
 * 用户管理页 — 列表 / 搜索 / 禁用 / 启用 / 重置密码 / 改角色
 */
export function UserManagement() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tempPassword, setTempPassword] = useState<{ user: string; pwd: string } | null>(null);
  const pageSize = 20;

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await sdk.admin.listUsers({
        limit: pageSize,
        offset: page * pageSize,
        search: search || undefined,
      });
      if (resp.success) {
        setUsers(resp.data.items);
        setTotal(resp.data.total);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  async function handleToggleDisabled(user: AdminUser) {
    const disabled = Boolean(user.profile?.disabled);
    if (disabled) {
      await sdk.admin.enableUser(user.id);
    } else {
      await sdk.admin.disableUser(user.id);
    }
    fetchUsers();
  }

  async function handleResetPassword(user: AdminUser) {
    if (!confirm(`确认重置用户 ${user.username} 的密码?`)) return;
    try {
      const resp = await sdk.admin.resetPassword(user.id);
      if (resp.success && resp.data?.temp_password) {
        setTempPassword({ user: user.username, pwd: resp.data.temp_password });
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '重置失败');
    }
  }

  async function handleRoleChange(user: AdminUser, role: 'user' | 'admin') {
    if (user.role === role) return;
    if (!confirm(`确认将 ${user.username} 的角色改为 ${role}?`)) return;
    await sdk.admin.updateRole(user.id, role);
    fetchUsers();
  }

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">用户管理 ({total})</h2>
        <div className="flex gap-2">
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            placeholder="搜索用户名/邮箱..."
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm w-64"
          />
          <button
            onClick={fetchUsers}
            className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
          >
            刷新
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-red-500">⚠️ {error}</p>}

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-3 py-2 text-left">ID</th>
              <th className="px-3 py-2 text-left">用户名</th>
              <th className="px-3 py-2 text-left">邮箱</th>
              <th className="px-3 py-2 text-left">角色</th>
              <th className="px-3 py-2 text-left">状态</th>
              <th className="px-3 py-2 text-left">配额</th>
              <th className="px-3 py-2 text-left">注册时间</th>
              <th className="px-3 py-2 text-left">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-muted-foreground">
                  加载中...
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-muted-foreground">
                  暂无用户
                </td>
              </tr>
            ) : (
              users.map((u) => {
                const disabled = Boolean(u.profile?.disabled);
                return (
                  <tr key={u.id} className="border-t border-border">
                    <td className="px-3 py-2">{u.id}</td>
                    <td className="px-3 py-2 font-medium">{u.username}</td>
                    <td className="px-3 py-2 text-muted-foreground">{u.email || '-'}</td>
                    <td className="px-3 py-2">
                      <select
                        value={u.role}
                        onChange={(e) =>
                          handleRoleChange(u, e.target.value as 'user' | 'admin')
                        }
                        className="rounded border border-border bg-background px-2 py-0.5 text-xs"
                      >
                        <option value="user">user</option>
                        <option value="admin">admin</option>
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      {disabled ? (
                        <span className="text-red-500">已禁用</span>
                      ) : (
                        <span className="text-green-600">正常</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {u.quota_used}/{u.quota_total}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {new Date(u.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleToggleDisabled(u)}
                          className="rounded border border-border px-2 py-0.5 text-xs hover:bg-muted"
                        >
                          {disabled ? '启用' : '禁用'}
                        </button>
                        <button
                          onClick={() => handleResetPassword(u)}
                          className="rounded border border-border px-2 py-0.5 text-xs hover:bg-muted"
                        >
                          重置密码
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* 分页 */}
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

      {/* 临时密码弹窗 */}
      {tempPassword && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-lg bg-background p-6 shadow-lg">
            <h3 className="mb-2 text-lg font-semibold">临时密码</h3>
            <p className="mb-3 text-sm text-muted-foreground">
              用户 <strong>{tempPassword.user}</strong> 的临时密码(仅显示一次):
            </p>
            <code className="block rounded bg-muted px-3 py-2 font-mono text-lg">
              {tempPassword.pwd}
            </code>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(tempPassword.pwd);
                }}
                className="rounded border border-border px-3 py-1.5 text-sm hover:bg-muted"
              >
                复制
              </button>
              <button
                onClick={() => setTempPassword(null)}
                className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
