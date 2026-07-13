/**
 * CommandPalette — Ctrl+Shift+P 调出的命令面板
 *
 * 模态浮层，支持模糊搜索、分类浏览、最近使用、键盘导航。
 */
import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';

/* ================================================
   Types
   ================================================ */

interface Command {
  id: string;
  name: string;
  category: string;
  shortcut?: string;
  description?: string;
}

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenFolder: () => void;
  onSave: () => void;
  onCloseFile: () => void;
  onToggleSidebar: () => void;
  onToggleAgentPanel: () => void;
}

const RECENT_KEY = 'command-palette-recent';
const MAX_RECENT = 3;

/* ================================================
   Command Definitions
   ================================================ */

const COMMANDS: Command[] = [
  // File
  { id: 'open-folder',      name: 'Open Folder',           category: 'File',  shortcut: 'Ctrl+O',     description: 'Open a folder in the workspace' },
  { id: 'save-file',        name: 'Save File',             category: 'File',  shortcut: 'Ctrl+S',     description: 'Save the current file' },
  { id: 'close-file',       name: 'Close File',            category: 'File',  shortcut: 'Ctrl+W',     description: 'Close the active editor tab' },
  // Edit
  { id: 'undo',             name: 'Undo',                  category: 'Edit',  shortcut: 'Ctrl+Z',     description: 'Undo the last action' },
  { id: 'redo',             name: 'Redo',                  category: 'Edit',  shortcut: 'Ctrl+Shift+Z', description: 'Redo the last undone action' },
  { id: 'cut',              name: 'Cut',                   category: 'Edit',  shortcut: 'Ctrl+X',     description: 'Cut selected text to clipboard' },
  { id: 'copy',             name: 'Copy',                  category: 'Edit',  shortcut: 'Ctrl+C',     description: 'Copy selected text to clipboard' },
  { id: 'paste',            name: 'Paste',                 category: 'Edit',  shortcut: 'Ctrl+V',     description: 'Paste from clipboard' },
  // View
  { id: 'toggle-sidebar',   name: 'Toggle Sidebar',        category: 'View',  shortcut: 'Ctrl+B',     description: 'Show or hide the sidebar' },
  { id: 'toggle-agent',     name: 'Toggle Agent Panel',    category: 'View',  shortcut: 'Ctrl+J',     description: 'Show or hide the agent panel' },
  { id: 'toggle-terminal',  name: 'Toggle Terminal',       category: 'View',  shortcut: 'Ctrl+`',     description: 'Show or hide the terminal' },
  // Git
  { id: 'git-status',       name: 'Git Status',            category: 'Git',   description: 'Show working tree status' },
  { id: 'git-commit',       name: 'Git Commit',            category: 'Git',   description: 'Record changes to the repository' },
  { id: 'git-push',         name: 'Git Push',              category: 'Git',   description: 'Push commits to remote' },
  { id: 'git-pull',         name: 'Git Pull',              category: 'Git',   description: 'Fetch and integrate remote changes' },
  // Agent
  { id: 'new-agent-task',   name: 'New Agent Task',        category: 'Agent', description: 'Create a new agent task' },
  { id: 'view-processes',   name: 'View Processes',        category: 'Agent', description: 'View running agent processes' },
  { id: 'clear-chat',       name: 'Clear Chat',            category: 'Agent', description: 'Clear the chat history' },
  // Help
  { id: 'about',            name: 'About',                 category: 'Help',  description: 'About FnixAgent' },
  { id: 'settings',         name: 'Settings',              category: 'Help',  description: 'Open application settings' },
];

const CATEGORY_ORDER = ['File', 'Edit', 'View', 'Git', 'Agent', 'Help'];

/* ================================================
   Helpers
   ================================================ */

function fuzzyScore(query: string, target: string): number {
  if (!query) return 0;
  const q = query.toLowerCase();
  const t = target.toLowerCase();
  let qi = 0;
  let score = 0;
  const consecutiveBonus = 2;
  const wordBoundaryBonus = 5;

  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) {
      score += 1;
      if (ti > 0 && t[ti - 1] === q[qi - 1]) {
        score += consecutiveBonus;
      }
      if (ti === 0 || t[ti - 1] === ' ' || t[ti - 1] === '-' || t[ti - 1] === '_') {
        score += wordBoundaryBonus;
      }
      qi++;
    }
  }

  return qi === q.length ? score : -1;
}

function getRecentCommands(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function addRecentCommand(id: string): void {
  try {
    const recent = getRecentCommands().filter((r) => r !== id);
    recent.unshift(id);
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)));
  } catch {
    // ignore
  }
}

