/**
 * Phase 2.1: 角色管理页
 *
 * 功能:
 *   1. 角色列表(含权限码、状态、是否内置)
 *   2. 新建角色(代码/名称/描述/初始权限)
 *   3. 编辑角色(名称/描述/状态/排序)
 *   4. 删除角色(内置不可删)
 *   5. 权限分配矩阵:按 resource 分组的复选框,全量替换角色权限
 */
import { useEffect, useState } from 'react';
import { sdk, type RbacPermission, type RbacRole } from '@officeagent/sdk';
import { HasPermission, usePermissions } from '../contexts/PermissionContext';

export function RoleManagement() {
  const { refresh } = usePermissions();
  const [roles, setRoles] = useState<RbacRole[]>([]);
  const [permissions, setPermissions] = useState<RbacPermission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingRole, setEditingRole] = useState<RbacRole | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  async function loadData() {
    try {
      setError(null);
      const [rolesResp, permsResp] = await Promise.all([
        sdk.rbac.listRoles(),
        sdk.rbac.listPermissions(),
      ]);
      setRoles(rolesResp.data?.items ?? []);
      setPermissions(permsResp.data?.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function handleDelete(role: RbacRole) {
    if (!confirm(`确认删除角色「${role.name}」?此操作不可恢复。`)) return;
    try {
      await sdk.rbac.deleteRole(role.id);
      await loadData();
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : '删除失败');
    }
  }

  if (loading) return <div className="p-4 text-muted-foreground">加载中...</div>;
  if (error) return <div className="p-4 text-red-500">错误:{error}</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">角色管理</h2>
        <HasPermission code="role:create">
          <button
            onClick={() => setShowCreate(true)}
            className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90"
          >
            + 新建角色
          </button>
        </HasPermission>
      </div>

      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-sm">
          <thead className="bg-secondary/50">
            <tr>
              <th className="px-3 py-2 text-left">代码</th>
              <th className="px-3 py-2 text-left">名称</th>
              <th className="px-3 py-2 text-left">描述</th>
              <th className="px-3 py-2 text-left">权限数</th>
              <th className="px-3 py-2 text-left">状态</th>
              <th className="px-3 py-2 text-left">类型</th>
              <th className="px-3 py-2 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {roles.map((r) => (
              <tr key={r.id} className="border-t border-border hover:bg-secondary/30">
                <td className="px-3 py-2 font-mono text-xs">{r.code}</td>
                <td className="px-3 py-2">{r.name}</td>
                <td className="px-3 py-2 text-muted-foreground">{r.description || '-'}</td>
                <td className="px-3 py-2">{r.permission_codes.length}</td>
                <td className="px-3 py-2">
                  {r.is_active ? (
                    <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">启用</span>
                  ) : (
                    <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700">禁用</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  {r.is_builtin ? (
                    <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700">内置</span>
                  ) : (
                    <span className="text-xs text-muted-foreground">自定义</span>
                  )}
                </td>
                <td className="px-3 py-2 text-right">
                  <HasPermission code="role:assign">
                    <button
                      onClick={() => setEditingRole(r)}
                      className="mr-2 text-xs text-primary hover:underline"
                    >
                      权限
                    </button>
                  </HasPermission>
                  <HasPermission code="role:update">
                    <button
                      onClick={() => setEditingRole(r)}
                      className="mr-2 text-xs text-primary hover:underline"
                    >
                      编辑
                    </button>
                  </HasPermission>
                  <HasPermission code="role:delete">
                    {!r.is_builtin && (
                      <button
                        onClick={() => handleDelete(r)}
                        className="text-xs text-red-500 hover:underline"
                      >
                        删除
                      </button>
                    )}
                  </HasPermission>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateRoleModal
          permissions={permissions}
          onClose={() => setShowCreate(false)}
          onCreated={async () => {
            setShowCreate(false);
            await loadData();
          }}
        />
      )}

      {editingRole && (
        <RolePermissionModal
          role={editingRole}
          permissions={permissions}
          onClose={() => setEditingRole(null)}
          onSaved={async () => {
            setEditingRole(null);
            await loadData();
            await refresh();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 新建角色弹窗
// ---------------------------------------------------------------------------

function CreateRoleModal({
  permissions,
  onClose,
  onCreated,
}: {
  permissions: RbacPermission[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  function togglePerm(code: string) {
    const next = new Set(selected);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setSelected(next);
  }

  async function handleSubmit() {
    if (!code || !name) {
      alert('代码和名称必填');
      return;
    }
    setSubmitting(true);
    try {
      await sdk.rbac.createRole({
        code,
        name,
        description,
        permission_codes: Array.from(selected),
      });
      onCreated();
    } catch (e) {
      alert(e instanceof Error ? e.message : '创建失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title="新建角色" onClose={onClose}>
      <div className="space-y-3">
        <Field label="代码" required>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="editor / manager / ..."
            className="input"
          />
        </Field>
        <Field label="名称" required>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="编辑者"
            className="input"
          />
        </Field>
        <Field label="描述">
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="input"
          />
        </Field>
        <PermissionMatrix
          permissions={permissions}
          selected={selected}
          onToggle={togglePerm}
        />
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="btn-secondary">
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="btn-primary"
          >
            {submitting ? '提交中...' : '创建'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// 角色权限编辑弹窗
// ---------------------------------------------------------------------------

function RolePermissionModal({
  role,
  permissions,
  onClose,
  onSaved,
}: {
  role: RbacRole;
  permissions: RbacPermission[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set(role.permission_codes));
  const [name, setName] = useState(role.name);
  const [description, setDescription] = useState(role.description);
  const [submitting, setSubmitting] = useState(false);

  function togglePerm(code: string) {
    const next = new Set(selected);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setSelected(next);
  }

  async function handleSave() {
    setSubmitting(true);
    try {
      // 1. 更新基本信息
      await sdk.rbac.updateRole(role.id, { name, description });
      // 2. 全量替换权限
      await sdk.rbac.setRolePermissions(role.id, Array.from(selected));
      onSaved();
    } catch (e) {
      alert(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title={`编辑角色:${role.code}`} onClose={onClose}>
      <div className="space-y-3">
        <Field label="名称">
          <input value={name} onChange={(e) => setName(e.target.value)} className="input" />
        </Field>
        <Field label="描述">
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="input"
          />
        </Field>
        <div>
          <div className="mb-2 text-sm font-medium">
            权限分配(已选 {selected.size} / {permissions.length})
          </div>
          <PermissionMatrix
            permissions={permissions}
            selected={selected}
            onToggle={togglePerm}
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="btn-secondary">
            取消
          </button>
          <button onClick={handleSave} disabled={submitting} className="btn-primary">
            {submitting ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// 权限矩阵(按 resource 分组)
// ---------------------------------------------------------------------------

function PermissionMatrix({
  permissions,
  selected,
  onToggle,
}: {
  permissions: RbacPermission[];
  selected: Set<string>;
  onToggle: (code: string) => void;
}) {
  // 按 resource 分组
  const grouped = permissions.reduce<Record<string, RbacPermission[]>>((acc, p) => {
    (acc[p.resource] ||= []).push(p);
    return acc;
  }, {});

  function toggleGroup(perms: RbacPermission[]) {
    const allSelected = perms.every((p) => selected.has(p.code));
    perms.forEach((p) => {
      if (allSelected && selected.has(p.code)) {
        onToggle(p.code);
      } else if (!allSelected && !selected.has(p.code)) {
        onToggle(p.code);
      }
    });
  }

  return (
    <div className="max-h-80 overflow-y-auto rounded border border-border p-3">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        {Object.entries(grouped).map(([resource, perms]) => {
          const allSel = perms.every((p) => selected.has(p.code));
          const someSel = perms.some((p) => selected.has(p.code));
          return (
            <div key={resource} className="space-y-1">
              <label className="flex items-center gap-2 border-b border-border pb-1 text-sm font-medium">
                <input
                  type="checkbox"
                  checked={allSel}
                  ref={(el) => {
                    if (el) el.indeterminate = !allSel && someSel;
                  }}
                  onChange={() => toggleGroup(perms)}
                />
                {resource}
              </label>
              {perms.map((p) => (
                <label
                  key={p.code}
                  className="flex items-center gap-2 text-xs text-muted-foreground"
                  title={p.description || p.code}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(p.code)}
                    onChange={() => onToggle(p.code)}
                  />
                  <span className="font-mono">{p.action}</span>
                  <span className="truncate">{p.name}</span>
                </label>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 通用 UI 组件
// ---------------------------------------------------------------------------

function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-4 text-lg font-semibold">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </label>
      {children}
    </div>
  );
}
