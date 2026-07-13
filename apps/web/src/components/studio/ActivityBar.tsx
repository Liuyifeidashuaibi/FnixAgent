/**
 * fnixagent Studio — 左侧活动栏 (VS Code/Cursor 风格)
 *
 * 48px 宽,垂直排列图标按钮,选中态左侧 2px 蓝色竖条。
 */
import { useStudio } from '../../stores/studio-store';
import type { LeftPanelView } from '../../stores/types';
import {
  FilesIcon,
  GitIcon,
  ProcessesIcon,
  SearchIcon,
  SettingsIcon,
  TasksIcon,
} from './icons';

interface ActivityItem {
  view: LeftPanelView;
  label: string;
  Icon: typeof FilesIcon;
}

const ITEMS: ActivityItem[] = [
  { view: 'files', label: '文件', Icon: FilesIcon },
  { view: 'search', label: '搜索', Icon: SearchIcon },
  { view: 'tasks', label: '任务', Icon: TasksIcon },
  { view: 'processes', label: '进程', Icon: ProcessesIcon },
];

/** 活动栏 — 48px 宽 */
export function ActivityBar() {
  const { state, dispatch } = useStudio();
  const { leftPanel } = state;

  return (
    <nav className="flex w-12 shrink-0 flex-col items-center justify-between border-r border-border bg-background py-2">
      <div className="flex flex-col items-center gap-1">
        {ITEMS.map(({ view, label, Icon }) => {
          const active = leftPanel === view;
          return (
            <button
              key={view}
              type="button"
              title={label}
              onClick={() => dispatch({ type: 'SET_LEFT_PANEL', view })}
              className={`relative flex h-9 w-9 items-center justify-center rounded-md transition-colors ${
                active
                  ? 'text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {/* 选中态左侧 2px 蓝色竖条 */}
              {active && (
                <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-x-[7px] -translate-y-1/2 rounded-full bg-primary" />
              )}
              <Icon width={22} height={22} />
            </button>
          );
        })}
      </div>
      {/* 底部:Git + 设置 */}
      <div className="flex flex-col items-center gap-1">
        <button
          type="button"
          title="Git"
          className="flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <GitIcon width={22} height={22} />
        </button>
        <button
          type="button"
          title="设置"
          className="flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <SettingsIcon width={22} height={22} />
        </button>
      </div>
    </nav>
  );
}