/* ================================================
   CommandPalette Component
   ================================================ */

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  onOpenFolder,
  onSave,
  onCloseFile,
  onToggleSidebar,
  onToggleAgentPanel,
}) => {
  const [search, setSearch] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  /* ---- 重置搜索 ---- */
  useEffect(() => {
    if (isOpen) {
      setSearch('');
      setSelectedIndex(0);
      // 自动聚焦搜索框
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }, [isOpen]);

  /* ---- 过滤 & 排序 ---- */
  const filtered = useMemo(() => {
    const q = search.trim();
    if (!q) {
      // 显示最近命令 + 分类列表
      const recentIds = getRecentCommands();
      const recentCommands = recentIds
        .map((id) => COMMANDS.find((c) => c.id === id))
        .filter((c): c is Command => c != null);

      const recentSection: Command[] = recentCommands.length > 0
        ? [{
            id: '__recent_header__',
            name: 'recently used',
            category: '__recent__',
            description: '',
          },
          ...recentCommands,
          {
            id: '__divider__',
            name: '',
            category: '__divider__',
            description: '',
          }]
        : [];

      const allCommands = [...recentSection, ...COMMANDS];
      return allCommands;
    }

    // 模糊搜索
    const scored = COMMANDS
      .map((cmd) => {
        const nameScore = fuzzyScore(q, cmd.name);
        const catScore = fuzzyScore(q, cmd.category);
        const descScore = cmd.description ? fuzzyScore(q, cmd.description) : -1;
        const best = Math.max(nameScore, catScore, descScore);
        return { cmd, score: best };
      })
      .filter(({ score }) => score >= 0)
      .sort((a, b) => b.score - a.score)
      .map(({ cmd }) => cmd);

    return scored;
  }, [search]);

  // 可选择的命令（排除 header / divider）
  const selectableCommands = useMemo(
    () => filtered.filter((c) => c.category !== '__recent__' && c.category !== '__divider__'),
    [filtered],
  );

  // 确保 selectedIndex 在合法范围
  useEffect(() => {
    if (selectedIndex >= selectableCommands.length) {
      setSelectedIndex(Math.max(0, selectableCommands.length - 1));
    }
  }, [selectableCommands.length, selectedIndex]);

  /* ---- 执行命令 ---- */
  const executeCommand = useCallback(
    (id: string) => {
      addRecentCommand(id);
      onClose();

      switch (id) {
        case 'open-folder':
          onOpenFolder();
          break;
        case 'save-file':
          onSave();
          break;
        case 'close-file':
          onCloseFile();
          break;
        case 'toggle-sidebar':
          onToggleSidebar();
          break;
        case 'toggle-agent':
          onToggleAgentPanel();
          break;
        // 其余命令暂时只关闭面板（占位）
        default:
          break;
      }
    },
    [onClose, onOpenFolder, onSave, onCloseFile, onToggleSidebar, onToggleAgentPanel],
  );

  /* ---- 键盘事件 ---- */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, selectableCommands.length - 1));
        return;
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
        return;
      }

      if (e.key === 'Enter') {
        e.preventDefault();
        const cmd = selectableCommands[selectedIndex];
        if (cmd) {
          executeCommand(cmd.id);
        }
        return;
      }
    },
    [onClose, selectableCommands, selectedIndex, executeCommand],
  );

  /* ---- 滚动可视区 ---- */
  useEffect(() => {
    if (!listRef.current) return;
    const selectedEl = listRef.current.querySelector(`[data-command-id="${selectableCommands[selectedIndex]?.id}"]`);
    if (selectedEl) {
      selectedEl.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex, selectableCommands]);

  /* ---- 点击外部关闭 ---- */
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        onClose();
      }
    },
    [onClose],
  );

  if (!isOpen) return null;

  /* ---- 按分类分组渲染 ---- */
  const renderCommandList = () => {
    // 按 category 分组
    const groups: { category: string; commands: Command[] }[] = [];
    let currentGroup: { category: string; commands: Command[] } | null = null;

    for (const cmd of filtered) {
      if (cmd.category === '__recent__') {
        // 渲染最近使用 header
        if (currentGroup) groups.push(currentGroup);
        currentGroup = null;
        groups.push({ category: '__recent__', commands: [cmd] });
        continue;
      }
      if (cmd.category === '__divider__') {
        if (currentGroup) groups.push(currentGroup);
        currentGroup = null;
        continue;
      }

      if (!currentGroup || currentGroup.category !== cmd.category) {
        if (currentGroup) groups.push(currentGroup);
        currentGroup = { category: cmd.category, commands: [cmd] };
      } else {
        currentGroup.commands.push(cmd);
      }
    }
    if (currentGroup) groups.push(currentGroup);

    // 按 CATEGORY_ORDER 排序（__recent__ 排最前）
    const sortedGroups = groups.sort((a, b) => {
      if (a.category === '__recent__') return -1;
      if (b.category === '__recent__') return 1;
      const ai = CATEGORY_ORDER.indexOf(a.category);
      const bi = CATEGORY_ORDER.indexOf(b.category);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });

    let globalSelectableIdx = 0;

    return sortedGroups.map((group) => {
      if (group.category === '__recent__') {
        return (
          <div key="__recent__" style={styles.categoryHeader}>
            <span>recently used</span>
          </div>
        );
      }

      return (
        <div key={group.category}>
          <div style={styles.categoryHeader}>
            <span>{group.category}</span>
          </div>
          {group.commands.map((cmd) => {
            const isSelected = selectableCommands[globalSelectableIdx]?.id === cmd.id;
            const idx = globalSelectableIdx;
            globalSelectableIdx++;

            return (
              <div
                key={cmd.id}
                data-command-id={cmd.id}
                style={{
                  ...styles.commandItem,
                  background: isSelected ? 'var(--bg-hover)' : 'transparent',
                }}
                onMouseEnter={() => setSelectedIndex(idx)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  executeCommand(cmd.id);
                }}
              >
                <span style={styles.commandName}>{cmd.name}</span>
                {cmd.shortcut && (
                  <span style={styles.shortcut}>{cmd.shortcut}</span>
                )}
              </div>
            );
          })}
        </div>
      );
    });
  };

  return (
    <div style={styles.backdrop} onClick={handleBackdropClick}>
      <div style={styles.palette} onKeyDown={handleKeyDown}>
        {/* 搜索框 */}
        <div style={styles.searchContainer}>
          <span style={styles.promptIcon}>{'>'}</span>
          <input
            ref={inputRef}
            style={styles.searchInput}
            type="text"
            placeholder="Type a command..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setSelectedIndex(0);
            }}
            autoFocus
          />
        </div>

        {/* 命令列表 */}
        <div ref={listRef} style={styles.list}>
          {filtered.length === 0 ? (
            <div style={styles.empty}>No matching commands</div>
          ) : (
            renderCommandList()
          )}
        </div>
      </div>
    </div>
  );
};

