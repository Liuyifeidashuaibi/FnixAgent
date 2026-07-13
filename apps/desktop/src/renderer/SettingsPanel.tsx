/**
 * SettingsPanel — 全屏设置面板
 *
 * 左侧 200px 分类导航栏 + 右侧内容区域。
 * 设置持久化到 localStorage，并动态应用 CSS 变量。
 */
import React, { useState, useCallback, useEffect } from 'react';

/* ================================================
   Types
   ================================================ */

type SettingsCategory = 'general' | 'editor' | 'ai' | 'git' | 'appearance' | 'about';

interface Settings {
  language: string;
  theme: string;
  fontSize: number;
  tabSize: number;
  wordWrap: boolean;
  minimap: boolean;
  lineNumbers: boolean;
  llmProvider: string;
  apiKey: string;
  model: string;
  temperature: number;
  gitAuthorName: string;
  gitAuthorEmail: string;
  autoCommit: boolean;
  accentColor: string;
  fontFamily: string;
  sidebarWidth: number;
}

interface SettingsPanelProps {
  onBack: () => void;
}

/* ================================================
   Constants
   ================================================ */

const STORAGE_KEY = 'fnixagent-settings';

const DEFAULT_SETTINGS: Settings = {
  language: 'zh-CN',
  theme: 'light',
  fontSize: 14,
  tabSize: 2,
  wordWrap: true,
  minimap: true,
  lineNumbers: true,
  llmProvider: 'openai',
  apiKey: '',
  model: 'gpt-4',
  temperature: 0.7,
  gitAuthorName: '',
  gitAuthorEmail: '',
  autoCommit: false,
  accentColor: '#0066b8',
  fontFamily: "'Inter', -apple-system, sans-serif",
  sidebarWidth: 260,
};

const CATEGORIES: { id: SettingsCategory; label: string }[] = [
  { id: 'general', label: '常规' },
  { id: 'editor', label: '编辑器' },
  { id: 'ai', label: 'AI' },
  { id: 'git', label: 'Git' },
  { id: 'appearance', label: '外观' },
  { id: 'about', label: '关于' },
];

const LLM_PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'glm', label: 'GLM' },
  { value: 'qwen', label: 'Qwen' },
];

const MODELS: Record<string, string[]> = {
  openai: ['gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo'],
  glm: ['glm-4', 'glm-3-turbo'],
  qwen: ['qwen-max', 'qwen-plus', 'qwen-turbo'],
};

const FONT_FAMILIES = [
  { value: "'Inter', -apple-system, sans-serif", label: 'Inter' },
  { value: "'JetBrains Mono', monospace", label: 'JetBrains Mono' },
  { value: "'PingFang SC', 'Microsoft YaHei', sans-serif", label: '苹方 / 微软雅黑' },
  { value: "'SF Mono', Menlo, Consolas, monospace", label: 'SF Mono' },
];

/* ================================================
   Helpers
   ================================================ */

function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
    }
  } catch {
    /* ignore parse errors */
  }
  return { ...DEFAULT_SETTINGS };
}

function saveSettings(settings: Settings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    /* ignore storage errors */
  }
}

function applyCssVariables(settings: Settings): void {
  const root = document.documentElement;
  root.style.setProperty('--accent', settings.accentColor);
  root.style.setProperty('--font-sans', settings.fontFamily);
  root.style.setProperty('--sidebar-width', `${settings.sidebarWidth}px`);
  if (settings.theme === 'dark') {
    root.style.setProperty('--bg-primary', '#1e1e2e');
    root.style.setProperty('--bg-secondary', '#252536');
    root.style.setProperty('--bg-tertiary', '#2d2d44');
    root.style.setProperty('--text-primary', '#e0e0e0');
    root.style.setProperty('--text-secondary', '#a0a0b0');
    root.style.setProperty('--text-tertiary', '#707088');
    root.style.setProperty('--border-color', '#3a3a50');
  } else {
    root.style.setProperty('--bg-primary', '#ffffff');
    root.style.setProperty('--bg-secondary', '#f4f5f7');
    root.style.setProperty('--bg-tertiary', '#ebecee');
    root.style.setProperty('--text-primary', '#28282c');
    root.style.setProperty('--text-secondary', '#6b7280');
    root.style.setProperty('--text-tertiary', '#9ca3af');
    root.style.setProperty('--border-color', '#e4e4e7');
  }
}

/* ================================================
   Sub-components
   ================================================ */

