import { useState } from 'react';

interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileNode[];
}

interface FileTreeProps {
  onFileSelect?: (path: string) => void;
}

/**
 * 左侧文件树
 * Phase 1.4: 基础展示 + 点击选中
 * 后续: 本地目录扫描(IPC)、拖拽导入、右键菜单
 */
export function FileTree({ onFileSelect }: FileTreeProps) {
  // 模拟文件树(Phase 1.5 将通过 IPC 扫描真实目录)
  const [files] = useState<FileNode[]>([
    {
      name: 'documents',
      path: '/documents',
      type: 'directory',
      children: [
        { name: 'paper.md', path: '/documents/paper.md', type: 'file' },
        { name: 'notes.txt', path: '/documents/notes.txt', type: 'file' },
        {
          name: 'reports',
          path: '/documents/reports',
          type: 'directory',
          children: [
            { name: 'weekly.pdf', path: '/documents/reports/weekly.pdf', type: 'file' },
          ],
        },
      ],
    },
    { name: 'config.yaml', path: '/config.yaml', type: 'file' },
  ]);

  return (
    <div className="h-full overflow-auto bg-secondary/30 p-2">
      <div className="mb-2 flex items-center justify-between px-2">
        <span className="text-xs font-medium text-muted-foreground uppercase">文件</span>
        <button className="text-xs text-muted-foreground hover:text-foreground">+ 新建</button>
      </div>
      <FileTreeNodes nodes={files} onFileSelect={onFileSelect} />
    </div>
  );
}

function FileTreeNodes({
  nodes,
  onFileSelect,
  depth = 0,
}: {
  nodes: FileNode[];
  onFileSelect?: (path: string) => void;
  depth?: number;
}) {
  return (
    <ul className="space-y-0.5">
      {nodes.map((node) => (
        <FileTreeNode key={node.path} node={node} onFileSelect={onFileSelect} depth={depth} />
      ))}
    </ul>
  );
}

function FileTreeNode({
  node,
  onFileSelect,
  depth,
}: {
  node: FileNode;
  onFileSelect?: (path: string) => void;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(depth < 1);

  if (node.type === 'directory') {
    return (
      <li>
        <button
          className="flex w-full items-center gap-1 rounded px-2 py-1 text-sm hover:bg-accent"
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
          onClick={() => setExpanded(!expanded)}
        >
          <span className="text-xs">{expanded ? '▼' : '▶'}</span>
          <span>{expanded ? '📁' : '📂'}</span>
          <span className="truncate">{node.name}</span>
        </button>
        {expanded && node.children && (
          <FileTreeNodes nodes={node.children} onFileSelect={onFileSelect} depth={depth + 1} />
        )}
      </li>
    );
  }

  return (
    <li>
      <button
        className="flex w-full items-center gap-1 rounded px-2 py-1 text-sm hover:bg-accent"
        style={{ paddingLeft: `${depth * 12 + 24}px` }}
        onClick={() => onFileSelect?.(node.path)}
      >
        <span>📄</span>
        <span className="truncate">{node.name}</span>
      </button>
    </li>
  );
}
