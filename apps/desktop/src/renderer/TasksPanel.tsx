/**
 * TasksPanel — 本地任务管理面板
 *
 * 纯前端实现,任务状态保存在 localStorage,不依赖后端。
 *
 * 功能:
 *   1. 新增任务(标题 + 优先级)
 *   2. 任务列表:按状态分组(todo / doing / done)
 *   3. 切换状态(点击 checkbox 循环 todo → doing → done → todo)
 *   4. 编辑标题(双击或点编辑按钮)
 *   5. 删除任务
 *   6. 过滤(全部 / 待办 / 进行中 / 已完成)
 *   7. localStorage 持久化(key: fnixagent.tasks.v1)
 *
 * 浅色主题,样式与 index.css 的 CSS 变量对齐。
 */
import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react';

/* ================================================================
   类型
   ================================================================ */

type TaskStatus = 'todo' | 'doing' | 'done';
type TaskPriority = 'low' | 'medium' | 'high';
type Filter = 'all' | TaskStatus;

interface Task {
  id: string;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  createdAt: number;
  updatedAt: number;
}

/* ================================================================
   常量
   ================================================================ */

const STORAGE_KEY = 'fnixagent.tasks.v1';

const STATUS_LABEL: Record<TaskStatus, string> = {
  todo: '待办',
  doing: '进行中',
  done: '已完成',
};

const PRIORITY_LABEL: Record<TaskPriority, string> = {
  low: '低',
  medium: '中',
  high: '高',
};

/* ================================================================
   主组件
   ================================================================ */

export function TasksPanel() {
  const [tasks, setTasks] = useState<Task[]>(() => loadTasks());
  const [title, setTitle] = useState('');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [filter, setFilter] = useState<Filter>('all');
  const [editingId, setEditingId] = useState<string | null>(null);

  // 持久化
  useEffect(() => {
    saveTasks(tasks);
  }, [tasks]);

  const visible = useMemo(() => {
    if (filter === 'all') return tasks;
    return tasks.filter((t) => t.status === filter);
  }, [tasks, filter]);

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: tasks.length, todo: 0, doing: 0, done: 0 };
    for (const t of tasks) c[t.status]++;
    return c;
  }, [tasks]);

  function addTask() {
    const t = title.trim();
    if (!t) return;
    const now = Date.now();
    const task: Task = {
      id: genId(),
      title: t,
      status: 'todo',
      priority,
      createdAt: now,
      updatedAt: now,
    };
    setTasks((prev) => [task, ...prev]);
    setTitle('');
  }

  function cycleStatus(id: string) {
    setTasks((prev) =>
      prev.map((t) =>
        t.id === id
          ? {
              ...t,
              status: nextStatus(t.status),
              updatedAt: Date.now(),
            }
          : t,
      ),
    );
  }

  function deleteTask(id: string) {
    setTasks((prev) => prev.filter((t) => t.id !== id));
    if (editingId === id) setEditingId(null);
  }

  function renameTask(id: string, newTitle: string) {
    const nt = newTitle.trim();
    if (!nt) {
      setEditingId(null);
      return;
    }
    setTasks((prev) =>
      prev.map((t) => (t.id === id ? { ...t, title: nt, updatedAt: Date.now() } : t)),
    );
    setEditingId(null);
  }

  function clearDone() {
    setTasks((prev) => prev.filter((t) => t.status !== 'done'));
  }

  return (
    <div style={s.container}>
      {/* 标题栏 */}
      <div style={s.header}>
        <span style={s.title}>任务</span>
        {counts.done > 0 && (
          <button style={s.linkBtn} onClick={clearDone} title="清除已完成任务">
            清除已完成
          </button>
        )}
      </div>

      {/* 新增表单 */}
      <div style={s.form}>
        <input
          style={s.input}
          type="text"
          placeholder="新增任务…"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addTask();
            }
          }}
        />
        <select
          style={s.prioritySelect}
          value={priority}
          onChange={(e) => setPriority(e.target.value as TaskPriority)}
          title="优先级"
        >
          <option value="low">低</option>
          <option value="medium">中</option>
          <option value="high">高</option>
        </select>
        <button style={title.trim() ? s.addBtn : s.addBtnDisabled} onClick={addTask} disabled={!title.trim()}>
          +
        </button>
      </div>

      {/* 过滤标签 */}
      <div style={s.tabs}>
        {(['all', 'todo', 'doing', 'done'] as Filter[]).map((f) => (
          <button
            key={f}
            style={filter === f ? s.tabActive : s.tab}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? '全部' : STATUS_LABEL[f]}
            <span style={s.tabCount}>{counts[f]}</span>
          </button>
        ))}
      </div>

      {/* 任务列表 */}
      <div style={s.listArea}>
        {visible.length === 0 ? (
          <div style={s.empty}>
            <span style={s.emptyIcon} aria-hidden="true">✓</span>
            <span style={s.emptyText}>
              {tasks.length === 0 ? '暂无任务,添加一个开始吧' : '该筛选下无任务'}
            </span>
          </div>
        ) : (
          visible.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              isEditing={editingId === task.id}
              onCycle={() => cycleStatus(task.id)}
              onDelete={() => deleteTask(task.id)}
              onEdit={() => setEditingId(task.id)}
              onRename={(nt) => renameTask(task.id, nt)}
            />
          ))
        )}
      </div>

      {/* 底部统计 */}
      <div style={s.footer}>
        <span>共 {tasks.length} 项</span>
        <span style={s.footerDot}>·</span>
        <span style={s.footerDone}>{counts.done} 已完成</span>
      </div>
    </div>
  );
}

