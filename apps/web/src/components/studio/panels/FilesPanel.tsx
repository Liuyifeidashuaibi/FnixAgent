import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type MouseEvent as ReactMouseEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { sdk } from '@fnixagent/sdk';
import type { AgentOSResponse } from '@fnixagent/sdk';
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  Input,
  ScrollArea,
  Spinner,
  Tabs,
  TabsList,
  TabsTrigger,
  cn,
} from '@fnixagent/ui';

/**
 * FilesPanel — 左侧文件树面板
 *
 * 对接 sdk.agentos.fsList / fsRead / fsWrite / fsMkdir / fsDelete
 * 功能:
 *   - 顶部 Tabs: Explorer / Open Editors
 *   - 工作区名 + 搜索框 + 新建按钮(+)
 *   - 树形懒加载(点击展开才加载子目录)
 *   - 文件图标: SVG(按扩展名着色,.py/.ts=蓝, .md=灰, .json=黄, .yaml=紫)
 *   - 选中态 bg-accent;右键菜单 Rename/Delete/New File/New Folder
 *   - HTML5 拖拽(可拖到编辑器)
 */

// ---- 文件系统条目(防御性类型,后端 data 为动态) ----
interface FsEntry {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  modified?: string;
}

// ---- 从 AgentOSResponse.data 中提取列表(兼容多种字段名) ----
function extractList(resp: AgentOSResponse): FsEntry[] {
  const data = resp.data;
  const candidates: unknown[] = [];
  if (Array.isArray(data)) candidates.push(...data);
  else if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    for (const key of ['entries', 'items', 'files', 'children'] as const) {
      if (Array.isArray(obj[key])) {
        candidates.push(...(obj[key] as unknown[]));
        break;
      }
    }
  }
  return candidates.map((raw) => {
    const o = (raw ?? {}) as Record<string, unknown>;
    const name = String(o.name ?? o.path ?? '');
    const path = String(o.path ?? name);
    const type = o.type === 'directory' || o.is_dir === true ? 'directory' : 'file';
    return {
      name,
      path,
      type: type as 'file' | 'directory',
      size: typeof o.size === 'number' ? o.size : undefined,
      modified: typeof o.modified === 'string' ? o.modified : undefined,
    } satisfies FsEntry;
  });
}

// ---- 扩展名 → 颜色 ----
const EXT_COLOR: Record<string, string> = {
  py: '#007acc',
  ts: '#3178c6',
  tsx: '#3178c6',
  js: '#f59e0b',
  jsx: '#f59e0b',
  md: '#6b7280',
  markdown: '#6b7280',
  json: '#f59e0b',
  yaml: '#8b5cf6',
  yml: '#8b5cf6',
  txt: '#9ca3af',
};

function extOf(name: string): string {
  const i = name.lastIndexOf('.');
  return i >= 0 ? name.slice(i + 1).toLowerCase() : '';
}

// ---- SVG 文件图标 ----
function FileIcon({ name }: { name: string }) {
  const color = EXT_COLOR[extOf(name)] ?? '#9ca3af';
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true" className="shrink-0">
      <path
        d="M3.5 1.5h5l3 3v9a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1z"
        fill={color}
        fillOpacity="0.15"
        stroke={color}
        strokeWidth="1"
      />
      <path d="M8.5 1.5v3h3" stroke={color} strokeWidth="1" fill="none" />
    </svg>
  );
}

// ---- SVG 文件夹图标 ----
function FolderIcon({ open }: { open: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true" className="shrink-0">
      <path
        d="M2 4.5a1 1 0 0 1 1-1h2.5l1.5 1.5h4a1 1 0 0 1 1 1V6H3a1 1 0 0 0-1 1V4.5z"
        fill={open ? '#007acc' : '#9ca3af'}
        fillOpacity="0.25"
      />
      <path
        d="M2 5.5a1 1 0 0 1 1-1h2.5l1.5 1.5h4a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-6.5z"
        fill="none"
        stroke={open ? '#007acc' : '#6b7280'}
        strokeWidth="1"
      />
    </svg>
  );
}

