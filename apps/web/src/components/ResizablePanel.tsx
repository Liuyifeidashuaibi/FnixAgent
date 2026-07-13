import { useCallback, useRef, useState } from 'react';

interface ResizablePanelProps {
  children: React.ReactNode;
  side: 'left' | 'right';
  initialWidth: number;
  minWidth?: number;
  maxWidth?: number;
  onResize?: (width: number) => void;
}

/**
 * 可拖拽调整宽度的侧边面板
 * 三栏布局的左/右栏使用此组件实现拖拽调整
 */
export function ResizablePanel({
  children,
  side,
  initialWidth,
  minWidth = 180,
  maxWidth = 500,
  onResize,
}: ResizablePanelProps) {
  const [width, setWidth] = useState(initialWidth);
  const isResizing = useRef(false);
  const startPos = useRef(0);
  const startWidth = useRef(0);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      isResizing.current = true;
      startPos.current = e.clientX;
      startWidth.current = width;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    },
    [width],
  );

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isResizing.current) return;
      const delta = side === 'left' ? e.clientX - startPos.current : startPos.current - e.clientX;
      const newWidth = Math.max(minWidth, Math.min(maxWidth, startWidth.current + delta));
      setWidth(newWidth);
      onResize?.(newWidth);
    },
    [side, minWidth, maxWidth, onResize],
  );

  const handleMouseUp = useCallback(() => {
    isResizing.current = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  // 全局鼠标事件(拖拽时鼠标可能移出面板范围)
  if (typeof window !== 'undefined') {
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  }

  return (
    <div className="relative shrink-0" style={{ width }}>
      {children}
      {/* 拖拽手柄 */}
      <div
        className={`absolute top-0 bottom-0 w-1 cursor-col-resize hover:bg-ring/50 transition-colors ${
          side === 'left' ? 'right-0' : 'left-0'
        }`}
        onMouseDown={handleMouseDown}
      />
    </div>
  );
}
