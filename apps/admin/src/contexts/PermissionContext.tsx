/**
 * Phase 2.1: 权限上下文
 *
 * 加载当前用户权限码集合,提供 hasPermission / hasAnyPermission 辅助函数,
 * 供菜单/按钮级权限控制使用。
 *
 * 用法:
 *   <PermissionProvider>
 *     <App />
 *   </PermissionProvider>
 *
 *   const { hasPermission } = usePermissions();
 *   {hasPermission('role:create') && <Button>新建角色</Button>}
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { sdk } from '@fnixagent/sdk';

interface PermissionContextValue {
  permissions: Set<string>;
  loading: boolean;
  error: string | null;
  /** 检查是否拥有指定权限 */
  hasPermission: (code: string) => boolean;
  /** 检查是否拥有任一权限 */
  hasAnyPermission: (...codes: string[]) => boolean;
  /** 检查是否拥有全部权限 */
  hasAllPermissions: (...codes: string[]) => boolean;
  /** 重新加载权限(角色变更后调用) */
  refresh: () => Promise<void>;
}

const PermissionContext = createContext<PermissionContextValue | null>(null);

export function PermissionProvider({ children }: { children: ReactNode }) {
  const [permissions, setPermissions] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadPermissions() {
    try {
      setError(null);
      const resp = await sdk.rbac.myPermissions();
      const codes = resp.data?.permissions ?? [];
      setPermissions(new Set(codes));
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载权限失败');
      // 权限加载失败时给空集合(最安全)
      setPermissions(new Set());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPermissions();
  }, []);

  const value: PermissionContextValue = {
    permissions,
    loading,
    error,
    hasPermission: (code: string) => permissions.has(code),
    hasAnyPermission: (...codes: string[]) => codes.some((c) => permissions.has(c)),
    hasAllPermissions: (...codes: string[]) => codes.every((c) => permissions.has(c)),
    refresh: loadPermissions,
  };

  return <PermissionContext.Provider value={value}>{children}</PermissionContext.Provider>;
}

export function usePermissions(): PermissionContextValue {
  const ctx = useContext(PermissionContext);
  if (!ctx) {
    throw new Error('usePermissions 必须在 <PermissionProvider> 内使用');
  }
  return ctx;
}

/**
 * 权限守卫组件:仅当用户拥有指定权限时才渲染子组件。
 *
 * 用法:
 *   <HasPermission code="role:create">
 *     <Button>新建角色</Button>
 *   </HasPermission>
 */
export function HasPermission({
  code,
  children,
  fallback = null,
}: {
  code: string;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { hasPermission } = usePermissions();
  return hasPermission(code) ? <>{children}</> : <>{fallback}</>;
}

/**
 * 任一权限守卫:拥有任一权限时渲染。
 */
export function HasAnyPermission({
  codes,
  children,
  fallback = null,
}: {
  codes: string[];
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { hasAnyPermission } = usePermissions();
  return hasAnyPermission(...codes) ? <>{children}</> : <>{fallback}</>;
}