const GeneralSettings: React.FC<{
  settings: Settings;
  onChange: (patch: Partial<Settings>) => void;
}> = ({ settings, onChange }) => (
  <div style={styles.contentInner}>
    <h2 style={styles.sectionTitle}>常规设置</h2>

    <div style={styles.field}>
      <label style={styles.label}>语言</label>
      <select
        style={styles.select}
        value={settings.language}
        onChange={(e) => onChange({ language: e.target.value })}
      >
        <option value="zh-CN">简体中文</option>
        <option value="en">English</option>
      </select>
    </div>

    <div style={styles.field}>
      <label style={styles.label}>主题</label>
      <select
        style={styles.select}
        value={settings.theme}
        onChange={(e) => onChange({ theme: e.target.value })}
      >
        <option value="light">浅色</option>
        <option value="dark">深色</option>
      </select>
    </div>

    <div style={styles.field}>
      <label style={styles.label}>
        字体大小：{settings.fontSize}px
      </label>
      <input
        type="range"
        style={styles.slider}
        min={10}
        max={24}
        step={1}
        value={settings.fontSize}
        onChange={(e) => onChange({ fontSize: Number(e.target.value) })}
      />
    </div>
  </div>
);

const EditorSettings: React.FC<{
  settings: Settings;
  onChange: (patch: Partial<Settings>) => void;
}> = ({ settings, onChange }) => (
  <div style={styles.contentInner}>
    <h2 style={styles.sectionTitle}>编辑器设置</h2>

    <div style={styles.field}>
      <label style={styles.label}>Tab 大小</label>
      <select
        style={styles.select}
        value={settings.tabSize}
        onChange={(e) => onChange({ tabSize: Number(e.target.value) })}
      >
        <option value={2}>2</option>
        <option value={4}>4</option>
        <option value={8}>8</option>
      </select>
    </div>

    <div style={styles.field}>
      <label style={styles.label}>自动换行</label>
      <Toggle
        checked={settings.wordWrap}
        onChange={(v) => onChange({ wordWrap: v })}
      />
    </div>

    <div style={styles.field}>
      <label style={styles.label}>小地图</label>
      <Toggle
        checked={settings.minimap}
        onChange={(v) => onChange({ minimap: v })}
      />
    </div>

    <div style={styles.field}>
      <label style={styles.label}>行号</label>
      <Toggle
        checked={settings.lineNumbers}
        onChange={(v) => onChange({ lineNumbers: v })}
      />
    </div>
  </div>
);

