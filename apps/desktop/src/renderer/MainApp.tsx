/**
 * OfficeAgent Desktop 主应用视图 — Cursor/Codex 风格
 *
 * 设计理念：浅色主题 + 极简留白 + 四栏布局（ActivityBar/Sidebar/Center/AgentPanel）
 *   - 左侧 ActivityBar（48px，竖向图标）
 *   - 左侧 Sidebar（260px，内容随 Activity 切换）
 *   - 中间 CenterArea（flex-1，TabBar + Editor/Chat + CommandInput）
 *   - 右侧 AgentPanel（320px，AgentOS 进程/记忆/Shell/Policy）
 *
 * 所有样式内联，CSS 变量与 index.css 对齐：
 *   --bg-primary: #ffffff
 *   --bg-secondary: #f4f5f7
 *   --border-color: #e4e4e7
 *   --text-primary: #28282c
 *   --text-secondary: #6b7280
 *   --accent: #0066b8
 *   --font-sans: Inter...
 *   --font-mono: JetBrains Mono...
 */
import { StudioLayout } from './StudioLayout';

interface MainAppProps {
  user: unknown;
  onLogout: () => void;
}

export function MainApp({ user: _user, onLogout }: MainAppProps) {
  // 由 StudioLayout 完成状态管理，我们只需要传递回调
  // 用户在 StudioLayout 中打开文件 → 传递给 EditorPanel
  // 我们在这里只做入口容器 + 根布局
  return (
    <StudioLayout onLogout={onLogout} />
  );
}
