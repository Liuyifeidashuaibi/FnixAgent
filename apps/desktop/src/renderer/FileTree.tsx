/**
 * 文件树组件(Phase 3.1 左侧栏)
 *
 * 功能:
 *   - 打开文件夹(系统对话框)
 *   - 递归显示目录树(可折叠/展开)
 *   - 点击文件 → 通知父组件打开
 *   - 显示当前工作区路径
 */
import { useState } from 'react';
import type { FileTreeNode } from './global';

interface FileTreeProps {
  /** 当前工作区根路径(空字符串表示未打开) */
  workspacePath: string;
  /** 文件树数据 */
  tree: FileTreeNode[];
  /** 当前激活文件路径(高亮) */
  activeFile: string | null;
  /** 打开文件回调 */
  onOpenFile: (node: FileTreeNode) => void;
  /** 点击「打开文件夹」按钮 */
  onOpenFolder: () => void;
  /** 刷新文件树 */
  onRefresh: () => void;
}

export function FileTree({
  workspacePath,
  tree,
  activeFile,
  onOpenFile,
  onOpenFolder,
  onRefresh,
}: FileTreeProps) {
  return (
    <div style={styles.container}>
      <div style={styles.toolbar}>
        <span style={styles.title}>资源管理器</span>
        <div style={styles.toolbarBtns}>
          {workspacePath && (
            <button style={styles.iconBtn} onClick={onRefresh} title="刷新">
              ↻
            </button>
          )}
          <button style={styles.iconBtn} onClick={onOpenFolder} title="打开文件夹">
            📁
          </button>
        </div>
      </div>

      {workspacePath ? (
        <>
          <div style={styles.workspaceInfo} title={workspacePath}>
            <span style={styles.workspaceIcon}>📂</span>
            <span style={styles.workspacePath}>{shortenPath(workspacePath)}</span>
          </div>
          <div style={styles.treeContainer}>
            {tree.length === 0 ? (
              <div style={styles.empty}>空文件夹</div>
            ) : (
              tree.map((node) => (
                <TreeItem
                  key={node.path}
                  node={node}
                  depth={0}
                  activeFile={activeFile}
                  onOpenFile={onOpenFile}
                />
              ))
            )}
          </div>
        </>
      ) : (
        <div style={styles.placeholder}>
          <div style={styles.placeholderIcon}>📁</div>
          <p style={styles.placeholderText}>尚未打开文件夹</p>
          <button style={styles.openBtn} onClick={onOpenFolder}>
            打开文件夹
          </button>
        </div>
      )}
    </div>
  );
}

/** 递归渲染树节点 */
function TreeItem({
  node,
  depth,
  activeFile,
  onOpenFile,
}: {
  node: FileTreeNode;
  depth: number;
  activeFile: string | null;
  onOpenFile: (node: FileTreeNode) => void;
}) {
  const [expanded, setExpanded] = useState(depth < 1);

  const isActive = activeFile === node.path;
  const indent = depth * 12 + 8;

  if (node.type === 'directory') {
    return (
      <div>
        <div
          style={styles.treeItem}
          onClick={() => setExpanded((v) => !v)}
          role="button"
          tabIndex={0}
        >
          <span style={{ ...styles.indent, width: indent }} />
          <span style={styles.chevron}>{expanded ? '▾' : '▸'}</span>
          <span style={styles.dirIcon}>{expanded ? '📂' : '📁'}</span>
          <span style={styles.dirName}>{node.name}</span>
        </div>
        {expanded && node.children && (
          <div>
            {node.children.map((child) => (
              <TreeItem
                key={child.path}
                node={child}
                depth={depth + 1}
                activeFile={activeFile}
                onOpenFile={onOpenFile}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      style={{
        ...styles.treeItem,
        background: isActive ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
      }}
      onClick={() => onOpenFile(node)}
      role="button"
      tabIndex={0}
    >
      <span style={{ ...styles.indent, width: indent }} />
      <span style={styles.chevronPlaceholder} />
      <span style={styles.fileIcon}>{getFileIcon(node.name)}</span>
      <span style={{ ...styles.fileName, color: isActive ? '#93c5fd' : '#cbd5e1' }}>
        {node.name}
      </span>
    </div>
  );
}

/** 缩短路径显示(只保留最后 2 级) */
function shortenPath(p: string): string {
  const parts = p.replace(/\\/g, '/').split('/').filter(Boolean);
  if (parts.length <= 2) return p;
  return '.../' + parts.slice(-2).join('/');
}

/** 根据扩展名返回文件图标 */
function getFileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase();
  if (!ext) return '📄';
  if (['ts', 'tsx'].includes(ext)) return '🔷';
  if (['js', 'jsx', 'mjs'].includes(ext)) return '🟨';
  if (['py'].includes(ext)) return '🐍';
  if (['json'].includes(ext)) return '📋';
  if (['md'].includes(ext)) return '📝';
  if (['html', 'htm'].includes(ext)) return '🌐';
  if (['css', 'scss', 'less'].includes(ext)) return '🎨';
  if (['yml', 'yaml'].includes(ext)) return '⚙️';
  if (['png', 'jpg', 'jpeg', 'gif', 'svg'].includes(ext)) return '🖼️';
  return '📄';
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: 'rgba(15, 23, 42, 0.4)',
    borderRight: '1px solid rgba(148, 163, 184, 0.1)',
    color: '#e2e8f0',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
    fontSize: 13,
    userSelect: 'none' as const,
  },
  toolbar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 12px',
    borderBottom: '1px solid rgba(148, 163, 184, 0.1)',
  },
  title: {
    fontSize: 11,
    fontWeight: 600,
    color: '#94a3b8',
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
  },
  toolbarBtns: {
    display: 'flex',
    gap: 4,
  },
  iconBtn: {
    background: 'transparent',
    border: 'none',
    color: '#94a3b8',
    cursor: 'pointer',
    fontSize: 14,
    padding: '2px 4px',
    borderRadius: 4,
  },
  workspaceInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 12px',
    fontSize: 12,
    color: '#64748b',
    overflow: 'hidden',
    whiteSpace: 'nowrap' as const,
    textOverflow: 'ellipsis',
  },
  workspaceIcon: { fontSize: 12 },
  workspacePath: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  treeContainer: {
    flex: 1,
    overflow: 'auto',
    padding: '4px 0',
  },
  treeItem: {
    display: 'flex',
    alignItems: 'center',
    padding: '3px 8px',
    cursor: 'pointer',
    gap: 4,
    whiteSpace: 'nowrap' as const,
  },
  indent: { display: 'inline-block' },
  chevron: {
    fontSize: 10,
    color: '#64748b',
    width: 12,
    textAlign: 'center' as const,
  },
  chevronPlaceholder: { width: 12 },
  dirIcon: { fontSize: 13 },
  dirName: { color: '#e2e8f0', fontWeight: 500 },
  fileIcon: { fontSize: 13 },
  fileName: { overflow: 'hidden', textOverflow: 'ellipsis' },
  empty: {
    padding: 20,
    textAlign: 'center' as const,
    color: '#64748b',
    fontSize: 12,
  },
  placeholder: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
    textAlign: 'center' as const,
  },
  placeholderIcon: { fontSize: 40, marginBottom: 12, opacity: 0.5 },
  placeholderText: { color: '#64748b', fontSize: 13, margin: '0 0 16px' },
  openBtn: {
    padding: '8px 16px',
    background: 'linear-gradient(135deg, #3b82f6, #6366f1)',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
  },
};
