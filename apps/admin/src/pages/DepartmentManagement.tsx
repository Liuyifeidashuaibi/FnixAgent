/**
 * Phase 2.1: 部门管理页(组织架构树)
 *
 * 功能:
 *   1. 树形展示部门结构(支持展开/折叠)
 *   2. 新建部门(指定父部门)
 *   3. 编辑部门(名称/描述/负责人/状态)
 *   4. 删除部门(子部门级联删除)
 */
import { useEffect, useState } from 'react';
import { sdk, type RbacDepartment } from '@fnixagent/sdk';
import { HasPermission } from '../contexts/PermissionContext';

export function DepartmentManagement() {
  const [tree, setTree] = useState<RbacDepartment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<RbacDepartment | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createParent, setCreateParent] = useState<RbacDepartment | null>(null);

  async function loadTree() {
    try {
      setError(null);
      const resp = await sdk.rbac.getDepartmentTree();
      setTree(resp.data?.tree ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadTree();
  }, []);

  async function handleDelete(dept: RbacDepartment) {
    const childCount = dept.children?.length ?? 0;
    const msg = childCount > 0
      ? `确认删除部门「${dept.name}」?该部门下有 ${childCount} 个子部门将一并删除。`
      : `确认删除部门「${dept.name}」?`;
    if (!confirm(msg)) return;
    try {
      await sdk.rbac.deleteDepartment(dept.id);
      await loadTree();
    } catch (e) {
      alert(e instanceof Error ? e.message : '删除失败');
    }
  }

  if (loading) return <div className="p-4 text-muted-foreground">加载中...</div>;
  if (error) return <div className="p-4 text-red-500">错误:{error}</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">部门管理(组织架构)</h2>
        <HasPermission code="department:create">
          <button
            onClick={() => {
              setCreateParent(null);
              setShowCreate(true);
            }}
            className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90"
          >
            + 新建顶层部门
          </button>
        </HasPermission>
      </div>

      {tree.length === 0 ? (
        <div className="rounded border border-dashed border-border p-8 text-center text-muted-foreground">
          暂无部门,点击右上角创建
        </div>
      ) : (
        <div className="rounded border border-border p-4">
          {tree.map((dept) => (
            <DepartmentNode
              key={dept.id}
              dept={dept}
              level={0}
              onEdit={setEditing}
              onAddChild={(parent) => {
                setCreateParent(parent);
                setShowCreate(true);
              }}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateDepartmentModal
          parent={createParent}
          allDepts={tree}
          onClose={() => setShowCreate(false)}
          onCreated={async () => {
            setShowCreate(false);
            await loadTree();
          }}
        />
      )}

      {editing && (
        <EditDepartmentModal
          dept={editing}
          allDepts={tree}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await loadTree();
          }}
        />
      )}
    </div>
  );
}

