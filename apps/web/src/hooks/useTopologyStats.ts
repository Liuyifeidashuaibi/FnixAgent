import { useCallback, useState } from 'react';
import { sdk, type TopologyStats } from '@officeagent/sdk';

/**
 * 拓扑统计 Hook — 调用 /api/v1/chat/topology/stats
 *
 * 用于 Phase 1.6 右侧面板的拓扑路径展示。
 */
export function useTopologyStats() {
  const [stats, setStats] = useState<TopologyStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await sdk.chat.topologyStats();
      if (resp.success) {
        setStats(resp.data);
      } else {
        setError('拓扑统计获取失败');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  return { stats, loading, error, refresh };
}