// ---- 右键菜单状态 ----
interface ContextMenuState {
  open: boolean;
  x: number;
  y: number;
  path: string;
  isDir: boolean;
}

// ---- 操作弹窗状态 ----
type ActionDialogState =
  | { mode: 'new-file' | 'new-folder'; parent: string }
  | { mode: 'rename'; path: string; isDir: boolean }
  | { mode: 'delete'; path: string; isDir: boolean }
  | null;

// 路径拼接 / 父目录 / 基名
function joinPath(parent: string, name: string): string {
  if (!parent) return name;
  return parent.replace(/\/+$/, '') + '/' + name;
}
function parentOf(path: string): string {
  const i = path.lastIndexOf('/');
  return i >= 0 ? path.slice(0, i) : '';
}
function basename(path: string): string {
  const i = path.lastIndexOf('/');
  return i >= 0 ? path.slice(i + 1) : path;
}

export interface FilesPanelProps {
  /** 工作区名(可选,默认 "workspace") */
  workspaceName?: string;
  /** 文件被打开(选中)时回调 */
  onFileOpen?: (path: string) => void;
}

export function FilesPanel({ workspaceName = 'workspace', onFileOpen }: FilesPanelProps) {
  const [tab, setTab] = useState<'explorer' | 'open'>('explorer');

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="border-b border-border px-2 pt-2 shrink-0">
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="explorer">Explorer</TabsTrigger>
            <TabsTrigger value="open">Open Editors</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      <div className="flex-1 min-h-0">
        {tab === 'explorer' ? (
          <ExplorerTab workspaceName={workspaceName} onFileOpen={onFileOpen} />
        ) : (
          <OpenEditorsTab onFileOpen={onFileOpen} />
        )}
      </div>
    </div>
  );
}

// ============ Explorer Tab ============

