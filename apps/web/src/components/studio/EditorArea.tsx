/**
 * fnixagent Studio — Monaco 编辑器区(浅色主题)
 *
 * 对标 Cursor IDE 编辑区:
 *   - Monaco 主题使用 light(非 vs-dark)
 *   - 标签栏显示打开的文件列表
 *   - 支持从全局状态读取 activeFile / openFiles
 *   - Ctrl+S 保存 + 自动保存
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import { Button } from '@fnixagent/ui';
import { CloseIcon } from './icons';
import { useStudio } from '../../stores/studio-store';

// 文件扩展名 → Monaco 语言 ID
const EXT_LANG_MAP: Record<string, string> = {
  md: 'markdown',
  markdown: 'markdown',
  txt: 'plaintext',
  py: 'python',
  js: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  html: 'html',
  css: 'css',
  xml: 'xml',
  sql: 'sql',
};

// 示例文件内容(按扩展名)— 后续通过 sdk.code.read 读取真实文件
const SAMPLE_CONTENT: Record<string, string> = {
  md: `# fnixagent Studio

这是一个 **Markdown** 文件示例。

## 功能
- 代码编辑
- 语法高亮
- Ctrl+S 保存
- 自动保存

\`\`\`python
def hello():
    print("Hello, fnixagent!")
\`\`\`
`,
  tsx: `import { useState } from 'react';

export function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(count + 1)}>{count}</button>;
}
`,
  py: `def main():
    print("Hello, fnixagent!")

if __name__ == "__main__":
    main()
`,
};

/**
 * 编辑器区域 — 读取全局状态的 activeFile / openFiles
 */
export function EditorArea() {
  const { state, dispatch } = useStudio();
  const { activeFile, openFiles } = state;
  const [content, setContent] = useState('');
  const [isDirty, setIsDirty] = useState(false);
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);

  // 文件切换时加载内容(模拟,后续接 sdk.code.read)
  useEffect(() => {
    if (!activeFile) {
      setContent('');
      setIsDirty(false);
      return;
    }
    const ext = activeFile.split('.').pop() || '';
    const sample =
      SAMPLE_CONTENT[ext] ?? `# ${activeFile}\n\n文件内容将在此显示。`;
    setContent(sample);
    setIsDirty(false);
  }, [activeFile]);

  const handleChange = useCallback((value: string | undefined) => {
    setContent(value || '');
    setIsDirty(true);
  }, []);

  const handleSave = useCallback(() => {
    if (!activeFile) return;
    setIsDirty(false);
    // 后续接 sdk.code.write
  }, [activeFile]);

  const handleMount: OnMount = useCallback(
    (editor, monaco) => {
      editorRef.current = editor;
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
        handleSave();
      });
    },
    [handleSave],
  );

  const getLanguage = (path: string): string => {
    const ext = path.split('.').pop()?.toLowerCase() || '';
    return EXT_LANG_MAP[ext] || 'plaintext';
  };

  // 空状态
  if (!activeFile) {
    return (
      <div className="flex h-full flex-col bg-background">
        <TabBar
          openFiles={openFiles}
          activeFile={activeFile}
          onSelect={(f) => dispatch({ type: 'OPEN_FILE', filePath: f })}
          onClose={(f) => dispatch({ type: 'CLOSE_FILE', filePath: f })}
        />
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <div className="text-center">
            <p className="mb-1 text-sm font-medium">未打开文件</p>
            <p className="text-xs">从左侧文件树选择一个文件开始编辑</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <TabBar
        openFiles={openFiles}
        activeFile={activeFile}
        onSelect={(f) => dispatch({ type: 'OPEN_FILE', filePath: f })}
        onClose={(f) => dispatch({ type: 'CLOSE_FILE', filePath: f })}
      />
      {/* 标签栏下方路径条 */}
      <div className="flex items-center justify-between border-b border-border px-4 py-1.5 h-8 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">{activeFile}</span>
          {isDirty && <span className="text-xs text-amber-500">●</span>}
        </div>
        <Button variant="ghost" size="sm" onClick={handleSave} disabled={!isDirty}>
          保存
        </Button>
      </div>
      <div className="flex-1 overflow-hidden">
        <Editor
          height="100%"
          language={getLanguage(activeFile)}
          value={content}
          onChange={handleChange}
          onMount={handleMount}
          theme="light"
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            lineNumbers: 'on',
            wordWrap: 'on',
            tabSize: 2,
            automaticLayout: true,
            scrollBeyondLastLine: false,
            padding: { top: 12, bottom: 12 },
            fontFamily: "'JetBrains Mono', 'SF Mono', 'Menlo', 'Consolas', monospace",
          }}
        />
      </div>
    </div>
  );
}

/** 文件标签栏 — 横向滚动显示打开的文件 */
function TabBar({
  openFiles,
  activeFile,
  onSelect,
  onClose,
}: {
  openFiles: string[];
  activeFile: string | null;
  onSelect: (path: string) => void;
  onClose: (path: string) => void;
}) {
  if (openFiles.length === 0) {
    return <div className="h-9 border-b border-border shrink-0" />;
  }
  return (
    <div className="flex items-stretch border-b border-border h-9 shrink-0 overflow-x-auto">
      {openFiles.map((file) => {
        const name = file.split('/').pop() || file;
        const active = file === activeFile;
        return (
          <div
            key={file}
            className={`group flex items-center gap-1 border-r border-border px-3 cursor-pointer text-xs whitespace-nowrap transition-colors ${
              active
                ? 'bg-background text-foreground'
                : 'bg-secondary/50 text-muted-foreground hover:bg-secondary'
            }`}
            onClick={() => onSelect(file)}
          >
            <span>{name}</span>
            <button
              type="button"
              className="ml-1 rounded p-0.5 opacity-0 hover:bg-accent group-hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation();
                onClose(file);
              }}
            >
              <CloseIcon width={12} height={12} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
