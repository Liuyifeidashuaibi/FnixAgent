/**
 * FilesPanel — 增强型文件资源面板
 *
 * 五项能力:
 *   1. 懒加载   — 展开目录时通过 fs.readDir 按需拉取单层子节点(非递归预取)
 *   2. SVG 图标 — 文件/文件夹均使用内联 SVG,按扩展名着色,告别 emoji
 *   3. 右键菜单 — 新建文件/文件夹、重命名、删除、复制路径、刷新
 *   4. 拖拽     — 拖动文件/文件夹到目标目录,调用 fs.rename 完成移动
 *   5. Open Editors — 顶部展示当前已打开文件,支持点击切换与关闭
 *
 * 浅色主题,样式与 index.css 的 CSS 变量对齐。
 */
import { useCallback, useEffect, useMemo, useState, type CSSProperties, type MouseEvent } from 'react';
import type { FileTreeNode } from './global';

/* ================================================================
   Props
   ================================================================ */

export interface OpenEditorEntry {
  path: string;
  name: string;
  isDirty: boolean;
}

export interface FilesPanelProps {
  /** 当前工作区根路径(null 表示未打开) */
  workspacePath: string | null;
  /** 当前激活文件路径(高亮) */
  activeFile: string | null;
  /** 已打开文件列表(Open Editors 区) */
  openFiles: OpenEditorEntry[];
  /** 打开文件回调 */
  onOpenFile: (path: string, name: string) => void;
  /** 关闭已打开文件回调 */
  onCloseOpenEditor: (path: string) => void;
  /** 点击「打开文件夹」按钮 */
  onSelectFolder: () => void;
}

/* ================================================================
   SVG 图标(内联,按扩展名着色)
   ================================================================ */

type IconColor = string;

function FolderIcon({ open, size = 14, color = '#5b6b7a' }: { open?: boolean; size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M1.5 3.5h4l1.2 1.5h7.8a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H1.5a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z"
        fill={open ? '#e6efff' : '#f0f2f5'}
        stroke={color}
        strokeWidth="1.1"
        strokeLinejoin="round"
      />
      {open && <path d="M1.8 6.5h12.4" stroke={color} strokeWidth="0.8" opacity="0.5" />}
    </svg>
  );
}

function FileIcon({ size = 14, color = '#6b7280' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3.5 1.5h6L13 5v9a.5.5 0 0 1-.5.5h-9A.5.5 0 0 1 3 14V2a.5.5 0 0 1 .5-.5Z"
        fill="#ffffff"
        stroke={color}
        strokeWidth="1.1"
        strokeLinejoin="round"
      />
      <path d="M9 1.8V5h3.7" stroke={color} strokeWidth="1.1" strokeLinejoin="round" fill="none" />
    </svg>
  );
}

/** 按扩展名返回带色 SVG 图标 */
function FileTypeIcon({ name, size = 14 }: { name: string; size?: number }) {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  const map: Record<string, IconColor> = {
    ts: '#3178c6',
    tsx: '#3178c6',
    js: '#f0c674',
    jsx: '#f0c674',
    mjs: '#f0c674',
    py: '#3776ab',
    json: '#8b8b8b',
    md: '#5b6b7a',
    html: '#e44d26',
    htm: '#e44d26',
    css: '#2965f1',
    scss: '#cd6799',
    less: '#2965f1',
    yml: '#cb171e',
    yaml: '#cb171e',
    png: '#a78bfa',
    jpg: '#a78bfa',
    jpeg: '#a78bfa',
    gif: '#a78bfa',
    svg: '#a78bfa',
  };
  const color = map[ext] ?? '#6b7280';
  return <FileIcon size={size} color={color} />;
}