function ExplorerTab({
  workspaceName,
  onFileOpen,
}: {
  workspaceName: string;
  onFileOpen?: (path: string) => void;
}) {
  const [rootEntries, setRootEntries] = useState<FsEntry[]>([]);
  const [childrenMap, setChildrenMap] = useState<Record<string, FsEntry[]>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [globalLoading, setGlobalLoading] = useState(true);
  const [menu, setMenu] = useState<ContextMenuState | null>(null);
  const [action, setAction] = useState<ActionDialogState>(null);
  const [openFiles, setOpenFiles] = useState<string[]>([]);

  const loadDir = useCallback(async (dir: string) => {
    setLoading((s) => new Set(s).add(dir));
    setError(null);
    try {
      const resp = await sdk.agentos.fsList(dir || undefined);
      const entries = extractList(resp).sort((a, b) => {
        if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      if (dir === '') {
        setRootEntries(entries);
      } else {
        setChildrenMap((m) => ({ ...m, [dir]: entries }));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading((s) => {
        const n = new Set(s);
        n.delete(dir);
        return n;
      });
    }
  }, []);

  // 初始加载根目录
  useEffect(() => {
    setGlobalLoading(true);
    loadDir('').finally(() => setGlobalLoading(false));
  }, [loadDir]);

  const toggleExpand = useCallback(
    (entry: FsEntry) => {
      if (entry.type !== 'directory') return;
      setExpanded((s) => {
        const n = new Set(s);
        if (n.has(entry.path)) {
          n.delete(entry.path);
        } else {
          n.add(entry.path);
          if (!childrenMap[entry.path]) void loadDir(entry.path);
        }
        return n;
      });
    },
    [childrenMap, loadDir],
  );

  const handleSelect = useCallback(
    (entry: FsEntry) => {
      setSelected(entry.path);
      if (entry.type === 'file') {
        setOpenFiles((f) => (f.includes(entry.path) ? f : [...f, entry.path]));
        onFileOpen?.(entry.path);
      }
    },
    [onFileOpen],
  );

  // 右键菜单
  const handleContextMenu = useCallback(
    (e: ReactMouseEvent, entry: FsEntry | null) => {
      e.preventDefault();
      e.stopPropagation();
      setMenu({
        open: true,
        x: e.clientX,
        y: e.clientY,
        path: entry?.path ?? '',
        isDir: entry?.type === 'directory',
      });
    },
    [],
  );

  const closeMenu = useCallback(() => setMenu(null), []);

  const reloadParent = useCallback(
    (path: string) => {
      const parent = parentOf(path);
      if (parent) void loadDir(parent);
      else void loadDir('');
    },
    [loadDir],
  );

  const filterEntries = useCallback(
    (entries: FsEntry[]): FsEntry[] => {
      if (!search.trim()) return entries;
      const q = search.toLowerCase();
      return entries.filter(
        (e) => e.name.toLowerCase().includes(q) || e.path.toLowerCase().includes(q),
      );
    },
    [search],
  );

  const rootFiltered = useMemo(() => filterEntries(rootEntries), [rootEntries, filterEntries]);

  // 把已打开文件列表广播给 Open Editors tab
  useEffect(() => {
    window.dispatchEvent(new CustomEvent('fnixagent:open-files', { detail: openFiles }));
  }, [openFiles]);

  return (
    <div
      className="flex h-full flex-col"
      onContextMenu={(e) => {
        if (e.target === e.currentTarget) handleContextMenu(e, null);
      }}
    >
      {/* 顶部:工作区名 + 搜索 + 新建 */}
      <div className="space-y-2 border-b border-border px-2 py-2 shrink-0">
        <div className="flex items-center justify-between">
          <span className="truncate text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {workspaceName}
          </span>
          <button
            type="button"
            title="新建文件"
            onClick={() =>
              setAction({
                mode: 'new-file',
                parent: selected && selected !== '' ? parentOf(selected) : '',
              })
            }
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <PlusIcon />
          </button>
        </div>
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索文件..."
          className="h-8 text-xs"
        />
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="shrink-0 px-3 py-1.5 text-xs text-destructive">⚠️ {error}</div>
      )}

      {/* 文件树 */}
      <ScrollArea className="flex-1 min-h-0" orientation="both">
        <div className="p-1">
          {globalLoading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Spinner size="sm" className="mr-2" /> 加载中...
            </div>
          ) : rootFiltered.length === 0 ? (
            <div className="px-3 py-8 text-center text-xs text-muted-foreground">
              {search ? '无匹配文件' : '空工作区'}
            </div>
          ) : (
            <TreeNodes
              entries={rootFiltered}
              childrenMap={childrenMap}
              expanded={expanded}
              loading={loading}
              selected={selected}
              depth={0}
              onToggle={toggleExpand}
              onSelect={handleSelect}
              onContextMenu={handleContextMenu}
            />
          )}
        </div>
      </ScrollArea>

      {/* 右键菜单(受控,定位到鼠标坐标) */}
      <DropdownMenu open={menu?.open ?? false} onOpenChange={(o) => !o && closeMenu()}>
        <DropdownMenuContent
          className="left-auto top-auto"
          style={{ position: 'fixed', left: menu?.x, top: menu?.y, minWidth: '10rem' }}
        >
          <DropdownMenuLabel>{menu?.path ? basename(menu.path) : '工作区'}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => {
              const parent =
                menu?.path && menu.isDir ? menu.path : parentOf(menu?.path ?? '');
              setAction({ mode: 'new-file', parent });
            }}
          >
            New File
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => {
              const parent =
                menu?.path && menu.isDir ? menu.path : parentOf(menu?.path ?? '');
              setAction({ mode: 'new-folder', parent });
            }}
          >
            New Folder
          </DropdownMenuItem>
          {menu?.path && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() =>
                  setAction({ mode: 'rename', path: menu.path, isDir: menu.isDir })
                }
              >
                Rename
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive"
                onClick={() =>
                  setAction({ mode: 'delete', path: menu.path, isDir: menu.isDir })
                }
              >
                Delete
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* 操作弹窗 */}
      {action && (
        <ActionDialog
          state={action}
          onClose={() => setAction(null)}
          onDone={(changedPath) => {
            setAction(null);
            reloadParent(changedPath);
          }}
        />
      )}
    </div>
  );
}