const AISettings: React.FC<{
  settings: Settings;
  onChange: (patch: Partial<Settings>) => void;
}> = ({ settings, onChange }) => (
  <div style={styles.contentInner}>
    <h2 style={styles.sectionTitle}>AI 设置</h2>

    <div style={styles.field}>
      <label style={styles.label}>LLM 提供商</label>
      <select
        style={styles.select}
        value={settings.llmProvider}
        onChange={(e) => onChange({ llmProvider: e.target.value, model: MODELS[e.target.value]?.[0] ?? '' })}
      >
        {LLM_PROVIDERS.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </select>
    </div>

    <div style={styles.field}>
      <label style={styles.label}>API Key</label>
      <input
        type="password"
        style={styles.textInput}
        value={settings.apiKey}
        placeholder="输入 API Key..."
        onChange={(e) => onChange({ apiKey: e.target.value })}
      />
    </div>

    <div style={styles.field}>
      <label style={styles.label}>模型</label>
      <select
        style={styles.select}
        value={settings.model}
        onChange={(e) => onChange({ model: e.target.value })}
      >
        {(MODELS[settings.llmProvider] ?? []).map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
    </div>

    <div style={styles.field}>
      <label style={styles.label}>
        Temperature：{settings.temperature}
      </label>
      <input
        type="range"
        style={styles.slider}
        min={0}
        max={2}
        step={0.1}
        value={settings.temperature}
        onChange={(e) => onChange({ temperature: Number(e.target.value) })}
      />
    </div>
  </div>
);

const GitSettings: React.FC<{
  settings: Settings;
  onChange: (patch: Partial<Settings>) => void;
}> = ({ settings, onChange }) => (
  <div style={styles.contentInner}>
    <h2 style={styles.sectionTitle}>Git 设置</h2>

    <div style={styles.field}>
      <label style={styles.label}>作者名称</label>
      <input
        type="text"
        style={styles.textInput}
        value={settings.gitAuthorName}
        placeholder="输入 Git 用户名..."
        onChange={(e) => onChange({ gitAuthorName: e.target.value })}
      />
    </div>

    <div style={styles.field}>
      <label style={styles.label}>作者邮箱</label>
      <input
        type="email"
        style={styles.textInput}
        value={settings.gitAuthorEmail}
        placeholder="输入 Git 邮箱..."
        onChange={(e) => onChange({ gitAuthorEmail: e.target.value })}
      />
    </div>

    <div style={styles.field}>
      <label style={styles.label}>自动提交</label>
      <Toggle
        checked={settings.autoCommit}
        onChange={(v) => onChange({ autoCommit: v })}
      />
    </div>
  </div>
);

const AppearanceSettings: React.FC<{
  settings: Settings;
  onChange: (patch: Partial<Settings>) => void;
}> = ({ settings, onChange }) => (
  <div style={styles.contentInner}>
    <h2 style={styles.sectionTitle}>外观设置</h2>

    <div style={styles.field}>
      <label style={styles.label}>强调色</label>
      <div style={styles.colorRow}>
        <input
          type="color"
          style={styles.colorInput}
          value={settings.accentColor}
          onChange={(e) => onChange({ accentColor: e.target.value })}
        />
        <span style={styles.colorValue}>{settings.accentColor}</span>
      </div>
    </div>

    <div style={styles.field}>
      <label style={styles.label}>字体</label>
      <select
        style={styles.select}
        value={settings.fontFamily}
        onChange={(e) => onChange({ fontFamily: e.target.value })}
      >
        {FONT_FAMILIES.map((f) => (
          <option key={f.value} value={f.value}>
            {f.label}
          </option>
        ))}
      </select>
    </div>

    <div style={styles.field}>
      <label style={styles.label}>
        侧边栏宽度：{settings.sidebarWidth}px
      </label>
      <input
        type="range"
        style={styles.slider}
        min={200}
        max={400}
        step={10}
        value={settings.sidebarWidth}
        onChange={(e) => onChange({ sidebarWidth: Number(e.target.value) })}
      />
    </div>
  </div>
);

const AboutSettings: React.FC = () => (
  <div style={styles.contentInner}>
    <h2 style={styles.sectionTitle}>关于</h2>

    <div style={styles.field}>
      <label style={styles.label}>版本</label>
      <span style={styles.staticValue}>1.0.0</span>
    </div>

    <div style={styles.field}>
      <label style={styles.label}>许可证</label>
      <span style={styles.staticValue}>MIT</span>
    </div>

    <div style={styles.field}>
      <label style={styles.label}>GitHub</label>
      <a
        href="https://github.com/Liuyifeidashuaibi/FnixAgent"
        target="_blank"
        rel="noopener noreferrer"
        style={styles.link}
      >
        github.com/Liuyifeidashuaibi/FnixAgent
      </a>
    </div>
  </div>
);

const Toggle: React.FC<{
  checked: boolean;
  onChange: (v: boolean) => void;
}> = ({ checked, onChange }) => (
  <button
    style={{
      ...styles.toggle,
      background: checked ? 'var(--accent)' : 'var(--bg-tertiary)',
    }}
    onClick={() => onChange(!checked)}
    type="button"
  >
    <span
      style={{
        ...styles.toggleKnob,
        transform: checked ? 'translateX(18px)' : 'translateX(2px)',
      }}
    />
  </button>
);

/* ================================================
   SettingsPanel
   ================================================ */

export const SettingsPanel: React.FC<SettingsPanelProps> = ({ onBack }) => {
  const [activeCategory, setActiveCategory] = useState<SettingsCategory>('general');
  const [settings, setSettings] = useState<Settings>(loadSettings);

  /* 应用 CSS 变量 */
  useEffect(() => {
    applyCssVariables(settings);
  }, [settings]);

  /* 持久化 */
  useEffect(() => {
    saveSettings(settings);
  }, [settings]);

  const handleChange = useCallback((patch: Partial<Settings>) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  }, []);

  const handleReset = useCallback(() => {
    setSettings({ ...DEFAULT_SETTINGS });
  }, []);

  const renderContent = () => {
    switch (activeCategory) {
      case 'general':
        return <GeneralSettings settings={settings} onChange={handleChange} />;
      case 'editor':
        return <EditorSettings settings={settings} onChange={handleChange} />;
      case 'ai':
        return <AISettings settings={settings} onChange={handleChange} />;
      case 'git':
        return <GitSettings settings={settings} onChange={handleChange} />;
      case 'appearance':
        return <AppearanceSettings settings={settings} onChange={handleChange} />;
      case 'about':
        return <AboutSettings />;
    }
  };

  return (
    <div style={styles.container}>
      {/* 侧边栏导航 */}
      <div style={styles.sidebar}>
        <div style={styles.sidebarHeader}>
          <button style={styles.backBtn} onClick={onBack} type="button">
            ← 返回
          </button>
        </div>
        <nav style={styles.nav}>
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              style={{
                ...styles.navItem,
                background: activeCategory === cat.id ? 'var(--accent-light)' : 'transparent',
                color: activeCategory === cat.id ? 'var(--accent)' : 'var(--text-primary)',
                fontWeight: activeCategory === cat.id ? 500 : 400,
              }}
              onClick={() => setActiveCategory(cat.id)}
              type="button"
            >
              {cat.label}
            </button>
          ))}
        </nav>
      </div>

      {/* 内容区域 */}
      <div style={styles.content}>
        {renderContent()}
        <div style={styles.footer}>
          <button style={styles.resetBtn} onClick={handleReset} type="button">
            恢复默认设置
          </button>
        </div>
      </div>
    </div>
  );
};

