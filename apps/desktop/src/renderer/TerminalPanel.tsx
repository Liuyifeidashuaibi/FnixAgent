/**
 * AgentOS 终端面板
 * 嵌入在 AgentPanel 中，轻量终端模拟器，快捷命令执行
 */
import { useState, useRef, type FormEvent } from 'react';

interface HistoryEntry {
  cmd: string;
  output: string;
  timestamp: number;
}

const API_BASE = 'http://localhost:8000/api/v1/agentos';

/** 根据命令前缀判断应调用的端点 */
function resolveEndpoint(cmd: string): { method: string; url: string; body?: unknown } {
  const trimmed = cmd.trim().toLowerCase();

  if (trimmed === 'ps') {
    return { method: 'GET', url: `${API_BASE}/ps` };
  }
  if (trimmed === 'stats') {
    return { method: 'GET', url: `${API_BASE}/stats` };
  }
  if (trimmed === 'help') {
    return { method: 'GET', url: `${API_BASE}/help` };
  }
  if (trimmed === 'boot' || trimmed === '启动') {
    return { method: 'POST', url: `${API_BASE}/boot` };
  }
  // 默认：自然语言命令
  return {
    method: 'POST',
    url: `${API_BASE}/natural`,
    body: { text: trimmed },
  };
}

export function TerminalPanel() {
  const [command, setCommand] = useState('');
  const [output, setOutput] = useState('');
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const outputRef = useRef<HTMLDivElement>(null);

  async function handleExecute(e: FormEvent) {
    e.preventDefault();
    const cmd = command.trim();
    if (!cmd || loading) return;

    setLoading(true);
    setOutput('');

    const ep = resolveEndpoint(cmd);
    try {
      let resp: Response;
      if (ep.method === 'GET') {
        resp = await fetch(ep.url);
      } else {
        resp = await fetch(ep.url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(ep.body),
        });
      }

      const text = await resp.text();
      let formatted: string;
      try {
        const json = JSON.parse(text);
        formatted = JSON.stringify(json, null, 2);
      } catch {
        formatted = text;
      }

      setOutput(formatted);
      setHistory((prev) => [
        { cmd, output: formatted, timestamp: Date.now() },
        ...prev,
      ]);
      setCommand('');

      // 滚动到底部
      setTimeout(() => {
        outputRef.current?.scrollTo({ top: outputRef.current.scrollHeight, behavior: 'smooth' });
      }, 50);
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : '执行失败';
      setOutput(`错误: ${errMsg}`);
      setHistory((prev) => [
        { cmd, output: `错误: ${errMsg}`, timestamp: Date.now() },
        ...prev,
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleHistoryClick(entry: HistoryEntry) {
    setCommand(entry.cmd);
    setOutput(entry.output);
  }

  function formatTime(ts: number) {
    return new Date(ts).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  return (
    <div style={s.container}>
      {/* 命令输入区 */}
      <form style={s.inputForm} onSubmit={handleExecute}>
        <input
          style={s.input}
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder="输入命令 (ps, stats, help, boot)..."
          disabled={loading}
          autoComplete="off"
        />
        <button
          type="submit"
          style={loading || !command.trim() ? s.execBtnDisabled : s.execBtn}
          disabled={loading || !command.trim()}
        >
          {loading ? '执行中...' : '执行'}
        </button>
      </form>

      {/* 快捷命令 */}
      <div style={s.quickActions}>
        <span style={s.quickLabel}>快捷:</span>
        {['ps', 'stats', 'help', 'boot'].map((cmd) => (
          <button
            key={cmd}
            style={s.quickBtn}
            onClick={() => setCommand((prev) => prev || cmd)}
            disabled={loading}
          >
            {cmd}
          </button>
        ))}
      </div>

      {/* 输出区 */}
      <div style={s.outputArea} ref={outputRef}>
        {output ? (
          <pre style={s.outputText}>{output}</pre>
        ) : (
          <div style={s.outputEmpty}>
            <span style={s.outputEmptyIcon}>⌨️</span>
            <span>执行命令查看输出</span>
          </div>
        )}
      </div>

      {/* 历史记录 */}
      {history.length > 0 && (
        <div style={s.historySection}>
          <div style={s.historyTitle}>历史记录</div>
          <div style={s.historyList}>
            {history.map((entry, idx) => (
              <div
                key={idx}
                style={s.historyItem}
                onClick={() => handleHistoryClick(entry)}
                title="点击复用"
              >
                <span style={s.historyTime}>{formatTime(entry.timestamp)}</span>
                <span style={s.historyCmd}>{entry.cmd}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    padding: 8,
    gap: 10,
  },
  inputForm: {
    display: 'flex',
    gap: 8,
  },
  input: {
    flex: 1,
    padding: '8px 10px',
    background: '#ffffff',
    border: '1px solid #e4e4e7',
    borderRadius: 6,
    fontSize: 13,
    color: '#28282c',
    outline: 'none',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
  },
  execBtn: {
    padding: '8px 16px',
    background: '#0066b8',
    color: '#ffffff',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  execBtnDisabled: {
    padding: '8px 16px',
    background: '#ebecee',
    color: '#9ca3af',
    border: 'none',
    borderRadius: 6,
    cursor: 'not-allowed',
    fontSize: 13,
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  quickActions: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    flexWrap: 'wrap',
  },
  quickLabel: {
    fontSize: 11,
    color: '#9ca3af',
    marginRight: 2,
  },
  quickBtn: {
    padding: '3px 10px',
    background: '#f4f5f7',
    border: '1px solid #e4e4e7',
    borderRadius: 4,
    fontSize: 11,
    color: '#28282c',
    cursor: 'pointer',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
  },
  outputArea: {
    flex: 1,
    minHeight: 120,
    background: '#1e1e1e',
    borderRadius: 8,
    padding: 10,
    overflowY: 'auto',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
  },
  outputText: {
    margin: 0,
    fontSize: 12,
    color: '#4ec9b0',
    lineHeight: 1.6,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-all',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
  },
  outputEmpty: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    minHeight: 100,
    gap: 6,
    fontSize: 12,
    color: '#6b7280',
  },
  outputEmptyIcon: { fontSize: 20, opacity: 0.4 },
  historySection: {
    borderTop: '1px solid #e4e4e7',
    paddingTop: 8,
  },
  historyTitle: {
    fontSize: 11,
    fontWeight: 600,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  historyList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    maxHeight: 120,
    overflowY: 'auto',
  },
  historyItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '4px 8px',
    borderRadius: 4,
    cursor: 'pointer',
    transition: 'background 0.15s',
    background: 'transparent',
  },
  historyTime: {
    fontSize: 10,
    color: '#9ca3af',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
    whiteSpace: 'nowrap',
  },
  historyCmd: {
    fontSize: 12,
    color: '#28282c',
    fontFamily: '"JetBrains Mono", Menlo, monospace',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
};