/**
 * OfficeAgent Studio — 全局状态管理
 *
 * 使用 React Context + useReducer 实现(不引入 zustand)。
 * 提供 StudioProvider 和 useStudio() hook。
 *
 * 注:文件扩展名为 .tsx,因 StudioProvider 包含 JSX。
 */
import {
  createContext,
  useContext,
  useReducer,
  useMemo,
  type Dispatch,
  type ReactNode,
} from 'react';
import type {
  AgentProcessInfo,
  AgentStatus,
  AppMode,
  CenterPanelView,
  ChatMessage,
  ComposerMode,
  ContextChip,
  FileChange,
  LeftPanelView,
  RightPanelView,
  Theme,
} from './types';

/** Studio 全局状态 */
export interface StudioState {
  mode: AppMode;
  leftPanel: LeftPanelView;
  rightPanel: RightPanelView;
  centerPanel: CenterPanelView;
  activeFile: string | null;
  openFiles: string[];
  theme: Theme;
  composerMode: ComposerMode;
  isStreaming: boolean;
  messages: ChatMessage[];
  contextChips: ContextChip[];
  pendingDiff: FileChange[] | null;
  agentStatus: AgentStatus;
  processes: AgentProcessInfo[];
}

/** 初始状态 */
const initialState: StudioState = {
  mode: 'ide',
  leftPanel: 'files',
  rightPanel: 'chat',
  centerPanel: 'editor',
  activeFile: null,
  openFiles: [],
  theme: 'light',
  composerMode: 'agent',
  isStreaming: false,
  messages: [
    {
      id: 'welcome',
      role: 'assistant',
      content:
        '你好!我是 OfficeAgent Studio,你的智能办公助手。有什么可以帮你的?\n\n试试输入 `/` 查看命令,或 `@` 添加上下文。',
      ts: Date.now(),
    },
  ],
  contextChips: [],
  pendingDiff: null,
  agentStatus: 'idle',
  processes: [],
};

/** Action 类型 — 判别式联合 */
export type StudioAction =
  | { type: 'SET_MODE'; mode: AppMode }
  | { type: 'SET_LEFT_PANEL'; view: LeftPanelView }
  | { type: 'SET_RIGHT_PANEL'; view: RightPanelView }
  | { type: 'OPEN_FILE'; filePath: string }
  | { type: 'CLOSE_FILE'; filePath: string }
  | { type: 'SET_THEME'; theme: Theme }
  | { type: 'SET_COMPOSER_MODE'; mode: ComposerMode }
  | { type: 'ADD_MESSAGE'; message: ChatMessage }
  | { type: 'UPDATE_MESSAGE'; id: string; patch: Partial<ChatMessage> }
  | { type: 'SET_STREAMING'; streaming: boolean }
  | { type: 'ADD_CONTEXT_CHIP'; chip: ContextChip }
  | { type: 'REMOVE_CONTEXT_CHIP'; id: string }
  | { type: 'SET_PENDING_DIFF'; changes: FileChange[] | null }
  | { type: 'ACCEPT_FILE_CHANGE'; filePath: string }
  | { type: 'REJECT_FILE_CHANGE'; filePath: string }
  | { type: 'SET_AGENT_STATUS'; status: AgentStatus }
  | { type: 'SET_PROCESSES'; processes: AgentProcessInfo[] }
  | { type: 'CLEAR_MESSAGES' };

/** 欢迎消息工厂 */
function welcomeMessage(): ChatMessage {
  return {
    id: 'welcome',
    role: 'assistant',
    content:
      '你好!我是 OfficeAgent Studio,你的智能办公助手。有什么可以帮你的?\n\n试试输入 `/` 查看命令,或 `@` 添加上下文。',
    ts: Date.now(),
  };
}

/** Reducer — 纯函数状态转换 */
function reducer(state: StudioState, action: StudioAction): StudioState {
  switch (action.type) {
    case 'SET_MODE': {
      // IDE 模式中栏=editor 右栏=chat;SOLO 模式中栏=chat 右栏=diff
      const centerPanel: CenterPanelView =
        action.mode === 'ide' ? 'editor' : 'chat';
      const rightPanel: RightPanelView = action.mode === 'ide' ? 'chat' : 'diff';
      return { ...state, mode: action.mode, centerPanel, rightPanel };
    }
    case 'SET_LEFT_PANEL':
      return { ...state, leftPanel: action.view };
    case 'SET_RIGHT_PANEL':
      return { ...state, rightPanel: action.view };
    case 'OPEN_FILE': {
      const openFiles = state.openFiles.includes(action.filePath)
        ? state.openFiles
        : [...state.openFiles, action.filePath];
      return { ...state, activeFile: action.filePath, openFiles };
    }
    case 'CLOSE_FILE': {
      const openFiles = state.openFiles.filter((f) => f !== action.filePath);
      const activeFile =
        state.activeFile === action.filePath
          ? (openFiles[openFiles.length - 1] ?? null)
          : state.activeFile;
      return { ...state, openFiles, activeFile };
    }
    case 'SET_THEME':
      return { ...state, theme: action.theme };
    case 'SET_COMPOSER_MODE':
      return { ...state, composerMode: action.mode };
    case 'ADD_MESSAGE':
      return { ...state, messages: [...state.messages, action.message] };
    case 'UPDATE_MESSAGE':
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.id ? { ...m, ...action.patch } : m,
        ),
      };
    case 'SET_STREAMING':
      return { ...state, isStreaming: action.streaming };
    case 'ADD_CONTEXT_CHIP':
      return { ...state, contextChips: [...state.contextChips, action.chip] };
    case 'REMOVE_CONTEXT_CHIP':
      return {
        ...state,
        contextChips: state.contextChips.filter((c) => c.id !== action.id),
      };
    case 'SET_PENDING_DIFF':
      return { ...state, pendingDiff: action.changes };
    case 'ACCEPT_FILE_CHANGE':
      return {
        ...state,
        pendingDiff: state.pendingDiff
          ? state.pendingDiff.map((c) =>
              c.filePath === action.filePath
                ? { ...c, status: 'accepted' as const }
                : c,
            )
          : null,
      };
    case 'REJECT_FILE_CHANGE':
      return {
        ...state,
        pendingDiff: state.pendingDiff
          ? state.pendingDiff.map((c) =>
              c.filePath === action.filePath
                ? { ...c, status: 'rejected' as const }
                : c,
            )
          : null,
      };
    case 'SET_AGENT_STATUS':
      return { ...state, agentStatus: action.status };
    case 'SET_PROCESSES':
      return { ...state, processes: action.processes };
    case 'CLEAR_MESSAGES':
      return { ...state, messages: [welcomeMessage()] };
    default:
      return state;
  }
}

interface StudioContextValue {
  state: StudioState;
  dispatch: Dispatch<StudioAction>;
}

const StudioContext = createContext<StudioContextValue | null>(null);

/** Studio 状态 Provider — 包裹在应用根部 */
export function StudioProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const value = useMemo<StudioContextValue>(
    () => ({ state, dispatch }),
    [state],
  );
  return (
    <StudioContext.Provider value={value}>{children}</StudioContext.Provider>
  );
}

/** 使用 Studio 全局状态 */
export function useStudio(): StudioContextValue {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error('useStudio 必须在 StudioProvider 内使用');
  return ctx;
}