// ============ 树节点递归渲染 ============

interface TreeNodesProps {
  entries: FsEntry[];
  childrenMap: Record<string, FsEntry[]>;
  expanded: Set<string>;
  loading: Set<string>;
  selected: string | null;
  depth: number;
  onToggle: (entry: FsEntry) => void;
  onSelect: (entry: FsEntry) => void;
  onContextMenu: (e: ReactMouseEvent, entry: FsEntry) => void;
}

function TreeNodes({
  entries,
  childrenMap,
  expanded,
  loading,
  selected,
  depth,
  onToggle,
  onSelect,
  onContextMenu,
}: TreeNodesProps) {
  return (
    <ul className="space-y-0.5">
      {entries.map((entry) => (
        <TreeNode
          key={entry.path}
          entry={entry}
          childrenMap={childrenMap}
          expanded={expanded}
          loading={loading}
          selected={selected}
          depth={depth}
          onToggle={onToggle}
          onSelect={onSelect}
          onContextMenu={onContextMenu}
        />
      ))}
    </ul>
  );
}

function TreeNode({
  entry,
  childrenMap,
  expanded,
  loading,
  selected,
  depth,
  onToggle,
  onSelect,
  onContextMenu,
}: Omit<TreeNodesProps, 'entries'> & { entry: FsEntry }) {
  const isExpanded = expanded.has(entry.path);
  const isLoading = loading.has(entry.path);
  const isSelected = selected === entry.path;
  const children = isExpanded ? childrenMap[entry.path] ?? [] : [];

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter') {
      entry.type === 'directory' ? onToggle(entry) : onSelect(entry);
    }
  };

  return (
    <li>
      <div
        role="button"
        tabIndex={0}
        draggable={entry.type === 'file'}
        onDragStart={(e) => {
          e.dataTransfer.setData('text/plain', entry.path);
          e.dataTransfer.setData('application/x-fnixagent-path', entry.path);
          e.dataTransfer.effectAllowed = 'copy';
        }}
        onClick={() => (entry.type === 'directory' ? onToggle(entry) : onSelect(entry))}
        onKeyDown={onKeyDown}
        onContextMenu={(e) => onContextMenu(e, entry)}
        className={cn(
          'group flex cursor-pointer select-none items-center gap-1.5 rounded px-1.5 py-1 text-sm',
          'hover:bg-accent',
          isSelected && 'bg-accent',
        )}
        style={{ paddingLeft: `${depth * 12 + 6}px` }}
        title={entry.path}
      >
        {entry.type === 'directory' ? (
          <>
            <span className="inline-flex w-3 justify-center text-[10px] text-muted-foreground">
              {isLoading ? '⟳' : isExpanded ? '▾' : '▸'}
            </span>
            <FolderIcon open={isExpanded} />
          </>
        ) : (
          <>
            <span className="w-3" />
            <FileIcon name={entry.name} />
          </>
        )}
        <span className="flex-1 truncate">{entry.name}</span>
      </div>
      {isExpanded && children.length > 0 && (
        <TreeNodes
          entries={children}
          childrenMap={childrenMap}
          expanded={expanded}
          loading={loading}
          selected={selected}
          depth={depth + 1}
          onToggle={onToggle}
          onSelect={onSelect}
          onContextMenu={onContextMenu}
        />
      )}
    </li>
  );
}

// ============ Open Editors Tab ============

