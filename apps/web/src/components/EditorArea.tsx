import { useCallback, useEffect, useRef, useState } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import { Button } from '@officeagent/ui';

interface EditorAreaProps {
  filePath?: string;
}

// 文件扩展名 → Monaco 语言 ID 映射
const EXT_LANG_MAP: Record<string, string> = {
  md: 'markdown',
  markdown: 'markdown',
  txt: 'plaintext',
  py: 'python',
  js: 'javascript',
  ts: 'typescript',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  html: 'html',
  css: 'css',
  xml: 'xml',
  sql: 'sql',
};

// 自动保存延迟(ms)
const AUTOSAVE_DELAY = 3000;

/**
 * 中间文档编辑区 — Monaco Editor 集成
 *
 * 功能:
 *   - 支持 .md/.txt/.py/.json/.yaml 语法高亮
 *   - Markdown 预览模式切换
 *   - Ctrl+S 保存(通过 IPC 写回磁盘,Electron 环境)
 *   - 自动保存(3 秒无操作后触发,防丢失)
 */
export function EditorArea({ filePath }: EditorAreaProps) {
  const [content, setContent] = useState<string>('');
  const [isDirty, setIsDirty] = useState(false);
  const [lastSaved, setLastSaved] = useState<string>('');
  const [previewMode, setPreviewMode] = useState(false);
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);

  // 文件路径变化时加载内容(模拟,Electron 环境通过 IPC 读取)
  useEffect(() => {
    if (!filePath) {
      setContent('');
      setIsDirty(false);
      return;
    }
    // 模拟加载文件内容(Phase 1.5 Electron 将通过 IPC 读取真实文件)
    const ext = filePath.split('.').pop() || '';
    const sample = SAMPLE_CONTENT[ext] || `# ${filePath}\n\n文件内容将在此显示。`;
    setContent(sample);
    setLastSaved(sample);
    setIsDirty(false);
  }, [filePath]);

  // 自动保存:内容变化后 3 秒无操作自动保存
  const scheduleAutoSave = useCallback(
    (newContent: string) => {
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
      autoSaveTimer.current = setTimeout(() => {
        if (newContent !== lastSaved) {
          setLastSaved(newContent);
          setIsDirty(false);
          // Electron 环境:通过 IPC 写回磁盘
          // window.electron?.ipcRenderer.send('file:save', filePath, newContent);
          console.log(`[autosave] ${filePath} 已自动保存`);
        }
      }, AUTOSAVE_DELAY);
    },
    [filePath, lastSaved],
  );

  const handleContentChange = useCallback(
    (value: string | undefined) => {
      const newContent = value || '';
      setContent(newContent);
      setIsDirty(newContent !== lastSaved);
      scheduleAutoSave(newContent);
    },
    [lastSaved, scheduleAutoSave],
  );

  // Ctrl+S 手动保存
  const handleSave = useCallback(() => {
    if (!filePath) return;
    setLastSaved(content);
    setIsDirty(false);
    // Electron 环境:通过 IPC 写回磁盘
    // window.electron?.ipcRenderer.send('file:save', filePath, content);
    console.log(`[save] ${filePath} 已保存(Ctrl+S)`);
  }, [filePath, content]);

  // Monaco 编辑器挂载回调
  const handleMount: OnMount = useCallback((editor, monaco) => {
    editorRef.current = editor;
    // 注册 Ctrl+S 快捷键
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      handleSave();
    });
  }, [handleSave]);

  // 获取 Monaco 语言 ID
  const getLanguage = (path: string): string => {
    const ext = path.split('.').pop()?.toLowerCase() || '';
    return EXT_LANG_MAP[ext] || 'plaintext';
  };

  if (!filePath) {
    return (
      <div className="flex h-full flex-col bg-background">
        <div className="flex items-center border-b border-border px-4 py-1.5 h-9 shrink-0">
          <span className="text-sm text-muted-foreground">未打开文件</span>
        </div>
        <div className="flex-1 flex items-center justify-center text-muted-foreground">
          <div className="text-center">
            <p className="mb-2 text-4xl">📝</p>
            <p>从左侧文件树选择一个文件,或拖拽文件到此区域</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-background">
      {/* 标签栏 */}
      <div className="flex items-center justify-between border-b border-border px-4 py-1.5 h-9 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-sm">{filePath}</span>
          {isDirty && <span className="text-xs text-amber-500">● 未保存</span>}
        </div>
        <div className="flex items-center gap-1">
          {filePath.endsWith('.md') && (
            <Button
              variant={previewMode ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setPreviewMode(!previewMode)}
            >
              {previewMode ? '编辑' : '预览'}
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={handleSave} disabled={!isDirty}>
            保存
          </Button>
        </div>
      </div>

      {/* 编辑器 / 预览区 */}
      <div className="flex-1 overflow-hidden">
        {previewMode && filePath.endsWith('.md') ? (
          <MarkdownPreview content={content} />
        ) : (
          <Editor
            height="100%"
            language={getLanguage(filePath)}
            value={content}
            onChange={handleContentChange}
            onMount={handleMount}
            theme="vs-dark"
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              lineNumbers: 'on',
              wordWrap: 'on',
              tabSize: 2,
              automaticLayout: true,
              scrollBeyondLastLine: false,
              padding: { top: 12, bottom: 12 },
            }}
          />
        )}
      </div>
    </div>
  );
}

/**
 * 简易 Markdown 预览(Phase 1.5 基础版,后续可替换为 react-markdown)
 */
function MarkdownPreview({ content }: { content: string }) {
  // 基础 Markdown → HTML 转换(标题/粗体/斜体/代码块/列表)
  const html = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/\n/g, '<br />');

  return (
    <div
      className="prose prose-sm dark:prose-invert max-w-none overflow-auto p-6"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

// 示例文件内容(按扩展名)
const SAMPLE_CONTENT: Record<string, string> = {
  md: `#欢迎使用 OfficeAgent

这是一个 **Markdown** 文件示例。

## 功能列表
- 文件编辑
- 语法高亮
- Ctrl+S 保存
- 自动保存(3秒延迟)
- Markdown 预览模式

\`\`\`python
def hello():
    print("Hello, OfficeAgent!")
\`\`\`
`,
  txt: '这是一个纯文本文件。\n支持 Ctrl+S 保存和自动保存。',
  py: `# OfficeAgent Python 示例
def main():
    print("Hello, OfficeAgent!")

if __name__ == "__main__":
    main()
`,
  json: `{
  "name": "officeagent",
  "version": "1.0.0",
  "description": "智能办公助手"
}
`,
  yaml: `# OfficeAgent 配置
server:
  host: localhost
  port: 8000
`,
};
