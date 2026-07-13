/**
 * OfficeAgent Desktop 渲染进程根组件
 *
 * 职责:
 *   1. 启动时尝试加载已保存的 Token,自动登录
 *   2. 未登录 → 显示 LoginPage(手机号 / Google 双 Tab)
 *   3. 已登录 → 显示 MainApp(Phase 3.0 占位,3.1 替换为三栏工作台)
 */
import { useEffect, useState } from 'react';
import { auth, type AuthUser } from '@officeagent/sdk';
import { LoginPage } from './LoginPage';
import { MainApp } from './MainApp';

type AppState =
  | { phase: 'loading' }
  | { phase: 'unauthenticated' }
  | { phase: 'authenticated'; user: AuthUser };

function App() {
  const [state, setState] = useState<AppState>({ phase: 'loading' });

  // 启动时尝试用已保存的 Token 自动恢复会话
  useEffect(() => {
    void (async () => {
      try {
        await auth.loadStoredTokens();
        const user = await auth.getCurrentUser();
        if (user) {
          setState({ phase: 'authenticated', user });
        } else {
          setState({ phase: 'unauthenticated' });
        }
      } catch {
        setState({ phase: 'unauthenticated' });
      }
    })();
  }, []);

  function handleLogin(user: AuthUser) {
    setState({ phase: 'authenticated', user });
  }

  function handleLogout() {
    setState({ phase: 'unauthenticated' });
  }

  if (state.phase === 'loading') {
    return (
      <div style={loadingStyle.container}>
        <div style={loadingStyle.spinner} />
        <p style={loadingStyle.text}>加载中...</p>
      </div>
    );
  }

  if (state.phase === 'unauthenticated') {
    return <LoginPage onLogin={handleLogin} />;
  }

  return <MainApp user={state.user} onLogout={handleLogout} />;
}

const loadingStyle: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#0f172a',
    color: '#e2e8f0',
    gap: 12,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  spinner: {
    width: 32,
    height: 32,
    borderRadius: '50%',
    border: '3px solid rgba(148, 163, 184, 0.2)',
    borderTopColor: '#3b82f6',
    animation: 'spin 0.8s linear infinite',
  },
  text: {
    margin: 0,
    fontSize: 13,
    color: '#94a3b8',
  },
};

export default App;
