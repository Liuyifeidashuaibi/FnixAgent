/**
 * fnixagent Studio — 代码差异视图
 *
 * 对标 Cursor/Continue 的 diff 视图:
 *   - 顶部标题 + 文件数 + 行数统计(+X / -Y)
 *   - 每个 FileChange 一张卡片(路径 + 状态徽标 + Accept/Reject)
 *   - 行级 diff(LCS 算法):旧行红底,新行绿底
 *   - 卡片可折叠/展开
 *   - 底部 Accept All / Reject All
 *   - 空状态
 */
import { useMemo, useState } from 'react';
import { Badge, Button } from '@fnixagent/ui';
import { useStudio } from '../../stores/studio-store';
import type { FileChange } from '../../stores/types';
import { ChevronIcon } from './icons';

/** diff 行类型 */
interface DiffLine {
  type: 'context' | 'added' | 'removed';
  oldLineNo?: number;
  newLineNo?: number;
  content: string;
}

/**
 * 基于 LCS(最长公共子序列)的行级 diff 算法。
 * 时间/空间 O(m*n),适合中小型文件。
 */
function computeLineDiff(
  oldText: string,
  newText: string,
): DiffLine[] {
  const oldLines = oldText.split('\n');
  const newLines = newText.split('\n');
  const m = oldLines.length;
  const n = newLines.length;

  // dp[i][j] = oldLines[i..] 与 newLines[j..] 的 LCS 长度
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array<number>(n + 1).fill(0),
  );
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (oldLines[i] === newLines[j]) {
        dp[i][j] = dp[i + 1][j + 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  const result: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (oldLines[i] === newLines[j]) {
      result.push({
        type: 'context',
        oldLineNo: i + 1,
        newLineNo: j + 1,
        content: oldLines[i],
      });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      result.push({ type: 'removed', oldLineNo: i + 1, content: oldLines[i] });
      i++;
    } else {
      result.push({ type: 'added', newLineNo: j + 1, content: newLines[j] });
      j++;
    }
  }
  while (i < m) {
    result.push({ type: 'removed', oldLineNo: i + 1, content: oldLines[i] });
    i++;
  }
  while (j < n) {
    result.push({ type: 'added', newLineNo: j + 1, content: newLines[j] });
    j++;
  }
  return result;
}

/** 文件状态徽标 */
function StatusBadge({ change }: { change: FileChange }) {
  const isNew = !change.oldContent && !!change.newContent;
  const isDelete = !!change.oldContent && !change.newContent;
  const label = isNew ? 'Added' : isDelete ? 'Deleted' : 'Modified';
  const variant = isNew ? 'success' : isDelete ? 'destructive' : 'warning';
  return <Badge variant={variant}>{label}</Badge>;
}