function OpenEditorsTab({ onFileOpen }: { onFileOpen?: (path: string) => void }) {
  const [files, setFiles] = useState<string[]>([]);

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<string[]>).detail;
      if (Array.isArray(detail)) setFiles(detail);
    };
    window.addEventListener('fnixagent:open-files', handler);
    return () => window.removeEventListener('fnixagent:open-files', handler);
  }, []);

  return (
    <ScrollArea className="h-full" orientation="both">
      <div className="p-1">
        {files.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs text-muted-foreground">
            暂无打开的文件
          </div>
        ) : (
          <ul className="space-y-0.5">
            {files.map((path) => (
              <li
                key={path}
                className="group flex cursor-pointer items-center gap-1.5 rounded px-1.5 py-1 text-sm hover:bg-accent"
                onClick={() => onFileOpen?.(path)}
              >
                <FileIcon name={basename(path)} />
                <span className="flex-1 truncate">{basename(path)}</span>
                <span className="truncate text-[10px] text-muted-foreground">
                  {parentOf(path)}
                </span>
                <button
                  type="button"
                  className="rounded p-0.5 text-muted-foreground opacity-0 hover:bg-border group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFiles((f) => f.filter((p) => p !== path));
                    window.dispatchEvent(
                      new CustomEvent('fnixagent:open-files', {
                        detail: files.filter((p) => p !== path),
                      }),
                    );
                  }}
                  title="关闭"
                >
                  <CloseIcon />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </ScrollArea>
  );
}

// ============ 操作弹窗(新建/重命名/删除) ============

function ActionDialog({
  state,
  onClose,
  onDone,
}: {
  state: ActionDialogState;
  onClose: () => void;
  onDone: (changedPath: string) => void;
}) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // 切换 state 时重置
  useEffect(() => {
    setName('');
    setErr(null);
    if (state?.mode === 'rename') setName(basename(state.path));
  }, [state]);

  if (!state) return null;

  const title =
    state.mode === 'new-file'
      ? '新建文件'
      : state.mode === 'new-folder'
        ? '新建文件夹'
        : state.mode === 'rename'
          ? '重命名'
          : '删除';

  const needName = state.mode !== 'delete';

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      if (state!.mode === 'new-file') {
        const target = joinPath(state!.parent, name.trim());
        await sdk.agentos.fsWrite({ path: target, content: '' });
        onDone(target);
      } else if (state!.mode === 'new-folder') {
        const target = joinPath(state!.parent, name.trim());
        await sdk.agentos.fsMkdir(target);
        onDone(target);
      } else if (state!.mode === 'rename') {
        const src = state!.path;
        const target = joinPath(parentOf(src), name.trim());
        if (target === src) {
          onDone(src);
          return;
        }
        // 读取旧内容 → 写入新路径 → 删除旧路径
        const readResp = await sdk.agentos.fsRead(src);
        const content = extractText(readResp);
        await sdk.agentos.fsWrite({ path: target, content });
        await sdk.agentos.fsDelete(src);
        onDone(src);
      } else if (state!.mode === 'delete') {
        await sdk.agentos.fsDelete(state!.path);
        onDone(state!.path);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {state.mode === 'delete'
              ? `确认删除 "${basename(state.path)}"? 此操作不可撤销。`
              : state.mode === 'rename'
                ? `重命名 "${basename(state.path)}" 为:`
                : `路径: ${state.parent || '/'}`}
          </DialogDescription>
        </DialogHeader>

        {needName && (
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">
              {state.mode === 'rename' ? '新名称' : '名称'}
            </label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && name.trim() && !busy) void submit();
              }}
              placeholder={state.mode === 'new-folder' ? 'folder-name' : 'file.txt'}
            />
          </div>
        )}

        {err && <p className="text-xs text-destructive">⚠️ {err}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            取消
          </Button>
          <Button
            variant={state.mode === 'delete' ? 'destructive' : 'default'}
            onClick={() => void submit()}
            disabled={busy || (needName && !name.trim())}
          >
            {busy ? '处理中...' : state.mode === 'delete' ? '删除' : '确定'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// 从 fsRead 响应中提取文本内容
function extractText(resp: AgentOSResponse): string {
  const data = resp.data;
  if (typeof data === 'string') return data;
  if (data && typeof data === 'object') {
    const o = data as Record<string, unknown>;
    if (typeof o.content === 'string') return o.content;
    if (typeof o.text === 'string') return o.text;
    if (typeof o.data === 'string') return o.data;
  }
  return '';
}

// ============ 小图标 ============

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
