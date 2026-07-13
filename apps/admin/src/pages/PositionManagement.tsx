/**
 * Phase 2.1: 职位管理页
 */
import { useEffect, useState } from 'react';
import { sdk, type RbacPosition } from '@officeagent/sdk';
import { HasPermission } from '../contexts/PermissionContext';

export function PositionManagement() {
  const [positions, setPositions] = useState<RbacPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<RbacPosition | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  async function load() {
    try {
      setError(null);
      const resp = await sdk.rbac.listPositions();
      setPositions(resp.data?.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleDelete(pos: RbacPosition) {
    if (!confirm(`确认删除职位「${pos.name}」?`)) return;
    try {
      await sdk.rbac.deletePosition(pos.id);
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : '删除失败');
    }
  }

  if (loading) return <div className="p-4 text-muted-foreground">加载中...</div>;
  if (error) return <div className="p-4 text-red-500">错误:{error}</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">职位管理</h2>
        <HasPermission code="position:create">
          <button
            onClick={() => setShowCreate(true)}
            className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90"
          >
            + 新建职位
          </button>
        </HasPermission>
      </div>

      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-sm">
          <thead className="bg-secondary/50">
            <tr>
              <th className="px-3 py-2 text-left">代码</th>
              <th className="px-3 py-2 text-left">名称</th>
              <th className="px-3 py-2 text-left">级别</th>
              <th className="px-3 py-2 text-left">描述</th>
              <th className="px-3 py-2 text-left">状态</th>
              <th className="px-3 py-2 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.id} className="border-t border-border hover:bg-secondary/30">
                <td className="px-3 py-2 font-mono text-xs">{p.code}</td>
                <td className="px-3 py-2">{p.name}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-1">
                    <span className="font-mono text-xs">{p.level}</span>
                    <div className="h-1.5 w-16 overflow-hidden rounded bg-secondary">
                      <div
                        className="h-full bg-primary"
                        style={{ width: `${p.level}%` }}
                      />
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2 text-muted-foreground">{p.description || '-'}</td>
                <td className="px-3 py-2">
                  {p.is_active ? (
                    <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">启用</span>
                  ) : (
                    <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700">禁用</span>
                  )}
                </td>
                <td className="px-3 py-2 text-right">
                  <HasPermission code="position:update">
                    <button
                      onClick={() => setEditing(p)}
                      className="mr-2 text-xs text-primary hover:underline"
                    >
                      编辑
                    </button>
                  </HasPermission>
                  <HasPermission code="position:delete">
                    <button
                      onClick={() => handleDelete(p)}
                      className="text-xs text-red-500 hover:underline"
                    >
                      删除
                    </button>
                  </HasPermission>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <PositionModal
          title="新建职位"
          onClose={() => setShowCreate(false)}
          onSubmit={async (body) => {
            await sdk.rbac.createPosition(body);
            setShowCreate(false);
            await load();
          }}
        />
      )}

      {editing && (
        <PositionModal
          title={`编辑职位:${editing.code}`}
          initial={editing}
          onClose={() => setEditing(null)}
          onSubmit={async (body) => {
            await sdk.rbac.updatePosition(editing.id, body);
            setEditing(null);
            await load();
          }}
        />
      )}
    </div>
  );
}

function PositionModal({
  title,
  initial,
  onClose,
  onSubmit,
}: {
  title: string;
  initial?: RbacPosition;
  onClose: () => void;
  onSubmit: (body: {
    code: string;
    name: string;
    level: number;
    description: string;
  }) => Promise<void>;
}) {
  const [code, setCode] = useState(initial?.code ?? '');
  const [name, setName] = useState(initial?.name ?? '');
  const [level, setLevel] = useState(initial?.level ?? 0);
  const [description, setDescription] = useState(initial?.description ?? '');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    if (!code || !name) {
      alert('代码和名称必填');
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit({ code, name, level, description });
    } catch (e) {
      alert(e instanceof Error ? e.message : '操作失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-md rounded bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-4 text-lg font-semibold">{title}</h3>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium">代码 *</label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              disabled={!!initial}
              className="input disabled:opacity-50"
              placeholder="senior_eng"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">名称 *</label>
            <input value={name} onChange={(e) => setName(e.target.value)} className="input" placeholder="高级工程师" />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">级别 (0-100)</label>
            <input
              type="number"
              min={0}
              max={100}
              value={level}
              onChange={(e) => setLevel(Number(e.target.value))}
              className="input"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">描述</label>
            <input value={description} onChange={(e) => setDescription(e.target.value)} className="input" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={onClose} className="btn-secondary">取消</button>
            <button onClick={handleSubmit} disabled={submitting} className="btn-primary">
              {submitting ? '提交中...' : '保存'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