/** 单个文件 diff 卡片 */
function FileChangeCard({ change }: { change: FileChange }) {
  const { dispatch } = useStudio();
  const [expanded, setExpanded] = useState(true);

  const diffLines = useMemo(
    () => computeLineDiff(change.oldContent, change.newContent),
    [change.oldContent, change.newContent],
  );

  const isPending = change.status === 'pending';

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-background shadow-sm">
      {/* 卡片头 */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-muted-foreground transition-transform"
            style={{ transform: expanded ? 'rotate(0deg)' : 'rotate(-90deg)' }}
          >
            <ChevronIcon width={14} height={14} />
          </button>
          <span className="truncate font-mono text-xs text-foreground">
            {change.filePath}
          </span>
          <StatusBadge change={change} />
          {change.status !== 'pending' && (
            <Badge variant={change.status === 'accepted' ? 'success' : 'destructive'}>
              {change.status === 'accepted' ? '已接受' : '已拒绝'}
            </Badge>
          )}
        </div>
        {isPending && (
          <div className="flex shrink-0 items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              className="h-6 px-2 text-xs"
              onClick={() =>
                dispatch({ type: 'REJECT_FILE_CHANGE', filePath: change.filePath })
              }
            >
              Reject
            </Button>
            <Button
              size="sm"
              className="h-6 px-2 text-xs"
              onClick={() =>
                dispatch({ type: 'ACCEPT_FILE_CHANGE', filePath: change.filePath })
              }
            >
              Accept
            </Button>
          </div>
        )}
      </div>

      {/* 卡片体:行级 diff */}
      {expanded && (
        <div className="overflow-x-auto bg-[hsl(var(--code-bg))]">
          <table className="w-full border-collapse font-mono text-xs">
            <tbody>
              {diffLines.map((line, idx) => {
                const bg =
                  line.type === 'added'
                    ? 'bg-[hsl(var(--success))]/10'
                    : line.type === 'removed'
                      ? 'bg-[hsl(var(--destructive))]/10'
                      : '';
                const prefix =
                  line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' ';
                const color =
                  line.type === 'added'
                    ? 'text-[hsl(var(--success))]'
                    : line.type === 'removed'
                      ? 'text-[hsl(var(--destructive))]'
                      : 'text-foreground';
                return (
                  <tr key={idx} className={bg}>
                    <td className="w-10 select-none px-2 text-right text-muted-foreground/50">
                      {line.oldLineNo ?? ''}
                    </td>
                    <td className="w-10 select-none px-2 text-right text-muted-foreground/50">
                      {line.newLineNo ?? ''}
                    </td>
                    <td className={`select-none px-1 ${color}`}>{prefix}</td>
                    <td className={`whitespace-pre-wrap break-all px-2 ${color}`}>
                      {line.content || ' '}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** Diff 视图主组件 */
export function DiffView() {
  const { state, dispatch } = useStudio();
  const { pendingDiff } = state;

  // 统计
  const stats = useMemo(() => {
    if (!pendingDiff) return { files: 0, added: 0, removed: 0 };
    return pendingDiff.reduce(
      (acc, c) => ({
        files: acc.files + 1,
        added: acc.added + c.addedLines,
        removed: acc.removed + c.removedLines,
      }),
      { files: 0, added: 0, removed: 0 },
    );
  }, [pendingDiff]);

  const hasPending = pendingDiff?.some((c) => c.status === 'pending');

  if (!pendingDiff || pendingDiff.length === 0) {
    return (
      <div className="flex h-full flex-col bg-background">
        <div className="border-b border-border px-4 py-2.5">
          <h2 className="text-sm font-semibold">代码变更</h2>
        </div>
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <p className="text-sm">无待确认变更</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-background">
      {/* 顶部标题 + 统计 */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">代码变更</h2>
          <span className="text-xs text-muted-foreground">
            {stats.files} 个文件
          </span>
          <span className="text-xs text-[hsl(var(--success))]">+{stats.added}</span>
          <span className="text-xs text-[hsl(var(--destructive))]">
            -{stats.removed}
          </span>
        </div>
        {hasPending && (
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="sm"
              className="h-6 text-xs"
              onClick={() => {
                pendingDiff.forEach((c) => {
                  if (c.status === 'pending') {
                    dispatch({ type: 'REJECT_FILE_CHANGE', filePath: c.filePath });
                  }
                });
              }}
            >
              Reject All
            </Button>
            <Button
              size="sm"
              className="h-6 text-xs"
              onClick={() => {
                pendingDiff.forEach((c) => {
                  if (c.status === 'pending') {
                    dispatch({ type: 'ACCEPT_FILE_CHANGE', filePath: c.filePath });
                  }
                });
              }}
            >
              Accept All
            </Button>
          </div>
        )}
      </div>

      {/* 文件列表 */}
      <div className="flex-1 space-y-2 overflow-auto p-3">
        {pendingDiff.map((change) => (
          <FileChangeCard key={change.filePath} change={change} />
        ))}
      </div>
    </div>
  );
}
