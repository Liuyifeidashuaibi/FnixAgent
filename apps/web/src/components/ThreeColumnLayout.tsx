import { useState } from 'react';
import { TopBar } from './TopBar';
import { FileTree } from './FileTree';
import { EditorArea } from './EditorArea';
import { ChatPanel } from './ChatPanel';
import { ResizablePanel } from './ResizablePanel';
import { useTheme } from '../hooks/useTheme';

/**
 * 三栏极简布局
 * 左:文件树 | 中:文档编辑区 | 右:AI 对话面板
 * 顶部:工具栏(主题切换/设置)
 */
export function ThreeColumnLayout() {
  const { theme, toggle } = useTheme();
  const [selectedFile, setSelectedFile] = useState<string | undefined>();

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <TopBar theme={theme} onToggleTheme={toggle} />

      <div className="flex flex-1 overflow-hidden">
        {/* 左栏:文件树 */}
        <ResizablePanel side="left" initialWidth={240}>
          <FileTree onFileSelect={setSelectedFile} />
        </ResizablePanel>

        {/* 中栏:编辑区 */}
        <div className="flex-1 min-w-0">
          <EditorArea filePath={selectedFile} />
        </div>

        {/* 右栏:AI 对话 */}
        <ResizablePanel side="right" initialWidth={360}>
          <ChatPanel onSendMessage={(msg) => console.log('发送消息:', msg)} />
        </ResizablePanel>
      </div>
    </div>
  );
}
