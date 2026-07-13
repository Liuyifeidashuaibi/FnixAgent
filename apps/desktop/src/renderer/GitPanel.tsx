/**
 * GitPanel — 源代码管理面板
 *
 * 功能:
 *   1. Git 状态显示(分支名、staged/unstaged/untracked 计数)
 *   2. 变更文件列表(M/A/D 标记、checkbox 暂存/取消暂存、点击打开)
 *   3. Stage All / Unstage All 按钮
 *   4. 提交区域(commit message + 提交按钮 + 最近 5 条提交)
 *   5. 分支操作(创建分支、切换分支、Push/Pull)
 *   6. 浅色主题,260px 宽,与 index.css 的 CSS 变量对齐
 *
 * API: POST /api/v1/coding/git (backend IDEServer git 包装)
 */

import { useState, useEffect, useCallback, type CSSProperties } from 'react';
import { API_BASE } from './apiConfig';

/* ================================================================
   Types
   ================================================================ */

export interface GitPanelProps {
  /** 当前工作区根路径 */
  workspacePath: string | null;
  /** 点击文件时回调 */
  onOpenFile: (path: string, name: string) => void;
}

interface GitFile {
  /** 文件相对路径 */
  path: string;
  /** 暂存区状态: 'M'|'A'|'D'|'R'|'C'|' ' */
  stagedStatus: string;
  /** 工作区状态: 'M'|'D'|'?'|' ' */
  unstagedStatus: string;
  /** 是否已暂存(即在 staging area 中) */
  staged: boolean;
}

interface GitCommit {
  hash: string;
  message: string;
  author: string;
  time: string;
}

/* ================================================================
   GitPanel 主组件
   ================================================================ */