/* ================================================
   样式
   ================================================ */

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: 'fixed',
    inset: 0,
    zIndex: 1000,
    display: 'flex',
    justifyContent: 'center',
    paddingTop: '12vh',
    background: 'rgba(0, 0, 0, 0.3)',
  },
  palette: {
    width: '100%',
    maxWidth: 600,
    maxHeight: '70vh',
    background: 'var(--bg-primary, #ffffff)',
    borderRadius: 12,
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.18), 0 2px 8px rgba(0, 0, 0, 0.08)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    alignSelf: 'flex-start',
  },
  searchContainer: {
    display: 'flex',
    alignItems: 'center',
    padding: '0 16px',
    borderBottom: '1px solid var(--border-color, #e0e0e0)',
    flexShrink: 0,
  },
  promptIcon: {
    fontSize: 18,
    fontWeight: 600,
    color: 'var(--text-tertiary, #999)',
    marginRight: 8,
    fontFamily: 'var(--font-mono, monospace)',
    userSelect: 'none',
  },
  searchInput: {
    flex: 1,
    height: 52,
    border: 'none',
    outline: 'none',
    background: 'transparent',
    fontSize: 15,
    fontFamily: 'var(--font-sans, sans-serif)',
    color: 'var(--text-primary, #111)',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
    padding: '6px 0',
  },
  categoryHeader: {
    padding: '8px 16px 4px',
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase' as const,
    color: 'var(--text-tertiary, #999)',
    letterSpacing: '0.5px',
  },
  commandItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 40,
    padding: '0 16px',
    cursor: 'pointer',
    borderRadius: 0,
    transition: 'background 0.08s',
  },
  commandName: {
    fontSize: 13,
    color: 'var(--text-primary, #111)',
    fontWeight: 400,
  },
  shortcut: {
    fontSize: 12,
    fontFamily: 'var(--font-mono, monospace)',
    color: 'var(--text-tertiary, #999)',
    whiteSpace: 'nowrap',
  },
  empty: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: 80,
    fontSize: 13,
    color: 'var(--text-tertiary, #999)',
  },
};