/**
 * OfficeAgent Studio — 代码变更汇总弹窗
 *
 * 独立 Dialog,由 TopBar 的 "Review Changes" 按钮触发。
 * 紧凑模式:只显示文件列表 + 行数 + 整体 Accept/Reject。
 */
import { useMemo } from 'react';
import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@officeagent/ui';
import { useStudio } from '../../stores/studio-store';

interface ChangesSummaryProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** 变更汇总弹窗 */
export function ChangesSummary({ open, onOpenChange }: ChangesSummaryProps) {
  const { state, dispatch } = useStudio();
  const { pendingDiff } = state;

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

  const acceptAll = () => {
    pendingDiff?.forEach((c) => {
      if (c.status === 'pending') {
        dispatch({ type: 'ACCEPT_FILE_CHANGE', filePath: c.filePath });
      }
    });
  };

  const rejectAll = () => {
    pendingDiff?.forEach((c) => {
      if (c.status === 'pending') {
        dispatch({ type: 'REJECT_FILE_CHANGE', filePath: c.filePath });
      }
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>代码变更汇总</DialogTitle>
          <DialogDescription>
            {stats.files > 0
              ? `${stats.files} 个文件 · +${stats.added} / -${stats.removed}`
              : '当前无待确认变更'}
          </DialogDescription>
        </DialogHeader>

        {/* 文件列表(紧凑) */}
        <div className="max-h-[50vh] space-y-1 overflow-auto">
          {pendingDiff && pendingDiff.length > 0 ? (
            pendingDiff.map((c) => {
              const isNew = !c.oldContent && !!c.newContent;
              const isDelete = !!c.oldContent && !c.newContent;
              return (
                <div
                  key={c.filePath}
                  className="flex items-center justify-between rounded-md border border-border px-3 py-2"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate font-mono text-xs">
                      {c.filePath}
                    </span>
                    <Badge
                      variant={
                        c.status === 'accepted'
                          ? 'success'
                          : c.status === 'rejected'
                            ? 'destructive'
                            : isNew
                              ? 'success'
                              : isDelete
                                ? 'destructive'
                                : 'warning'
                      }
                    >
                      {c.status === 'accepted'
                        ? '已接受'
                        : c.status === 'rejected'
                          ? '已拒绝'
                          : isNew
                            ? 'Added'
                            : isDelete
                              ? 'Deleted'
                              : 'Modified'}
                    </Badge>
                  </div>
                  <span className="shrink-0 font-mono text-xs text-muted-foreground">
                    <span className="text-[hsl(var(--success))]">+{c.addedLines}</span>
                    {' '}
                    <span className="text-[hsl(var(--destructive))]">-{c.removedLines}</span>
                  </span>
                </div>
              );
            })
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">
              无待确认变更
            </p>
          )}
        </div>

        <DialogFooter>
          {hasPending && (
            <>
              <Button variant="outline" onClick={rejectAll}>
                Reject All
              </Button>
              <Button onClick={acceptAll}>Accept All</Button>
            </>
          )}
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