export function GitPanel({ workspacePath, onOpenFile }: GitPanelProps) {
  /* ---- 状态 ---- */
  const [branch, setBranch] = useState('');
  const [files, setFiles] = useState<GitFile[]>([]);
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [branches, setBranches] = useState<string[]>([]);
  const [commitMessage, setCommitMessage] = useState('');
  const [newBranchName, setNewBranchName] = useState('');
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [isRepo, setIsRepo] = useState<boolean | null>(null);
  const [showCreateBranch, setShowCreateBranch] = useState(false);
  const [selectedBranch, setSelectedBranch] = useState('');

  /* ---- 调用后端 Git API ---- */
  const gitApi = useCallback(
    async (args: string[]): Promise<string> => {
      const body: Record<string, unknown> = { args };
      if (workspacePath) {
        body.workspace = workspacePath;
      }
      const resp = await fetch(`${API_BASE}/api/v1/coding/git`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        throw new Error(`Git API ${resp.status}: ${await resp.text().catch(() => '')}`);
      }
      const json = await resp.json();
      if (!json.success) {
        throw new Error(json.error ?? 'Git 操作失败');
      }
      return String(json.result ?? '');
    },
    [workspacePath],
  );

  /* ---- 刷新全部状态 ---- */
  const refreshAll = useCallback(async () => {
    if (!workspacePath) return;
    setLoading(true);
    try {
      // 并行获取分支、状态、日志
      const [branchOut, statusOut, logOut, branchListOut] = await Promise.all([
        gitApi(['branch', '--show-current']).catch(() => ''),
        gitApi(['status', '--porcelain']).catch(() => ''),
        gitApi(['log', '--format=%h|%s|%an|%ar', '-5']).catch(() => ''),
        gitApi(['branch', '--list']).catch(() => ''),
      ]);

      setIsRepo(true);

      // 解析分支名
      const branchName = branchOut.trim();
      setBranch(branchName || 'HEAD');

      // 解析 status --porcelain
      const parsedFiles = parseStatus(branchName ? statusOut : '');
      setFiles(parsedFiles);

      // 解析 log
      const parsedCommits = parseLog(logOut);
      setCommits(parsedCommits);

      // 解析 branch list
      const parsedBranches = parseBranchList(branchListOut);
      setBranches(parsedBranches);
      setSelectedBranch(branchName || '');
    } catch {
      setIsRepo(false);
      setBranch('');
      setFiles([]);
      setCommits([]);
      setBranches([]);
    } finally {
      setLoading(false);
    }
  }, [workspacePath, gitApi]);

  /* ---- 工作区变化时刷新 ---- */
  useEffect(() => {
    if (workspacePath) {
      void refreshAll();
    } else {
      setIsRepo(null);
      setBranch('');
      setFiles([]);
      setCommits([]);
      setBranches([]);
    }
  }, [workspacePath, refreshAll]);

  /* ---- Stage / Unstage 单个文件 ---- */
  const handleStageFile = useCallback(
    async (file: GitFile) => {
      setActionLoading(file.path);
      try {
        if (file.staged) {
          await gitApi(['reset', 'HEAD', file.path]);
        } else {
          await gitApi(['add', file.path]);
        }
        await refreshAll();
      } catch (e) {
        console.error('Stage/Unstage failed:', e);
      } finally {
        setActionLoading(null);
      }
    },
    [gitApi, refreshAll],
  );

  /* ---- Stage All / Unstage All ---- */
  const handleStageAll = useCallback(async () => {
    setActionLoading('__stage_all__');
    try {
      await gitApi(['add', '--all']);
      await refreshAll();
    } catch (e) {
      console.error('Stage all failed:', e);
    } finally {
      setActionLoading(null);
    }
  }, [gitApi, refreshAll]);

  const handleUnstageAll = useCallback(async () => {
    setActionLoading('__unstage_all__');
    try {
      await gitApi(['reset', 'HEAD']);
      await refreshAll();
    } catch (e) {
      console.error('Unstage all failed:', e);
    } finally {
      setActionLoading(null);
    }
  }, [gitApi, refreshAll]);

  /* ---- Commit ---- */
  const handleCommit = useCallback(async () => {
    const msg = commitMessage.trim();
    if (!msg) return;
    setActionLoading('__commit__');
    try {
      await gitApi(['commit', '-m', msg]);
      setCommitMessage('');
      await refreshAll();
    } catch (e) {
      console.error('Commit failed:', e);
    } finally {
      setActionLoading(null);
    }
  }, [commitMessage, gitApi, refreshAll]);

  /* ---- Push / Pull ---- */
  const handlePush = useCallback(async () => {
    setActionLoading('__push__');
    try {
      await gitApi(['push']);
      await refreshAll();
    } catch (e) {
      console.error('Push failed:', e);
    } finally {
      setActionLoading(null);
    }
  }, [gitApi, refreshAll]);

  const handlePull = useCallback(async () => {
    setActionLoading('__pull__');
    try {
      await gitApi(['pull']);
      await refreshAll();
    } catch (e) {
      console.error('Pull failed:', e);
    } finally {
      setActionLoading(null);
    }
  }, [gitApi, refreshAll]);

  /* ---- Create Branch ---- */
  const handleCreateBranch = useCallback(async () => {
    const name = newBranchName.trim();
    if (!name) return;
    setActionLoading('__create_branch__');
    try {
      await gitApi(['branch', name]);
      setNewBranchName('');
      setShowCreateBranch(false);
      await refreshAll();
    } catch (e) {
      console.error('Create branch failed:', e);
    } finally {
      setActionLoading(null);
    }
  }, [newBranchName, gitApi, refreshAll]);

  /* ---- Switch Branch ---- */
  const handleSwitchBranch = useCallback(
    async (targetBranch: string) => {
      if (!targetBranch || targetBranch === branch) return;
      setActionLoading('__switch_branch__');
      try {
        await gitApi(['checkout', targetBranch]);
        setSelectedBranch(targetBranch);
        await refreshAll();
      } catch (e) {
        console.error('Switch branch failed:', e);
        setSelectedBranch(branch);
      } finally {
        setActionLoading(null);
      }
    },
    [branch, gitApi, refreshAll],
  );

  /* ---- 统计 ---- */
  const stagedCount = files.filter((f) => f.staged).length;
  const unstagedCount = files.filter((f) => !f.staged && f.unstagedStatus !== '?').length;
  const untrackedCount = files.filter((f) => f.unstagedStatus === '?').length;

  /* ---- 渲染 ---- */

  // 无工作区
  if (!workspacePath) {
    return (
      <div style={gs.container}>
        <div style={gs.header}>
          <span style={gs.title}>源代码管理</span>
        </div>
        <div style={gs.emptyState}>
          <p style={gs.emptyText}>尚未打开文件夹</p>
          <p style={gs.hint}>打开包含 Git 仓库的文件夹以查看变更</p>
        </div>
      </div>
    );
  }

  // 检查中
  if (isRepo === null) {
    return (
      <div style={gs.container}>
        <div style={gs.header}>
          <span style={gs.title}>源代码管理</span>
        </div>
        <div style={gs.emptyState}>
          <span style={gs.spinner} />
          <p style={gs.emptyText}>正在检查仓库…</p>
        </div>
      </div>
    );
  }

  // 非 Git 仓库
  if (isRepo === false) {
    return (
      <div style={gs.container}>
        <div style={gs.header}>
          <span style={gs.title}>源代码管理</span>
        </div>
        <div style={gs.emptyState}>
          <span style={{ fontSize: 28, color: 'var(--text-tertiary)', opacity: 0.6 }}>⎇</span>
          <p style={gs.emptyText}>暂无 Git 仓库</p>
          <p style={gs.hint}>当前文件夹未检测到 Git 仓库</p>
        </div>
      </div>
    );
  }

  // 正常 Git 仓库
  return (
    <div style={gs.container}>
      {/* 标题栏 */}
      <div style={gs.header}>
        <span style={gs.title}>源代码管理</span>
        <button style={gs.iconBtn} onClick={refreshAll} title="刷新" disabled={loading}>
          <RefreshIcon />
        </button>
      </div>

      {/* 滚动区域 */}
      <div style={gs.scrollArea}>
        {/* 分支信息 + 操作 */}
        <section style={gs.section}>
          <div style={gs.sectionTitle}>
            <span>⎇ {branch || 'HEAD'}</span>
          </div>

          {/* Push / Pull / Create Branch */}
          <div style={gs.rowBtns}>
            <button
              style={gs.actionBtn}
              onClick={handlePull}
              disabled={actionLoading === '__pull__'}
            >
              {actionLoading === '__pull__' ? <MiniSpinner /> : '↓ Pull'}
            </button>
            <button
              style={gs.actionBtn}
              onClick={handlePush}
              disabled={actionLoading === '__push__'}
            >
              {actionLoading === '__push__' ? <MiniSpinner /> : '↑ Push'}
            </button>
          </div>

          {/* 切换分支下拉 */}
          {branches.length > 0 && (
            <div style={gs.rowBtns}>
              <select
                style={gs.select}
                value={selectedBranch}
                onChange={(e) => {
                  const v = e.target.value;
                  setSelectedBranch(v);
                  if (v !== branch) {
                    void handleSwitchBranch(v);
                  }
                }}
                disabled={actionLoading === '__switch_branch__'}
              >
                {branches.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* 创建分支 */}
          {showCreateBranch ? (
            <div style={gs.rowBtns}>
              <input
                style={gs.smallInput}
                type="text"
                placeholder="新分支名…"
                value={newBranchName}
                onChange={(e) => setNewBranchName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleCreateBranch();
                  if (e.key === 'Escape') {
                    setShowCreateBranch(false);
                    setNewBranchName('');
                  }
                }}
                autoFocus
              />
              <button
                style={gs.actionBtn}
                onClick={handleCreateBranch}
                disabled={!newBranchName.trim() || actionLoading === '__create_branch__'}
              >
                {actionLoading === '__create_branch__' ? <MiniSpinner /> : '创建'}
              </button>
              <button
                style={gs.actionBtn}
                onClick={() => {
                  setShowCreateBranch(false);
                  setNewBranchName('');
                }}
              >
                取消
              </button>
            </div>
          ) : (
            <div style={{ padding: '0 12px 4px' }}>
              <button
                style={gs.linkBtn}
                onClick={() => setShowCreateBranch(true)}
              >
                + 新建分支
              </button>
            </div>
          )}
        </section>

        {/* 变更统计 */}
        <section style={gs.section}>
          <div style={gs.sectionTitle}>
            <span>变更</span>
            <span style={gs.countBadge}>{files.length}</span>
          </div>

          {files.length === 0 ? (
            <div style={gs.emptyHint}>工作区干净,无变更</div>
          ) : (
            <>
              {/* Stage All / Unstage All */}
              <div style={gs.rowBtns}>
                <button
                  style={gs.actionBtn}
                  onClick={handleStageAll}
                  disabled={actionLoading === '__stage_all__'}
                >
                  {actionLoading === '__stage_all__' ? <MiniSpinner /> : '+ Stage All'}
                </button>
                <button
                  style={gs.actionBtn}
                  onClick={handleUnstageAll}
                  disabled={stagedCount === 0 || actionLoading === '__unstage_all__'}
                >
                  {actionLoading === '__unstage_all__' ? <MiniSpinner /> : '− Unstage All'}
                </button>
              </div>

              {/* 暂存区 */}
              {stagedCount > 0 && (
                <div style={{ marginBottom: 4 }}>
                  <div style={gs.subTitle}>
                    <span style={{ color: 'var(--success)' }}>●</span> 暂存的更改 ({stagedCount})
                  </div>
                  {files
                    .filter((f) => f.staged)
                    .map((f) => (
                      <FileRow
                        key={'staged-' + f.path}
                        file={f}
                        loading={actionLoading === f.path}
                        onStage={handleStageFile}
                        onOpen={onOpenFile}
                        workspacePath={workspacePath}
                      />
                    ))}
                </div>
              )}

              {/* 未暂存区 */}
              {unstagedCount > 0 && (
                <div style={{ marginBottom: 4 }}>
                  <div style={gs.subTitle}>
                    <span style={{ color: 'var(--warning)' }}>●</span> 更改 ({unstagedCount})
                  </div>
                  {files
                    .filter((f) => !f.staged && f.unstagedStatus !== '?')
                    .map((f) => (
                      <FileRow
                        key={'unstaged-' + f.path}
                        file={f}
                        loading={actionLoading === f.path}
                        onStage={handleStageFile}
                        onOpen={onOpenFile}
                        workspacePath={workspacePath}
                      />
                    ))}
                </div>
              )}

              {/* 未跟踪 */}
              {untrackedCount > 0 && (
                <div>
                  <div style={gs.subTitle}>
                    <span style={{ color: 'var(--text-tertiary)' }}>●</span> 未跟踪的文件 ({untrackedCount})
                  </div>
                  {files
                    .filter((f) => f.unstagedStatus === '?')
                    .map((f) => (
                      <FileRow
                        key={'untracked-' + f.path}
                        file={f}
                        loading={actionLoading === f.path}
                        onStage={handleStageFile}
                        onOpen={onOpenFile}
                        workspacePath={workspacePath}
                      />
                    ))}
                </div>
              )}
            </>
          )}
        </section>

        {/* 提交区域 */}
        {stagedCount > 0 && (
          <section style={gs.section}>
            <div style={gs.sectionTitle}>
              <span>提交</span>
            </div>
            <div style={{ padding: '0 12px 6px' }}>
              <textarea
                style={gs.textarea}
                placeholder="提交信息…"
                value={commitMessage}
                onChange={(e) => setCommitMessage(e.target.value)}
                rows={3}
                onKeyDown={(e) => {
                  if (e.ctrlKey && e.key === 'Enter') {
                    e.preventDefault();
                    void handleCommit();
                  }
                }}
              />
              <button
                style={{
                  ...gs.commitBtn,
                  opacity: commitMessage.trim() && actionLoading !== '__commit__' ? 1 : 0.5,
                  cursor:
                    commitMessage.trim() && actionLoading !== '__commit__'
                      ? 'pointer'
                      : 'not-allowed',
                }}
                onClick={handleCommit}
                disabled={!commitMessage.trim() || actionLoading === '__commit__'}
              >
                {actionLoading === '__commit__' ? <MiniSpinner /> : '✓ 提交'}
              </button>
            </div>
          </section>
        )}

        {/* 最近提交 */}
        {commits.length > 0 && (
          <section style={gs.section}>
            <div style={gs.sectionTitle}>
              <span>最近提交</span>
              <span style={gs.countBadge}>{commits.length}</span>
            </div>
            {commits.map((c) => (
              <div key={c.hash} style={gs.commitItem}>
                <div style={gs.commitHead}>
                  <span style={gs.commitHash}>{c.hash}</span>
                  <span style={gs.commitTime}>{c.time}</span>
                </div>
                <div style={gs.commitMsg} title={c.message}>
                  {c.message}
                </div>
                <div style={gs.commitAuthor}>{c.author}</div>
              </div>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}

/* ================================================================
   FileRow — 单个文件行
   ================================================================ */

function FileRow({
  file,
  loading,
  onStage,
  onOpen,
  workspacePath,
}: {
  file: GitFile;
  loading: boolean;
  onStage: (f: GitFile) => void;
  onOpen: (path: string, name: string) => void;
  workspacePath: string;
}) {
  const statusLabel = file.unstagedStatus === '?' ? 'U' : file.stagedStatus !== ' ' ? file.stagedStatus : file.unstagedStatus;
  const statusColor =
    statusLabel === 'A' ? 'var(--success)'
    : statusLabel === 'D' ? 'var(--error)'
    : statusLabel === 'M' ? 'var(--warning)'
    : statusLabel === 'U' ? 'var(--text-tertiary)'
    : 'var(--text-secondary)';

  const fullPath = workspacePath.replace(/\\/g, '/') + '/' + file.path;
  const name = file.path.split(/[\\/]/).pop() ?? file.path;

  return (
    <div
      style={gs.fileRow}
      role="button"
      tabIndex={0}
      onClick={() => onOpen(fullPath, name)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(fullPath, name);
        }
      }}
    >
      <button
        style={{
          ...gs.stageCheckbox,
          color: file.staged ? 'var(--success)' : 'var(--text-tertiary)',
        }}
        onClick={(e) => {
          e.stopPropagation();
          onStage(file);
        }}
        disabled={loading}
        title={file.staged ? '取消暂存' : '暂存'}
      >
        {loading ? <MiniSpinner /> : file.staged ? '✓' : '○'}
      </button>
      <span style={{ ...gs.statusBadge, color: statusColor }}>{statusLabel}</span>
      <span style={gs.fileName} title={file.path}>
        {name}
      </span>
      <span style={gs.filePath}>{file.path}</span>
    </div>
  );
}

/* ================================================================
   辅助组件
   ================================================================ */

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
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ animation: 'gitpanel-spin 0.8s linear infinite' }}>
      <circle cx="12" cy="12" r="10" stroke="#9ca3af" strokeWidth="3" opacity="0.25" />
      <path d="M4 12a8 8 0 0 1 8-8" stroke="#0066b8" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

/* ================================================================
   解析函数
   ================================================================ */

/** 解析 git status --porcelain 输出 */
function parseStatus(output: string): GitFile[] {
  if (!output.trim()) return [];
  const lines = output.split('\n').filter(Boolean);
  const result: GitFile[] = [];
  for (const line of lines) {
    if (line.length < 3) continue;
    const stagedStatus = line[0];
    const unstagedStatus = line[1];
    const rawPath = line.slice(3).trim();
    // 处理重命名 "R  old -> new"
    let path = rawPath;
    if (stagedStatus === 'R' || unstagedStatus === 'R') {
      const arrowIdx = rawPath.indexOf(' -> ');
      if (arrowIdx !== -1) {
        path = rawPath.slice(arrowIdx + 4);
      }
    }
    const staged = stagedStatus !== ' ' && stagedStatus !== '?';
    result.push({ path, stagedStatus, unstagedStatus, staged });
  }
  return result;
}

/** 解析 git log --format="%h|%s|%an|%ar" -5 输出 */
function parseLog(output: string): GitCommit[] {
  if (!output.trim()) return [];
  const lines = output.split('\n').filter(Boolean);
  return lines.map((line) => {
    const parts = line.split('|');
    return {
      hash: parts[0]?.trim() ?? '',
      message: parts[1]?.trim() ?? '',
      author: parts[2]?.trim() ?? '',
      time: parts[3]?.trim() ?? '',
    };
  });
}

/** 解析 git branch --list 输出 */
function parseBranchList(output: string): string[] {
  if (!output.trim()) return [];
  return output
    .split('\n')
    .filter(Boolean)
    .map((line) => line.replace(/^\*?\s+/, '').trim())
    .filter(Boolean);
}

/* ================================================================
   样式
   ================================================================ */

const gs: Record<string, CSSProperties> = {
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
  title: {
    fontSize: 11,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
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
    marginBottom: 4,
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
  subTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    padding: '4px 12px 2px',
    fontSize: 10,
    fontWeight: 600,
    color: 'var(--text-tertiary)',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  countBadge: {
    fontSize: 10,
    color: 'var(--text-tertiary)',
    background: 'var(--bg-tertiary)',
    padding: '0 6px',
    borderRadius: 10,
    fontWeight: 600,
  },
  rowBtns: {
    display: 'flex',
    gap: 4,
    padding: '2px 12px 4px',
  },
  actionBtn: {
    flex: 1,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: 24,
    padding: '0 8px',
    background: 'var(--bg-primary)',
    border: '1px solid var(--border-color)',
    borderRadius: 4,
    color: 'var(--text-secondary)',
    fontSize: 11,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'background 0.12s',
    fontFamily: 'var(--font-sans)',
  },
  linkBtn: {
    background: 'transparent',
    border: 'none',
    color: 'var(--accent)',
    fontSize: 11,
    cursor: 'pointer',
    padding: 0,
    fontFamily: 'var(--font-sans)',
    transition: 'opacity 0.12s',
  },
  select: {
    flex: 1,
    height: 24,
    padding: '0 6px',
    border: '1px solid var(--border-color)',
    borderRadius: 4,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 11,
    fontFamily: 'var(--font-sans)',
    cursor: 'pointer',
    outline: 'none',
  },
  smallInput: {
    flex: 1,
    height: 24,
    padding: '0 8px',
    border: '1px solid var(--border-color)',
    borderRadius: 4,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 11,
    fontFamily: 'var(--font-sans)',
    outline: 'none',
  },
  textarea: {
    width: '100%',
    padding: '6px 8px',
    border: '1px solid var(--border-color)',
    borderRadius: 4,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 12,
    fontFamily: 'var(--font-sans)',
    resize: 'vertical',
    outline: 'none',
    boxSizing: 'border-box',
    marginBottom: 4,
  },
  commitBtn: {
    width: '100%',
    height: 28,
    padding: '0 12px',
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    fontSize: 12,
    fontWeight: 600,
    transition: 'opacity 0.12s',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: 'var(--font-sans)',
  },
  fileRow: {
    display: 'flex',
    alignItems: 'center',
    height: 24,
    padding: '0 12px',
    gap: 5,
    cursor: 'pointer',
    fontSize: 12,
    transition: 'background 0.08s',
  },
  stageCheckbox: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 16,
    height: 16,
    padding: 0,
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    fontSize: 12,
    flexShrink: 0,
    fontFamily: 'var(--font-sans)',
  },
  statusBadge: {
    fontSize: 9,
    fontWeight: 700,
    width: 14,
    textAlign: 'center',
    flexShrink: 0,
    fontFamily: 'var(--font-mono)',
  },
  fileName: {
    flex: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    color: 'var(--text-primary)',
    fontSize: 12,
    minWidth: 0,
  },
  filePath: {
    fontSize: 10,
    color: 'var(--text-tertiary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    maxWidth: 80,
    flexShrink: 1,
  },
  commitItem: {
    padding: '6px 12px',
    borderBottom: '1px solid var(--border-color)',
    fontSize: 11,
  },
  commitHead: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 2,
  },
  commitHash: {
    fontFamily: 'var(--font-mono)',
    fontSize: 10,
    color: 'var(--accent)',
    fontWeight: 600,
  },
  commitTime: {
    fontSize: 10,
    color: 'var(--text-tertiary)',
  },
  commitMsg: {
    color: 'var(--text-primary)',
    fontSize: 12,
    fontWeight: 500,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    marginBottom: 1,
  },
  commitAuthor: {
    fontSize: 10,
    color: 'var(--text-tertiary)',
  },
  emptyState: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    textAlign: 'center',
    gap: 8,
  },
  emptyText: {
    color: 'var(--text-secondary)',
    fontSize: 13,
    margin: 0,
  },
  hint: {
    color: 'var(--text-tertiary)',
    fontSize: 11,
    margin: 0,
  },
  emptyHint: {
    padding: '8px 12px',
    fontSize: 12,
    color: 'var(--text-tertiary)',
    textAlign: 'center',
  },
  spinner: {
    width: 18,
    height: 18,
    border: '2px solid var(--border-color)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    display: 'inline-block',
    animation: 'gitpanel-spin 0.8s linear infinite',
  },
};

/* ---- spin keyframes ---- */
const __GITPANEL_SPIN_ID = '__fnixagent_gitpanel_spin__';
if (typeof document !== 'undefined' && !document.getElementById(__GITPANEL_SPIN_ID)) {
  const el = document.createElement('style');
  el.id = __GITPANEL_SPIN_ID;
  el.textContent = '@keyframes gitpanel-spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}';
  document.head.appendChild(el);
}