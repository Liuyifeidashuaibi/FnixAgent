/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * SkillManager — 技能管理面板（技能管理面板）
 * ============================================================
 * 两个 tab：
 *   - 静态技能（.fnix/skills/*.md）：用户手写的 Markdown 技能包
 *   - 自动捕获（SkillMarket 动态技能）：HERA 自动捕获的成功轨迹
 *
 * 静态技能支持：
 *   - 列表展示：name / description / triggers / priority / enabled 开关
 *   - 新建/编辑：内置 Markdown 编辑器 + frontmatter 字段表单
 *   - 删除
 *   - 启用/禁用（影响 system prompt 注入）
 *
 * 自动捕获支持：
 *   - 列表展示：name / status / install_count / rating
 *   - 审核流程：submit → approve / deprecate
 */

import { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Edit3,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  deleteHarnessSkill,
  fetchHarnessSkills,
  fetchSkillsList,
  toggleHarnessSkill,
  writeHarnessSkill,
  type FnixSkillEntry,
  type FnixSkillsList,
  type HarnessSkill,
} from "../../lib/fnixBridge";

interface Props {
  workspace: string;
  onClose: () => void;
}

type Tab = "static" | "captured";

export function SkillManager({ workspace, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("static");
  const [staticSkills, setStaticSkills] = useState<HarnessSkill[]>([]);
  const [capturedEntries, setCapturedEntries] = useState<FnixSkillEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingSkill, setEditingSkill] = useState<HarnessSkill | null>(null);
  const [creating, setCreating] = useState(false);

  const refreshStatic = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const list = await fetchHarnessSkills(workspace);
      setStaticSkills(list?.skills ?? []);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [workspace]);

  const refreshCaptured = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const list: FnixSkillsList | null = await fetchSkillsList();
      setCapturedEntries(list?.entries ?? []);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "static") void refreshStatic();
    else void refreshCaptured();
  }, [tab, refreshStatic, refreshCaptured]);

  // 自动捕获为空时，回退到静态技能 tab（避免用户看到空列表困惑）
  useEffect(() => {
    if (tab === "captured" && capturedEntries.length === 0) {
      setTab("static");
    }
  }, [tab, capturedEntries.length]);

  const handleToggle = async (skill: HarnessSkill) => {
    setBusy(true);
    setError(null);
    try {
      const res = await toggleHarnessSkill(workspace, skill.name, !skill.enabled);
      if (!res.ok) {
        setError(res.error || "切换失败");
      } else {
        await refreshStatic();
      }
    } finally {
      setBusy(false);
    }
  };

  const [deletingPath, setDeletingPath] = useState<string | null>(null);

  const handleDelete = async (skill: HarnessSkill) => {
    setDeletingPath(skill.path);
  };

  const confirmDelete = async (skill: HarnessSkill) => {
    setBusy(true);
    setError(null);
    setDeletingPath(null);
    try {
      const res = await deleteHarnessSkill(workspace, skill.name);
      if (!res.ok) {
        setError(res.error || "删除失败");
      } else {
        await refreshStatic();
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="fnix-skill-mgr" role="dialog" aria-label="技能管理">
      <header className="fnix-skill-mgr-head">
        <div className="fnix-skill-mgr-title">
          <BookOpen size={15} />
          <span>技能管理</span>
        </div>
        <div className="fnix-skill-mgr-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "static"}
            className={`fnix-skill-mgr-tab${tab === "static" ? " on" : ""}`}
            onClick={() => setTab("static")}
          >
            静态技能（{staticSkills.length}）
          </button>
          {capturedEntries.length > 0 && (
            <button
              type="button"
              role="tab"
              aria-selected={tab === "captured"}
              className={`fnix-skill-mgr-tab${tab === "captured" ? " on" : ""}`}
              onClick={() => setTab("captured")}
            >
              自动捕获（{capturedEntries.length}）
            </button>
          )}
        </div>
        <div className="fnix-skill-mgr-actions">
          <button
            type="button"
            className="fnix-ibtn sm"
            title="刷新"
            onClick={() => (tab === "static" ? void refreshStatic() : void refreshCaptured())}
          >
            <RefreshCw size={13} className={busy ? "spinning" : ""} />
          </button>
          {tab === "static" && (
            <button
              type="button"
              className="fnix-ibtn sm"
              title="新建技能"
              onClick={() => {
                setEditingSkill(null);
                setCreating(true);
              }}
            >
              <Plus size={13} />
            </button>
          )}
          <button type="button" className="fnix-ibtn sm" title="关闭" onClick={onClose}>
            <X size={13} />
          </button>
        </div>
      </header>

      {error && (
        <div className="fnix-skill-mgr-error" role="alert">
          {error}
        </div>
      )}

      <div className="fnix-skill-mgr-body">
        {tab === "static" ? (
          <StaticSkillsList
            skills={staticSkills}
            onToggle={handleToggle}
            onEdit={(s) => {
              setEditingSkill(s);
              setCreating(false);
            }}
            onDelete={handleDelete}
            onConfirmDelete={confirmDelete}
            onCancelDelete={() => setDeletingPath(null)}
            deletingPath={deletingPath}
            busy={busy}
          />
        ) : (
          <CapturedSkillsList entries={capturedEntries} />
        )}
      </div>

      {(creating || editingSkill) && (
        <SkillEditor
          skill={editingSkill}
          workspace={workspace}
          onClose={() => {
            setEditingSkill(null);
            setCreating(false);
          }}
          onSaved={async () => {
            setEditingSkill(null);
            setCreating(false);
            await refreshStatic();
          }}
        />
      )}
    </aside>
  );
}

// ---------------------------------------------------------------------------
// 静态技能列表
// ---------------------------------------------------------------------------

function StaticSkillsList({
  skills,
  onToggle,
  onEdit,
  onDelete,
  onConfirmDelete,
  onCancelDelete,
  deletingPath,
  busy,
}: {
  skills: HarnessSkill[];
  onToggle: (s: HarnessSkill) => void;
  onEdit: (s: HarnessSkill) => void;
  onDelete: (s: HarnessSkill) => void;
  onConfirmDelete: (s: HarnessSkill) => void;
  onCancelDelete: () => void;
  deletingPath: string | null;
  busy: boolean;
}) {
  if (skills.length === 0) {
    return (
      <div className="fnix-skill-empty">
        <BookOpen size={28} />
        <p>当前 workspace 暂无静态技能</p>
        <p className="dim">点击右上角 + 新建技能，或手动在 .fnix/skills/ 下创建 .md 文件</p>
      </div>
    );
  }
  return (
    <ul className="fnix-skill-list">
      {skills.map((s) => (
        <li key={s.path} className={`fnix-skill-card${s.enabled ? "" : " disabled"}`}>
          <div className="fnix-skill-card-head">
            <span className="fnix-skill-name">{s.name}</span>
            <span className={`fnix-skill-priority priority-${s.priority}`}>{s.priority}</span>
            <label className="fnix-skill-toggle" title={s.enabled ? "已启用" : "已禁用"}>
              <input
                type="checkbox"
                checked={s.enabled}
                disabled={busy}
                onChange={() => onToggle(s)}
              />
              <span className="fnix-skill-toggle-track">
                <span className="fnix-skill-toggle-thumb" />
              </span>
            </label>
          </div>
          {s.description && <p className="fnix-skill-desc">{s.description}</p>}
          {s.triggers.length > 0 && (
            <div className="fnix-skill-triggers">
              {s.triggers.slice(0, 6).map((t, i) => (
                <span key={i} className="fnix-skill-trigger-chip">{t}</span>
              ))}
              {s.triggers.length > 6 && <span className="dim">+{s.triggers.length - 6}</span>}
            </div>
          )}
          {deletingPath === s.path ? (
            <div className="fnix-skill-confirm-delete">
              <span>确定删除「{s.name}」？</span>
              <button
                type="button"
                className="fnix-ibtn sm danger"
                onClick={() => onConfirmDelete(s)}
                disabled={busy}
              >
                <Check size={11} /> 删除
              </button>
              <button type="button" className="fnix-ibtn sm" onClick={onCancelDelete} disabled={busy}>
                取消
              </button>
            </div>
          ) : (
            <div className="fnix-skill-card-actions">
              <button type="button" className="fnix-ibtn sm" onClick={() => onEdit(s)} title="编辑">
                <Edit3 size={11} />
              </button>
              <button
                type="button"
                className="fnix-ibtn sm danger"
                onClick={() => onDelete(s)}
                title="删除"
                disabled={busy}
              >
                <Trash2 size={11} />
              </button>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// 自动捕获技能列表（SkillMarket 动态技能）
// ---------------------------------------------------------------------------

function CapturedSkillsList({ entries }: { entries: FnixSkillEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="fnix-skill-empty">
        <Sparkles size={28} />
        <p>暂无自动捕获的技能</p>
        <p className="dim">完成 Work 模式任务后，HERA 会自动捕获成功轨迹为技能</p>
      </div>
    );
  }
  return (
    <ul className="fnix-skill-list">
      {entries.map((e) => (
        <li key={e.id} className="fnix-skill-card">
          <div className="fnix-skill-card-head">
            <span className="fnix-skill-name">{e.display_name || e.name}</span>
            {e.owner_id === "builtin" && <span className="fnix-skill-sample-tag">内置</span>}
            <span className={`fnix-skill-status status-${e.status}`}>{e.status}</span>
          </div>
          {e.description && <p className="fnix-skill-desc">{e.description}</p>}
          <div className="fnix-skill-meta">
            <span>v{e.latest_version || "—"}</span>
            <span>·</span>
            <span>{e.install_count} 次安装</span>
            {e.rating > 0 && (
              <>
                <span>·</span>
                <span>★ {e.rating.toFixed(1)}</span>
              </>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// 技能编辑器（新建/编辑共用）
// ---------------------------------------------------------------------------

function SkillEditor({
  skill,
  workspace,
  onClose,
  onSaved,
}: {
  skill: HarnessSkill | null;
  workspace: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(skill?.name || "");
  const [description, setDescription] = useState(skill?.description || "");
  const [triggers, setTriggers] = useState((skill?.triggers || []).join(", "));
  const [priority, setPriority] = useState<"high" | "normal" | "low">(skill?.priority || "normal");
  const [enabled, setEnabled] = useState(skill?.enabled ?? true);
  const [content, setContent] = useState(skill?.content || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!name.trim()) {
      setError("技能名不能为空");
      return;
    }
    if (!content.trim()) {
      setError("技能内容不能为空");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const triggersList = triggers
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const res = await writeHarnessSkill({
        workspace,
        name: name.trim(),
        content: content.trim(),
        description: description.trim(),
        triggers: triggersList,
        priority,
        enabled,
      });
      if (!res.ok) {
        setError(res.error || "保存失败");
        return;
      }
      onSaved();
    } finally {
      setBusy(false);
    }
  };

  // Ctrl+S / Cmd+S 快捷保存
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (!busy) void handleSave();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy, name, description, triggers, priority, enabled, content]);

  return (
    <div className="fnix-skill-editor-overlay" role="dialog" aria-label="技能编辑器">
      <div className="fnix-skill-editor">
        <header className="fnix-skill-editor-head">
          <span>{skill ? "编辑技能" : "新建技能"}</span>
          <button type="button" className="fnix-ibtn sm" onClick={onClose} title="关闭">
            <X size={13} />
          </button>
        </header>
        <div className="fnix-skill-editor-body">
          <label className="fnix-skill-field">
            <span className="fnix-skill-field-label">名称</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如 mbti-test-generator"
              disabled={busy || !!skill}
            />
          </label>
          <label className="fnix-skill-field">
            <span className="fnix-skill-field-label">描述</span>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="一句话描述这个技能做什么"
              disabled={busy}
            />
          </label>
          <label className="fnix-skill-field">
            <span className="fnix-skill-field-label">触发词（逗号分隔）</span>
            <input
              type="text"
              value={triggers}
              onChange={(e) => setTriggers(e.target.value)}
              placeholder="mbti, 性格测试, 人格分析"
              disabled={busy}
            />
          </label>
          <div className="fnix-skill-field-row">
            <label className="fnix-skill-field">
              <span className="fnix-skill-field-label">优先级</span>
              <select value={priority} onChange={(e) => setPriority(e.target.value as "high" | "normal" | "low")} disabled={busy}>
                <option value="high">high</option>
                <option value="normal">normal</option>
                <option value="low">low</option>
              </select>
            </label>
            <label className="fnix-skill-field fnix-skill-field-toggle">
              <span className="fnix-skill-field-label">启用</span>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                disabled={busy}
              />
            </label>
          </div>
          <label className="fnix-skill-field fnix-skill-field-content">
            <span className="fnix-skill-field-label">内容（Markdown）</span>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={"# 技能说明\n\n描述这个技能的应用场景、执行步骤、注意事项等…"}
              disabled={busy}
              rows={12}
            />
          </label>
          {error && <div className="fnix-skill-mgr-error">{error}</div>}
        </div>
        <footer className="fnix-skill-editor-foot">
          <button type="button" className="fnix-ibtn sm" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button type="button" className="fnix-ibtn sm primary" onClick={handleSave} disabled={busy} title="Ctrl+S">
            <Check size={12} />
            保存
          </button>
        </footer>
      </div>
    </div>
  );
}