/* ================================================
   样式
   ================================================ */

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flex: 1,
    height: '100%',
    overflow: 'hidden',
  },
  sidebar: {
    width: 200,
    flexShrink: 0,
    background: 'var(--bg-secondary)',
    borderRight: '1px solid var(--border-color)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  sidebarHeader: {
    padding: '12px 12px 8px',
  },
  backBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    padding: '4px 10px',
    background: 'transparent',
    color: 'var(--text-secondary)',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 12,
    transition: 'background 0.12s, color 0.12s',
  },
  nav: {
    flex: 1,
    padding: '4px 8px',
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    overflowY: 'auto',
  },
  navItem: {
    display: 'block',
    width: '100%',
    padding: '8px 12px',
    border: 'none',
    borderRadius: 6,
    fontSize: 13,
    cursor: 'pointer',
    textAlign: 'left' as const,
    transition: 'background 0.12s, color 0.12s',
  },
  content: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  contentInner: {
    flex: 1,
    padding: '24px 32px',
    overflowY: 'auto',
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: 20,
    marginTop: 0,
  },
  field: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 0',
    borderBottom: '1px solid var(--border-color)',
    gap: 16,
  },
  label: {
    fontSize: 13,
    color: 'var(--text-primary)',
    flexShrink: 0,
  },
  select: {
    padding: '6px 10px',
    border: '1px solid var(--border-color)',
    borderRadius: 6,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 13,
    outline: 'none',
    cursor: 'pointer',
    minWidth: 160,
  },
  textInput: {
    padding: '6px 10px',
    border: '1px solid var(--border-color)',
    borderRadius: 6,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 13,
    outline: 'none',
    minWidth: 240,
  },
  slider: {
    width: 160,
    cursor: 'pointer',
    accentColor: 'var(--accent)',
  },
  toggle: {
    position: 'relative' as const,
    width: 40,
    height: 22,
    borderRadius: 11,
    border: 'none',
    cursor: 'pointer',
    padding: 0,
    transition: 'background 0.15s',
    flexShrink: 0,
  },
  toggleKnob: {
    display: 'block',
    width: 18,
    height: 18,
    borderRadius: '50%',
    background: '#fff',
    transition: 'transform 0.15s',
    boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
  },
  colorRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  },
  colorInput: {
    width: 32,
    height: 32,
    border: '1px solid var(--border-color)',
    borderRadius: 6,
    padding: 2,
    cursor: 'pointer',
    background: 'var(--bg-primary)',
  },
  colorValue: {
    fontSize: 13,
    color: 'var(--text-secondary)',
    fontFamily: 'var(--font-mono)',
  },
  staticValue: {
    fontSize: 13,
    color: 'var(--text-secondary)',
  },
  link: {
    fontSize: 13,
    color: 'var(--accent)',
    textDecoration: 'none',
  },
  footer: {
    padding: '12px 32px',
    borderTop: '1px solid var(--border-color)',
    flexShrink: 0,
  },
  resetBtn: {
    padding: '6px 16px',
    background: 'transparent',
    color: 'var(--text-secondary)',
    border: '1px solid var(--border-color)',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 12,
    transition: 'background 0.12s, color 0.12s',
  },
};