/* ================================================================
   任务行
   ================================================================ */

interface TaskRowProps {
  task: Task;
  isEditing: boolean;
  onCycle: () => void;
  onDelete: () => void;
  onEdit: () => void;
  onRename: (newTitle: string) => void;
}

function TaskRow({ task, isEditing, onCycle, onDelete, onEdit, onRename }: TaskRowProps) {
  const [draft, setDraft] = useState(task.title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing) {
      setDraft(task.title);
      // 聚焦并在末尾
      requestAnimationFrame(() => {
        const el = inputRef.current;
        if (el) {
          el.focus();
          el.setSelectionRange(el.value.length, el.value.length);
        }
      });
    }
  }, [isEditing, task.title]);

  function commit() {
    onRename(draft);
  }

  function handleKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault();
      commit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onRename(task.title); // 取消,保留原标题
    }
  }

  const isDone = task.status === 'done';

  return (
    <div style={s.row}>
      {/* 状态切换 checkbox */}
      <button
        style={{
          ...s.checkbox,
          background:
            task.status === 'done'
              ? 'var(--success)'
              : task.status === 'doing'
                ? 'var(--accent)'
                : 'transparent',
          borderColor:
            task.status === 'todo' ? 'var(--border-color)' : 'transparent',
        }}
        onClick={onCycle}
        title={`状态:${STATUS_LABEL[task.status]}(点击切换)`}
        aria-label="切换任务状态"
      >
        {task.status === 'done' && <span style={s.checkmark}>✓</span>}
        {task.status === 'doing' && <span style={s.doingDot} />}
      </button>

      {/* 标题 / 编辑框 */}
      {isEditing ? (
        <input
          ref={inputRef}
          style={s.editInput}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={handleKey}
        />
      ) : (
        <span
          style={{
            ...s.taskTitle,
            textDecoration: isDone ? 'line-through' : 'none',
            color: isDone ? 'var(--text-tertiary)' : 'var(--text-primary)',
          }}
          onDoubleClick={onEdit}
          title="双击编辑"
        >
          {task.title}
        </span>
      )}

      {/* 优先级徽标 */}
      {!isEditing && (
        <span style={{ ...s.priorityBadge, ...priorityStyle(task.priority) }}>
          {PRIORITY_LABEL[task.priority]}
        </span>
      )}

      {/* 操作按钮 */}
      {!isEditing && (
        <div style={s.rowActions}>
          <button style={s.iconBtn} onClick={onEdit} title="编辑">
            ✎
          </button>
          <button
            style={{ ...s.iconBtn, color: 'var(--error)' }}
            onClick={onDelete}
            title="删除"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}

/* ================================================================
   工具函数
   ================================================================ */

function nextStatus(s: TaskStatus): TaskStatus {
  if (s === 'todo') return 'doing';
  if (s === 'doing') return 'done';
  return 'todo';
}

function genId(): string {
  return `t_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function loadTasks(): Task[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((t): t is Task => t && typeof t.id === 'string' && typeof t.title === 'string')
      .map((t) => ({
        id: t.id,
        title: t.title,
        status: (['todo', 'doing', 'done'].includes(t.status) ? t.status : 'todo') as TaskStatus,
        priority: (['low', 'medium', 'high'].includes(t.priority) ? t.priority : 'medium') as TaskPriority,
        createdAt: typeof t.createdAt === 'number' ? t.createdAt : Date.now(),
        updatedAt: typeof t.updatedAt === 'number' ? t.updatedAt : Date.now(),
      }));
  } catch {
    return [];
  }
}

function saveTasks(tasks: Task[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
  } catch {
    // 配额超限或隐私模式,静默忽略
  }
}

function priorityStyle(p: TaskPriority): CSSProperties {
  if (p === 'high') return { background: 'rgba(220, 38, 38, 0.1)', color: 'var(--error)' };
  if (p === 'medium') return { background: 'rgba(245, 158, 11, 0.12)', color: 'var(--warning)' };
  return { background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' };
}

/* ================================================================
   样式
   ================================================================ */

const s: Record<string, CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: 'var(--bg-secondary)',
    userSelect: 'none',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 12px',
    flexShrink: 0,
  },
  title: {
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  linkBtn: {
    background: 'transparent',
    border: 'none',
    color: 'var(--accent)',
    fontSize: 11,
    cursor: 'pointer',
    padding: 0,
  },
  form: {
    display: 'flex',
    gap: 6,
    padding: '0 12px 8px',
    flexShrink: 0,
  },
  input: {
    flex: 1,
    height: 28,
    padding: '0 8px',
    border: '1px solid var(--border-color)',
    borderRadius: 4,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 12,
    fontFamily: 'var(--font-sans)',
    outline: 'none',
  },
  prioritySelect: {
    height: 28,
    padding: '0 4px',
    border: '1px solid var(--border-color)',
    borderRadius: 4,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 12,
    cursor: 'pointer',
  },
  addBtn: {
    width: 28,
    height: 28,
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 16,
    fontWeight: 600,
    lineHeight: 1,
    flexShrink: 0,
  },
  addBtnDisabled: {
    width: 28,
    height: 28,
    background: 'var(--bg-tertiary)',
    color: 'var(--text-tertiary)',
    border: 'none',
    borderRadius: 4,
    cursor: 'not-allowed',
    fontSize: 16,
    fontWeight: 600,
    lineHeight: 1,
    flexShrink: 0,
  },
  tabs: {
    display: 'flex',
    gap: 4,
    padding: '0 12px 8px',
    flexShrink: 0,
    borderBottom: '1px solid var(--border-color)',
  },
  tab: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    height: 24,
    padding: '0 8px',
    background: 'transparent',
    border: '1px solid transparent',
    borderRadius: 4,
    color: 'var(--text-secondary)',
    fontSize: 11,
    cursor: 'pointer',
    transition: 'background 0.12s',
  },
  tabActive: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    height: 24,
    padding: '0 8px',
    background: 'var(--accent-light)',
    border: '1px solid transparent',
    borderRadius: 4,
    color: 'var(--accent)',
    fontSize: 11,
    fontWeight: 600,
    cursor: 'pointer',
  },
  tabCount: {
    fontSize: 10,
    color: 'var(--text-tertiary)',
    background: 'var(--bg-tertiary)',
    padding: '0 5px',
    borderRadius: 8,
    minWidth: 16,
    textAlign: 'center' as const,
  },
  listArea: {
    flex: 1,
    overflow: 'auto',
    padding: '6px 8px',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '6px 8px',
    marginBottom: 4,
    borderRadius: 6,
    background: 'var(--bg-primary)',
    border: '1px solid var(--border-color)',
    transition: 'background 0.12s',
  },
  checkbox: {
    width: 16,
    height: 16,
    borderRadius: 4,
    border: '1px solid var(--border-color)',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 0,
    flexShrink: 0,
    transition: 'background 0.12s',
  },
  checkmark: {
    color: '#fff',
    fontSize: 11,
    fontWeight: 700,
    lineHeight: 1,
  },
  doingDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: '#fff',
  },
  taskTitle: {
    flex: 1,
    fontSize: 12,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    cursor: 'text',
    minWidth: 0,
  },
  editInput: {
    flex: 1,
    height: 22,
    padding: '0 6px',
    border: '1px solid var(--accent)',
    borderRadius: 3,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 12,
    fontFamily: 'var(--font-sans)',
    outline: 'none',
    minWidth: 0,
  },
  priorityBadge: {
    fontSize: 10,
    padding: '1px 6px',
    borderRadius: 3,
    flexShrink: 0,
    fontWeight: 500,
  },
  rowActions: {
    display: 'flex',
    gap: 2,
    flexShrink: 0,
  },
  iconBtn: {
    width: 22,
    height: 22,
    background: 'transparent',
    border: 'none',
    borderRadius: 3,
    color: 'var(--text-tertiary)',
    cursor: 'pointer',
    fontSize: 13,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 0,
  },
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
    textAlign: 'center',
    gap: 10,
  },
  emptyIcon: {
    fontSize: 28,
    color: 'var(--text-tertiary)',
    opacity: 0.5,
  },
  emptyText: {
    color: 'var(--text-secondary)',
    fontSize: 12,
  },
  footer: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 12px',
    flexShrink: 0,
    borderTop: '1px solid var(--border-color)',
    fontSize: 11,
    color: 'var(--text-tertiary)',
  },
  footerDot: {
    color: 'var(--text-tertiary)',
  },
  footerDone: {
    color: 'var(--success)',
  },
};

export default TasksPanel;