function DepartmentNode({
  dept,
  level,
  onEdit,
  onAddChild,
  onDelete,
}: {
  dept: RbacDepartment;
  level: number;
  onEdit: (d: RbacDepartment) => void;
  onAddChild: (parent: RbacDepartment) => void;
  onDelete: (d: RbacDepartment) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = (dept.children?.length ?? 0) > 0;

  return (
    <div>
      <div
        className="flex items-center gap-2 py-1.5 hover:bg-secondary/30"
        style={{ paddingLeft: `${level * 24}px` }}
      >
        {hasChildren ? (
          <button
            onClick={() => setExpanded(!expanded)}
            className="w-4 text-xs text-muted-foreground"
          >
            {expanded ? '▼' : '▶'}
          </button>
        ) : (
          <span className="w-4" />
        )}
        <span className="text-sm font-medium">{dept.name}</span>
        <span className="font-mono text-xs text-muted-foreground">({dept.code})</span>
        {!dept.is_active && (
          <span className="rounded bg-red-100 px-1 text-xs text-red-700">禁用</span>
        )}
        <div className="ml-auto flex gap-2">
          <HasPermission code="department:create">
            <button
              onClick={() => onAddChild(dept)}
              className="text-xs text-primary hover:underline"
            >
              + 子部门
            </button>
          </HasPermission>
          <HasPermission code="department:update">
            <button
              onClick={() => onEdit(dept)}
              className="text-xs text-primary hover:underline"
            >
              编辑
            </button>
          </HasPermission>
          <HasPermission code="department:delete">
            <button
              onClick={() => onDelete(dept)}
              className="text-xs text-red-500 hover:underline"
            >
              删除
            </button>
          </HasPermission>
        </div>
      </div>
      {expanded && hasChildren && (
        <div>
          {dept.children.map((child) => (
            <DepartmentNode
              key={child.id}
              dept={child}
              level={level + 1}
              onEdit={onEdit}
              onAddChild={onAddChild}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function flattenDepts(tree: RbacDepartment[], level = 0): Array<RbacDepartment & { _level: number }> {
  const result: Array<RbacDepartment & { _level: number }> = [];
  for (const d of tree) {
    result.push({ ...d, _level: level });
    if (d.children?.length) {
      result.push(...flattenDepts(d.children, level + 1));
    }
  }
  return result;
}

function CreateDepartmentModal({
  parent,
  allDepts,
  onClose,
  onCreated,
}: {
  parent: RbacDepartment | null;
  allDepts: RbacDepartment[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [parentId, setParentId] = useState<string>(parent?.id?.toString() ?? '');
  const [submitting, setSubmitting] = useState(false);
  const flat = flattenDepts(allDepts);

  async function handleSubmit() {
    if (!code || !name) {
      alert('代码和名称必填');
      return;
    }
    setSubmitting(true);
    try {
      await sdk.rbac.createDepartment({
        code,
        name,
        description,
        parent_id: parentId ? Number(parentId) : null,
      });
      onCreated();
    } catch (e) {
      alert(e instanceof Error ? e.message : '创建失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title={parent ? `在「${parent.name}」下新建子部门` : '新建顶层部门'} onClose={onClose}>
      <div className="space-y-3">
        <Field label="代码" required>
          <input value={code} onChange={(e) => setCode(e.target.value)} className="input" placeholder="tech / sales / ..." />
        </Field>
        <Field label="名称" required>
          <input value={name} onChange={(e) => setName(e.target.value)} className="input" placeholder="技术部" />
        </Field>
        <Field label="父部门">
          <select value={parentId} onChange={(e) => setParentId(e.target.value)} className="input">
            <option value="">(顶层)</option>
            {flat.map((d) => (
              <option key={d.id} value={d.id}>
                {'　'.repeat(d._level)}{d.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="描述">
          <input value={description} onChange={(e) => setDescription(e.target.value)} className="input" />
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="btn-secondary">取消</button>
          <button onClick={handleSubmit} disabled={submitting} className="btn-primary">
            {submitting ? '提交中...' : '创建'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function EditDepartmentModal({
  dept,
  allDepts,
  onClose,
  onSaved,
}: {
  dept: RbacDepartment;
  allDepts: RbacDepartment[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(dept.name);
  const [description, setDescription] = useState(dept.description);
  const [parentId, setParentId] = useState<string>(dept.parent_id?.toString() ?? '');
  const [isActive, setIsActive] = useState(dept.is_active);
  const [submitting, setSubmitting] = useState(false);
  const flat = flattenDepts(allDepts).filter((d) => d.id !== dept.id);

  async function handleSave() {
    setSubmitting(true);
    try {
      await sdk.rbac.updateDepartment(dept.id, {
        name,
        description,
        parent_id: parentId ? Number(parentId) : null,
        is_active: isActive,
      });
      onSaved();
    } catch (e) {
      alert(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title={`编辑部门:${dept.code}`} onClose={onClose}>
      <div className="space-y-3">
        <Field label="名称">
          <input value={name} onChange={(e) => setName(e.target.value)} className="input" />
        </Field>
        <Field label="父部门">
          <select value={parentId} onChange={(e) => setParentId(e.target.value)} className="input">
            <option value="">(顶层)</option>
            {flat.map((d) => (
              <option key={d.id} value={d.id}>
                {'　'.repeat(d._level)}{d.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="描述">
          <input value={description} onChange={(e) => setDescription(e.target.value)} className="input" />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
          启用
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="btn-secondary">取消</button>
          <button onClick={handleSave} disabled={submitting} className="btn-primary">
            {submitting ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded bg-background p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-lg font-semibold">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
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