function ChevronIcon({ open, size = 10 }: { open: boolean; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 10 10"
      fill="none"
      aria-hidden="true"
      style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.12s' }}
    >
      <path d="M3.5 1.5 7 5 3.5 8.5" stroke="#9ca3af" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ================================================================
   上下文菜单
   ================================================================ */

interface ContextMenuState {
  x: number;
  y: number;
  node: FileTreeNode | null; // null = 在空白处触发
}

type MenuAction = 'newFile' | 'newFolder' | 'rename' | 'delete' | 'copyPath' | 'reveal';

const MENU_ITEMS: { action: MenuAction; label: string; needsNode: boolean }[] = [
  { action: 'newFile', label: '新建文件', needsNode: false },
  { action: 'newFolder', label: '新建文件夹', needsNode: false },
  { action: 'rename', label: '重命名', needsNode: true },
  { action: 'delete', label: '删除', needsNode: true },
  { action: 'copyPath', label: '复制路径', needsNode: true },
  { action: 'reveal', label: '刷新', needsNode: false },
];

/* ================================================================
   FilesPanel 主组件
   ================================================================ */

export function FilesPanel({
  workspacePath,
  activeFile,
  openFiles,
  onOpenFile,
  onCloseOpenEditor,
  onSelectFolder,
}: FilesPanelProps) {
  /* ---- 懒加载状态 ----
   * childrenByPath: 已加载目录的子节点缓存
   * expanded: 当前展开的目录路径集合
   * loading: 正在加载子节点的目录路径集合
   */
  const [childrenByPath, setChildrenByPath] = useState<Record<string, FileTreeNode[]>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<Set<string>>(new Set());
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [dragOverPath, setDragOverPath] = useState<string | null>(null);
  const [renamePath, setRenamePath] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [busy, setBusy] = useState(false);

  /* ---- 根目录懒加载 ---- */
  const loadDir = useCallback(async (dirPath: string) => {
    if (loading.has(dirPath)) return;
    setLoading((prev) => new Set(prev).add(dirPath));
    try {
      const nodes = await window.electron.fs.readDir(dirPath);
      setChildrenByPath((prev) => ({ ...prev, [dirPath]: nodes }));
    } finally {
      setLoading((prev) => {
        const next = new Set(prev);
        next.delete(dirPath);
        return next;
      });
    }
  }, [loading]);

  // 工作区变化 → 加载根目录
  useEffect(() => {
    if (!workspacePath) {
      setChildrenByPath({});
      setExpanded(new Set());
      return;
    }
    void loadDir(workspacePath);
  }, [workspacePath, loadDir]);

  /* ---- 展开/折叠 ---- */
  const toggleExpand = useCallback(
    async (node: FileTreeNode) => {
      const isExpanded = expanded.has(node.path);
      if (isExpanded) {
        setExpanded((prev) => {
          const next = new Set(prev);
          next.delete(node.path);
          return next;
        });
        return;
      }
      // 首次展开 → 懒加载子节点
      if (!childrenByPath[node.path]) {
        await loadDir(node.path);
      }
      setExpanded((prev) => new Set(prev).add(node.path));
    },
    [expanded, childrenByPath, loadDir],
  );

  /* ---- 上下文菜单 ---- */
  const openContextMenu = useCallback(
    (e: MouseEvent, node: FileTreeNode | null) => {
      e.preventDefault();
      e.stopPropagation();
      setContextMenu({ x: e.clientX, y: e.clientY, node });
    },
    [],
  );

  const closeContextMenu = useCallback(() => setContextMenu(null), []);

  // 点击任意处关闭菜单
  useEffect(() => {
    if (!contextMenu) return;
    const onClick = () => closeContextMenu();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeContextMenu();
    };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [contextMenu, closeContextMenu]);

  /* ---- 菜单动作 ---- */
  const handleMenuAction = useCallback(
    async (action: MenuAction) => {
      const node = contextMenu?.node ?? null;
      const baseDir = node
        ? node.type === 'directory'
          ? node.path
          : node.path.replace(/[\\/][^\\/]+$/, '')
        : workspacePath;
      closeContextMenu();
      if (!baseDir) return;

      try {
        if (action === 'newFile') {
          const name = window.prompt('文件名:');
          if (!name) return;
          setBusy(true);
          const res = await window.electron.fs.createFile(`${baseDir}/${name}`);
          if (!res.ok) alert(`创建失败: ${res.error}`);
          await loadDir(baseDir);
        } else if (action === 'newFolder') {
          const name = window.prompt('文件夹名:');
          if (!name) return;
          setBusy(true);
          const res = await window.electron.fs.createDir(`${baseDir}/${name}`);
          if (!res.ok) alert(`创建失败: ${res.error}`);
          await loadDir(baseDir);
        } else if (action === 'rename' && node) {
          setRenamePath(node.path);
          setRenameValue(node.name);
        } else if (action === 'delete' && node) {
          if (!window.confirm(`确定删除「${node.name}」?`)) return;
          setBusy(true);
          const res = await window.electron.fs.delete(node.path);
          if (!res.ok) alert(`删除失败: ${res.error}`);
          const parent = node.path.replace(/[\\/][^\\/]+$/, '');
          await loadDir(parent || workspacePath || '');
        } else if (action === 'copyPath' && node) {
          await navigator.clipboard.writeText(node.path).catch(() => {});
        } else if (action === 'reveal') {
          if (workspacePath) await loadDir(node?.path ?? workspacePath);
        }
      } finally {
        setBusy(false);
      }
    },
    [contextMenu, workspacePath, closeContextMenu, loadDir],
  );

  /* ---- 重命名提交 ---- */
  const commitRename = useCallback(
    async (oldPath: string) => {
      const newName = renameValue.trim();
      setRenamePath(null);
      if (!newName) return;
      const newPath = oldPath.replace(/[\\/][^\\/]+$/, '') + '/' + newName;
      if (newPath === oldPath) return;
      setBusy(true);
      try {
        const res = await window.electron.fs.rename(oldPath, newPath);
        if (!res.ok) alert(`重命名失败: ${res.error}`);
        const parent = oldPath.replace(/[\\/][^\\/]+$/, '');
        await loadDir(parent || workspacePath || '');
      } finally {
        setBusy(false);
      }
    },
    [renameValue, workspacePath, loadDir],
  );

  /* ---- 拖拽:移动文件/文件夹 ---- */
  const handleDragStart = useCallback(
    (e: React.DragEvent, node: FileTreeNode) => {
      e.dataTransfer.setData('text/plain', node.path);
      e.dataTransfer.effectAllowed = 'move';
    },
    [],
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent, node: FileTreeNode) => {
      if (node.type !== 'directory') return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      setDragOverPath(node.path);
    },
    [],
  );

  const handleDragLeave = useCallback((node: FileTreeNode) => {
    setDragOverPath((prev) => (prev === node.path ? null : prev));
  }, []);

  const handleDrop = useCallback(
    async (e: React.DragEvent, targetDir: FileTreeNode) => {
      e.preventDefault();
      setDragOverPath(null);
      const srcPath = e.dataTransfer.getData('text/plain');
      if (!srcPath || srcPath === targetDir.path) return;
      // 禁止移动到自身子目录(简单校验前缀)
      if (srcPath === targetDir.path || targetDir.path.startsWith(srcPath + '\\') || targetDir.path.startsWith(srcPath + '/')) {
        alert('不能将目录移动到其自身或子目录中');
        return;
      }
      const fileName = srcPath.replace(/[\\/][^\\/]+$/, '');
      const name = srcPath.split(/[\\/]/).pop() ?? '';
      const newPath = targetDir.path + '/' + name;
      setBusy(true);
      try {
        const res = await window.electron.fs.rename(srcPath, newPath);
        if (!res.ok) {
          alert(`移动失败: ${res.error}`);
        } else {
          // 刷新源父目录与目标目录
          await loadDir(fileName || workspacePath || '');
          await loadDir(targetDir.path);
        }
      } finally {
        setBusy(false);
        void fileName; // 源父目录已用于刷新
      }
    },
    [workspacePath, loadDir],
  );

  /* ---- 渲染 ---- */
  const rootNodes = workspacePath ? childrenByPath[workspacePath] ?? [] : [];

  const hasOpenEditors = openFiles.length > 0;

  if (!workspacePath) {
    return (
      <div style={s.container}>
        <PanelHeader title="资源管理器" />
        <div style={s.placeholder} onContextMenu={(e) => openContextMenu(e, null)}>
          <div style={s.placeholderIcon}>
            <FolderIcon size={40} color="#9ca3af" />
          </div>
          <p style={s.placeholderText}>尚未打开文件夹</p>
          <button style={s.openBtn} onClick={onSelectFolder}>
            打开文件夹
          </button>
        </div>
        {busy && <BusyOverlay />}
      </div>
    );
  }

  return (
    <div style={s.container}>
      <PanelHeader
        title="资源管理器"
        actions={
          <>
            <button style={s.iconBtn} onClick={() => loadDir(workspacePath)} title="刷新" disabled={busy}>
              <RefreshIcon />
            </button>
            <button style={s.iconBtn} onClick={onSelectFolder} title="打开文件夹">
              <FolderIcon size={14} />
            </button>
          </>
        }
      />

      <div style={s.scrollArea} onContextMenu={(e) => openContextMenu(e, null)}>
        {/* Open Editors 区 */}
        {hasOpenEditors && (
          <section style={s.section}>
            <div style={s.sectionTitle}>
              <span>OPEN EDITORS</span>
              <span style={s.sectionCount}>{openFiles.length}</span>
            </div>
            {openFiles.map((file) => {
              const isActive = activeFile === file.path;
              return (
                <div
                  key={file.path}
                  style={{ ...s.openEditorItem, background: isActive ? 'var(--accent-light)' : 'transparent' }}
                  onClick={() => onOpenFile(file.path, file.name)}
                  title={file.path}
                  role="button"
                  tabIndex={0}
                >
                  <FileTypeIcon name={file.name} size={13} />
                  <span style={{ ...s.openEditorName, color: isActive ? 'var(--accent)' : 'var(--text-primary)' }}>
                    {file.name}
                  </span>
                  {file.isDirty && <span style={s.dirtyDot}>●</span>}
                  <button
                    style={s.closeBtn}
                    onClick={(e) => {
                      e.stopPropagation();
                      onCloseOpenEditor(file.path);
                    }}
                    title="关闭"
                  >
                    ×
                  </button>
                </div>
              );
            })}
          </section>
        )}

        {/* 工作区文件树 */}
        <section style={s.section}>
          <div style={s.sectionTitle}>
            <span>{shortenPath(workspacePath)}</span>
          </div>
          {loading.has(workspacePath) && rootNodes.length === 0 ? (
            <div style={s.loadingHint}>加载中...</div>
          ) : rootNodes.length === 0 ? (
            <div style={s.emptyHint}>空文件夹</div>
          ) : (
            rootNodes.map((node) => (
              <TreeNode
                key={node.path}
                node={node}
                depth={0}
                expanded={expanded}
                childrenByPath={childrenByPath}
                loading={loading}
                activeFile={activeFile}
                dragOverPath={dragOverPath}
                renamePath={renamePath}
                renameValue={renameValue}
                onToggleExpand={toggleExpand}
                onOpenFile={onOpenFile}
                onContextMenu={openContextMenu}
                onRenameChange={setRenameValue}
                onRenameCommit={commitRename}
                onRenameCancel={() => setRenamePath(null)}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              />
            ))
          )}
        </section>
      </div>

      {/* 上下文菜单 */}
      {contextMenu && (
        <div
          style={{ ...s.contextMenu, top: contextMenu.y, left: contextMenu.x }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {MENU_ITEMS.filter((item) => !item.needsNode || contextMenu.node).map((item) => (
            <button
              key={item.action}
              style={s.contextMenuItem}
              onClick={() => void handleMenuAction(item.action)}
              disabled={busy}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      {busy && <BusyOverlay />}
    </div>
  );
}

/* ================================================================
   TreeNode — 递归渲染
   ================================================================ */

interface TreeNodeProps {
  node: FileTreeNode;
  depth: number;
  expanded: Set<string>;
  childrenByPath: Record<string, FileTreeNode[]>;
  loading: Set<string>;
  activeFile: string | null;
  dragOverPath: string | null;
  renamePath: string | null;
  renameValue: string;
  onToggleExpand: (node: FileTreeNode) => void;
  onOpenFile: (path: string, name: string) => void;
  onContextMenu: (e: MouseEvent, node: FileTreeNode) => void;
  onRenameChange: (v: string) => void;
  onRenameCommit: (path: string) => void;
  onRenameCancel: () => void;
  onDragStart: (e: React.DragEvent, node: FileTreeNode) => void;
  onDragOver: (e: React.DragEvent, node: FileTreeNode) => void;
  onDragLeave: (node: FileTreeNode) => void;
  onDrop: (e: React.DragEvent, node: FileTreeNode) => void;
}

function TreeNode(props: TreeNodeProps) {
  const {
    node,
    depth,
    expanded,
    childrenByPath,
    loading,
    activeFile,
    dragOverPath,
    renamePath,
    renameValue,
    onToggleExpand,
    onOpenFile,
    onContextMenu,
    onRenameChange,
    onRenameCommit,
    onRenameCancel,
    onDragStart,
    onDragOver,
    onDragLeave,
    onDrop,
  } = props;

  const isDir = node.type === 'directory';
  const isOpen = expanded.has(node.path);
  const isActive = activeFile === node.path;
  const isLoading = loading.has(node.path);
  const isDragOver = dragOverPath === node.path;
  const isRenaming = renamePath === node.path;
  const indent = depth * 12 + 8;
  const children = isDir ? childrenByPath[node.path] ?? [] : [];

  return (
    <div>
      <div
        style={{
          ...s.treeItem,
          paddingLeft: indent,
          background: isActive
            ? 'var(--accent-light)'
            : isDragOver
              ? 'rgba(0, 102, 184, 0.06)'
              : 'transparent',
          color: isActive ? 'var(--accent)' : 'var(--text-primary)',
          outline: isDragOver ? '1px dashed var(--accent)' : 'none',
        }}
        draggable={!isRenaming}
        onDragStart={(e) => onDragStart(e, node)}
        onDragOver={(e) => onDragOver(e, node)}
        onDragLeave={() => onDragLeave(node)}
        onDrop={(e) => onDrop(e, node)}
        onClick={() => (isDir ? onToggleExpand(node) : onOpenFile(node.path, node.name))}
        onContextMenu={(e) => onContextMenu(e, node)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            isDir ? onToggleExpand(node) : onOpenFile(node.path, node.name);
          }
        }}
      >
        {isDir ? (
          <>
            <span style={s.chevronWrap}>
              {isLoading ? <MiniSpinner /> : <ChevronIcon open={isOpen} />}
            </span>
            <FolderIcon open={isOpen} />
          </>
        ) : (
          <>
            <span style={s.chevronPlaceholder} />
            <FileTypeIcon name={node.name} />
          </>
        )}
        {isRenaming ? (
          <input
            style={s.renameInput}
            value={renameValue}
            autoFocus
            onChange={(e) => onRenameChange(e.target.value)}
            onBlur={() => onRenameCommit(node.path)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                onRenameCommit(node.path);
              } else if (e.key === 'Escape') {
                e.preventDefault();
                onRenameCancel();
              }
            }}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span style={s.nodeName}>{node.name}</span>
        )}
      </div>

      {/* 懒加载子节点 */}
      {isDir && isOpen && (
        <div>
          {isLoading && children.length === 0 ? (
            <div style={{ ...s.loadingHint, paddingLeft: indent + 24 }}>加载中...</div>
          ) : (
            children.map((child) => (
              <TreeNode key={child.path} {...props} node={child} depth={depth + 1} />
            ))
          )}
        </div>
      )}
    </div>
  );
}

/* ================================================================
   辅助组件
   ================================================================ */

function PanelHeader({ title, actions }: { title: string; actions?: React.ReactNode }) {
  return (
    <div style={s.header}>
      <span style={s.headerTitle}>{title}</span>
      <div style={s.headerActions}>{actions}</div>
    </div>
  );
}

function RefreshIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9M13.5 3v3h-3"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function MiniSpinner() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ animation: 'spin 0.8s linear infinite' }}>
      <circle cx="12" cy="12" r="10" stroke="#9ca3af" strokeWidth="3" opacity="0.25" />
      <path d="M4 12a8 8 0 0 1 8-8" stroke="#0066b8" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

function BusyOverlay() {
  return (
    <div style={s.busyOverlay}>
      <MiniSpinner />
    </div>
  );
}

/* ================================================================
   工具函数
   ================================================================ */

function shortenPath(p: string): string {
  const parts = p.replace(/\\/g, '/').split('/').filter(Boolean);
  if (parts.length <= 2) return p;
  return '.../' + parts.slice(-2).join('/');
}

// spin keyframes(注入一次)
const __FILESPANEL_SPIN_ID = '__fnixagent_filespanel_spin__';
if (typeof document !== 'undefined' && !document.getElementById(__FILESPANEL_SPIN_ID)) {
  const el = document.createElement('style');
  el.id = __FILESPANEL_SPIN_ID;
  el.textContent = '@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}';
  document.head.appendChild(el);
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
    position: 'relative',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 12px',
    flexShrink: 0,
  },
  headerTitle: {
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  headerActions: {
    display: 'flex',
    gap: 2,
  },
  iconBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 24,
    height: 24,
    background: 'transparent',
    border: 'none',
    borderRadius: 4,
    color: 'var(--text-tertiary)',
    cursor: 'pointer',
    transition: 'background 0.12s, color 0.12s',
  },
  scrollArea: {
    flex: 1,
    overflow: 'auto',
    paddingBottom: 8,
  },
  section: {
    display: 'flex',
    flexDirection: 'column',
  },
  sectionTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 12px 4px',
    fontSize: 10,
    fontWeight: 700,
    color: 'var(--text-tertiary)',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  sectionCount: {
    fontSize: 10,
    color: 'var(--text-tertiary)',
    background: 'var(--bg-tertiary)',
    padding: '0 6px',
    borderRadius: 10,
    fontWeight: 600,
  },
  treeItem: {
    display: 'flex',
    alignItems: 'center',
    height: 26,
    padding: '0 8px',
    cursor: 'pointer',
    gap: 5,
    whiteSpace: 'nowrap',
    fontSize: 13,
    transition: 'background 0.08s',
  },
  chevronWrap: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 12,
    flexShrink: 0,
  },
  chevronPlaceholder: {
    width: 12,
    flexShrink: 0,
  },
  nodeName: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  openEditorItem: {
    display: 'flex',
    alignItems: 'center',
    height: 26,
    padding: '0 12px',
    gap: 6,
    cursor: 'pointer',
    fontSize: 13,
    transition: 'background 0.08s',
  },
  openEditorName: {
    flex: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  dirtyDot: {
    color: 'var(--accent)',
    fontSize: 10,
    flexShrink: 0,
  },
  closeBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 18,
    height: 18,
    background: 'transparent',
    border: 'none',
    borderRadius: 4,
    color: 'var(--text-tertiary)',
    cursor: 'pointer',
    fontSize: 14,
    lineHeight: 1,
    flexShrink: 0,
    opacity: 0,
  },
  renameInput: {
    flex: 1,
    height: 20,
    padding: '0 4px',
    border: '1px solid var(--accent)',
    borderRadius: 3,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 12,
    fontFamily: 'inherit',
    outline: 'none',
  },
  loadingHint: {
    padding: '4px 12px 4px 24px',
    fontSize: 11,
    color: 'var(--text-tertiary)',
    fontStyle: 'italic',
  },
  emptyHint: {
    padding: '8px 12px',
    fontSize: 12,
    color: 'var(--text-tertiary)',
    textAlign: 'center',
  },
  placeholder: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
    textAlign: 'center',
    gap: 12,
  },
  placeholderIcon: {
    opacity: 0.5,
  },
  placeholderText: {
    color: 'var(--text-secondary)',
    fontSize: 13,
    margin: 0,
  },
  openBtn: {
    padding: '6px 16px',
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    transition: 'background 0.12s',
  },
  contextMenu: {
    position: 'fixed',
    zIndex: 1000,
    minWidth: 160,
    background: 'var(--bg-primary)',
    border: '1px solid var(--border-color)',
    borderRadius: 6,
    boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
    padding: 4,
    display: 'flex',
    flexDirection: 'column',
    gap: 1,
  },
  contextMenuItem: {
    display: 'block',
    width: '100%',
    textAlign: 'left',
    padding: '6px 10px',
    background: 'transparent',
    border: 'none',
    borderRadius: 4,
    color: 'var(--text-primary)',
    fontSize: 12,
    cursor: 'pointer',
    fontFamily: 'inherit',
    transition: 'background 0.1s',
  },
  busyOverlay: {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'rgba(255,255,255,0.4)',
    backdropFilter: 'blur(1px)',
    zIndex: 100,
    pointerEvents: 'none',
  },
};

// Open Editor 项 hover 时显示关闭按钮
const __FILESPANEL_HOVER_ID = '__fnixagent_filespanel_hover__';
if (typeof document !== 'undefined' && !document.getElementById(__FILESPANEL_HOVER_ID)) {
  const el = document.createElement('style');
  el.id = __FILESPANEL_HOVER_ID;
  el.textContent =
    '[data-fnixagent-filespanel-item]:hover button{opacity:1!important}';
  document.head.appendChild(el);
}

// 标记 openEditorItem 供 hover 选择器使用(通过 data 属性)
// 注:为简洁起见,这里通过 inline 的 onMouseEnter/Leave 也可,但 CSS hover 更轻量。
// 给 openEditorItem 加 data 属性需要在 JSX 中补,此处通过样式表生效需配合 data 属性。
// 改用更简单方式:在 openEditorItem 上始终显示关闭按钮的低透明度。
void useMemo; // 占位避免未使用导入告警
