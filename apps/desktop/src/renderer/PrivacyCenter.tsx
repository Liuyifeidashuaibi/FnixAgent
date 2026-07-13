/**
 * 桌面端隐私中心(Phase 4.5)
 *
 * 功能:
 *   - 查看本人个人数据(手机号已脱敏)
 *   - 导出全部数据(JSON)
 *   - 注销账号(软删除,30 天保留)
 *   - 撤销注销
 */
import { useEffect, useState } from 'react';
import type { AuthUser } from '@fnixagent/sdk';
import { sdk, type PrivacyProfile, type PrivacyDeletionStatus } from '@fnixagent/sdk';
import { downloadTextFile } from './utils';

interface Props {
  user: AuthUser;
  onBack: () => void;
  onLogout: () => void;
}

export function PrivacyCenter({ user, onBack, onLogout }: Props) {
  const [profile, setProfile] = useState<PrivacyProfile | null>(null);
  const [status, setStatus] = useState<PrivacyDeletionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [profResp, statusResp] = await Promise.all([
        sdk.privacy.profile(),
        sdk.privacy.deletionStatus(),
      ]);
      if (profResp.success && profResp.data) setProfile(profResp.data);
      if (statusResp.success && statusResp.data) setStatus(statusResp.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  async function handleExport() {
    try {
      const text = await sdk.privacy.export();
      downloadTextFile(text, `fnixagent_export_${Date.now()}.json`, 'application/json');
    } catch (e) {
      alert(e instanceof Error ? e.message : '导出失败');
    }
  }

  async function handleDeleteAccount() {
    try {
      const resp = await sdk.privacy.deleteAccount(30);
      if (resp.success) {
        alert('账号注销请求已提交,30 天后永久删除。期间可登录撤销。');
        await load();
      } else {
        alert('注销失败');
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : '注销失败');
    } finally {
      setConfirmDelete(false);
    }
  }

  async function handleCancelDeletion() {
    try {
      const resp = await sdk.privacy.cancelDeletion();
      if (resp.success) {
        alert('已撤销注销请求');
        await load();
      } else {
        alert('撤销失败');
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : '撤销失败');
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loading}>加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.container}>
        <div style={styles.error}>{error}</div>
        <button style={styles.btn} onClick={load}>重试</button>
      </div>
    );
  }

  const isPendingDeletion = status?.status === 'pending_deletion';

  return (
    <div style={styles.container}>
      {/* 顶栏 */}
      <header style={styles.header}>
        <button style={styles.backBtn} onClick={onBack}>← 返回</button>
        <h1 style={styles.title}>隐私中心</h1>
        <div style={styles.userBox}>
          <div style={styles.avatar}>{user.username.charAt(0).toUpperCase()}</div>
          <button style={styles.logoutBtn} onClick={onLogout}>退出</button>
        </div>
      </header>

      <div style={styles.content}>
        {/* 个人信息 */}
        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>个人信息</h2>
          <div style={styles.card}>
            <Row label="用户名" value={profile?.username} />
            <Row label="邮箱" value={profile?.email} />
            <Row label="手机号" value={profile?.phone} hint="已脱敏" />
            <Row label="角色" value={profile?.role} />
            <Row label="注册时间" value={profile?.created_at?.slice(0, 10)} />
            <Row
              label="配额"
              value={profile ? `${profile.quota.used} / ${profile.quota.total}` : '-'}
              hint="已用 / 总量"
            />
          </div>
        </section>

        {/* 数据导出 */}
        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>数据导出</h2>
          <div style={styles.card}>
            <p style={styles.desc}>
              导出您的全部个人数据(JSON 文件),包含账号信息、API Keys、文档、任务、审计日志。
            </p>
            <button style={styles.primaryBtn} onClick={handleExport}>
              📦 导出我的数据
            </button>
          </div>
        </section>

        {/* 注销状态 */}
        {isPendingDeletion && status && (
          <section style={styles.section}>
            <h2 style={styles.sectionTitle}>注销状态</h2>
            <div style={{ ...styles.card, borderColor: 'rgba(251, 191, 36, 0.3)' }}>
              <div style={styles.warningBox}>
                <span style={styles.warningIcon}>⚠</span>
                <div>
                  <div style={styles.warningTitle}>账号正在注销流程中</div>
                  <div style={styles.warningDesc}>
                    将于 {status.hard_delete_at?.slice(0, 10)} 永久删除
                    (剩余 {status.remaining_days} 天)
                  </div>
                </div>
              </div>
              <button style={styles.primaryBtn} onClick={handleCancelDeletion}>
                撤销注销
              </button>
            </div>
          </section>
        )}

        {/* 账号注销 */}
        {!isPendingDeletion && (
          <section style={styles.section}>
            <h2 style={styles.sectionTitle}>注销账号</h2>
            <div style={{ ...styles.card, borderColor: 'rgba(239, 68, 68, 0.2)' }}>
              <p style={styles.desc}>
                注销后账号将立即禁用登录,数据保留 30 天后永久删除。
                期间您可登录撤销注销请求。
              </p>
              {!confirmDelete ? (
                <button
                  style={styles.dangerBtn}
                  onClick={() => setConfirmDelete(true)}
                >
                  申请注销账号
                </button>
              ) : (
                <div style={styles.confirmBox}>
                  <p style={styles.confirmText}>
                    确认要注销账号吗?此操作将立即禁用您的登录。
                  </p>
                  <div style={styles.confirmBtns}>
                    <button style={styles.cancelBtn} onClick={() => setConfirmDelete(false)}>
                      取消
                    </button>
                    <button style={styles.dangerBtn} onClick={handleDeleteAccount}>
                      确认注销
                    </button>
                  </div>
                </div>
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function Row({ label, value, hint }: { label: string; value?: string; hint?: string }) {
  return (
    <div style={styles.row}>
      <span style={styles.rowLabel}>{label}</span>
      <div style={styles.rowValue}>
        <span>{value || '-'}</span>
        {hint && <span style={styles.rowHint}>{hint}</span>}
      </div>
    </div>
  );
}

const COLORS = {
  bg: '#0a0f1e',
  surface: '#0f172a',
  surface2: '#1e293b',
  border: 'rgba(148, 163, 184, 0.1)',
  text: '#e2e8f0',
  textMuted: '#94a3b8',
  primary: '#6366f1',
  danger: '#ef4444',
  warning: '#fbbf24',
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    background: COLORS.bg,
    color: COLORS.text,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 16px',
    height: 44,
    background: COLORS.surface,
    borderBottom: `1px solid ${COLORS.border}`,
    flexShrink: 0,
  },
  backBtn: {
    background: 'transparent',
    border: 'none',
    color: COLORS.textMuted,
    cursor: 'pointer',
    fontSize: 13,
  },
  title: {
    fontSize: 14,
    fontWeight: 600,
  },
  userBox: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  },
  avatar: {
    width: 24,
    height: 24,
    borderRadius: '50%',
    background: `linear-gradient(135deg, ${COLORS.primary}, #8b5cf6)`,
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 11,
    fontWeight: 600,
  },
  logoutBtn: {
    background: 'transparent',
    border: `1px solid ${COLORS.border}`,
    color: COLORS.textMuted,
    padding: '4px 10px',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 11,
  },
  content: {
    flex: 1,
    overflowY: 'auto',
    padding: '32px 24px',
    maxWidth: 720,
    width: '100%',
    alignSelf: 'center',
  },
  section: {
    marginBottom: 32,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: COLORS.textMuted,
    marginBottom: 12,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  card: {
    background: COLORS.surface,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 8,
    padding: 20,
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '10px 0',
    borderBottom: `1px solid ${COLORS.border}`,
    fontSize: 13,
  },
  rowLabel: {
    color: COLORS.textMuted,
  },
  rowValue: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  rowHint: {
    fontSize: 10,
    color: COLORS.textMuted,
    background: COLORS.surface2,
    padding: '1px 6px',
    borderRadius: 3,
  },
  desc: {
    fontSize: 12,
    color: COLORS.textMuted,
    lineHeight: 1.6,
    marginBottom: 16,
  },
  primaryBtn: {
    background: COLORS.primary,
    color: '#fff',
    border: 'none',
    padding: '8px 16px',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 500,
  },
  dangerBtn: {
    background: COLORS.danger,
    color: '#fff',
    border: 'none',
    padding: '8px 16px',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 500,
  },
  cancelBtn: {
    background: 'transparent',
    color: COLORS.textMuted,
    border: `1px solid ${COLORS.border}`,
    padding: '8px 16px',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 12,
  },
  warningBox: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: 12,
    background: 'rgba(251, 191, 36, 0.05)',
    borderRadius: 6,
    marginBottom: 16,
  },
  warningIcon: {
    fontSize: 20,
    color: COLORS.warning,
  },
  warningTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: COLORS.warning,
  },
  warningDesc: {
    fontSize: 11,
    color: COLORS.textMuted,
    marginTop: 2,
  },
  confirmBox: {
    marginTop: 12,
  },
  confirmText: {
    fontSize: 12,
    color: COLORS.text,
    marginBottom: 12,
  },
  confirmBtns: {
    display: 'flex',
    gap: 8,
  },
  loading: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: COLORS.textMuted,
    fontSize: 13,
  },
  error: {
    color: COLORS.danger,
    fontSize: 13,
    textAlign: 'center',
    marginTop: 24,
  },
  btn: {
    background: COLORS.primary,
    color: '#fff',
    border: 'none',
    padding: '6px 14px',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 12,
    margin: '12px auto 0',
    display: 'block',
  },
};
