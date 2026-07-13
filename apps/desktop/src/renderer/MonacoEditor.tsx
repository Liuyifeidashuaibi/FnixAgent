/**
 * MonacoEditor.tsx — Monaco Editor 包装组件
 *
 * 功能：
 *   - 根据文件扩展名自动检测语言（语法高亮）
 *   - 自定义浅色主题（Cursor/Codex 风格：白底 #ffffff，文字 #28282c）
 *   - 行号、缩略图(minimap)、括号匹配
 *   - 对非可编辑文件（图片、二进制）自动启用只读模式
 *   - Ctrl+S 保存支持
 *   - Diff 编辑器模式（传入 original 时启用）
 */
import { useCallback } from 'react';
import Editor, { DiffEditor, type OnMount } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';

export interface MonacoEditorProps {
  /** 当前编辑器内容 */
  value: string;
  /** 内容变更回调 */
  onChange?: (value: string) => void;
  /** 语言标识（如不传则根据 filePath 自动检测） */
  language?: string;
  /** 是否只读 */
  readOnly?: boolean;
  /** 文件路径（用于自动检测语言和是否可编辑） */
  filePath?: string;
  /** Ctrl+S 保存回调 */
  onSave?: () => void;
  /** 原始内容（传入后启用 Diff 编辑器模式） */
  original?: string;
}

// ── 主题 CSS 变量 ──
const CSS = {
  '--bg-primary': '#ffffff',
  '--bg-secondary': '#f4f5f7',
  '--text-primary': '#28282c',
  '--font-mono': "'JetBrains Mono', Menlo, monospace",
} as const;

// ── 语言检测 ──
function detectLanguage(filePath: string): string {
  const ext = (filePath.split('.').pop() || '').toLowerCase();
  const langMap: Record<string, string> = {
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    mjs: 'javascript',
    cjs: 'javascript',
    py: 'python',
    pyi: 'python',
    pyx: 'python',
    json: 'json',
    jsonc: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    md: 'markdown',
    mdx: 'markdown',
    html: 'html',
    htm: 'html',
    css: 'css',
    scss: 'scss',
    less: 'less',
    sql: 'sql',
    graphql: 'graphql',
    gql: 'graphql',
    sh: 'shell',
    bash: 'shell',
    zsh: 'shell',
    bat: 'bat',
    ps1: 'powershell',
    xml: 'xml',
    svg: 'xml',
    toml: 'ini',
    ini: 'ini',
    env: 'plaintext',
    txt: 'plaintext',
    gitignore: 'plaintext',
    dockerfile: 'dockerfile',
    makefile: 'makefile',
    rs: 'rust',
    go: 'go',
    java: 'java',
    c: 'c',
    cpp: 'cpp',
    h: 'c',
    hpp: 'cpp',
    rb: 'ruby',
    php: 'php',
    swift: 'swift',
    kt: 'kotlin',
    scala: 'scala',
    r: 'r',
    lua: 'lua',
    pl: 'perl',
    ex: 'elixir',
    exs: 'elixir',
    elm: 'elm',
    vue: 'html',
    svelte: 'html',
    astro: 'html',
    prisma: 'graphql',
    cs: 'csharp',
    vb: 'vb',
    fs: 'fsharp',
    fsx: 'fsharp',
    dart: 'dart',
    proto: 'protobuf',
    cmake: 'cmake',
    coffee: 'coffeescript',
    pug: 'pug',
    jade: 'pug',
    styl: 'stylus',
    stylus: 'stylus',
    sass: 'sass',
    handlebars: 'handlebars',
    hbs: 'handlebars',
    twig: 'twig',
    ejs: 'html',
    erb: 'ruby',
    ml: 'ocaml',
    mli: 'ocaml',
    hs: 'haskell',
    lhs: 'haskell',
    clj: 'clojure',
    cljs: 'clojure',
    cljc: 'clojure',
    edn: 'clojure',
    groovy: 'groovy',
    tf: 'hcl',
    tfvars: 'hcl',
    hcl: 'hcl',
    nix: 'nix',
    zig: 'zig',
    nim: 'nim',
    cr: 'crystal',
    pony: 'pony',
    sol: 'solidity',
    rkt: 'scheme',
    scm: 'scheme',
    ss: 'scheme',
    v: 'verilog',
    vhdl: 'vhdl',
    sv: 'systemverilog',
    tex: 'latex',
    sty: 'latex',
    bib: 'bibtex',
    rmd: 'r',
    rnw: 'r',
    ipynb: 'json',
    properties: 'ini',
    cfg: 'ini',
    conf: 'ini',
    log: 'plaintext',
    lock: 'plaintext',
    lockb: 'plaintext',
    csproj: 'xml',
    vbproj: 'xml',
    fsproj: 'xml',
    sln: 'plaintext',
    xaml: 'xml',
    axml: 'xml',
    resx: 'xml',
    plist: 'xml',
    gradle: 'groovy',
    sbt: 'scala',
    cabal: 'haskell',
    opam: 'ocaml',
    dune: 'ocaml',
    cargo: 'toml',
    'cargo.lock': 'toml',
    'docker-compose': 'yaml',
    'docker-compose.yml': 'yaml',
    'docker-compose.yaml': 'yaml',
    'docker-compose.override': 'yaml',
    'docker-compose.override.yml': 'yaml',
    'docker-compose.override.yaml': 'yaml',
  };
  return langMap[ext] || 'plaintext';
}

// ── 非可编辑文件检测（图片、二进制等） ──
function isNonEditableFile(filePath: string): boolean {
  const ext = (filePath.split('.').pop() || '').toLowerCase();
  const nonEditable: Set<string> = new Set([
    // 图片
    'png', 'jpg', 'jpeg', 'gif', 'bmp', 'ico', 'webp', 'tiff', 'tif', 'svg',
    'heic', 'heif', 'avif', 'raw', 'nef', 'cr2', 'dng',
    // 二进制
    'pdf', 'zip', 'tar', 'gz', 'bz2', 'xz', '7z', 'rar', 'lz', 'lz4', 'zst',
    'exe', 'dll', 'so', 'dylib', 'wasm', 'bin', 'dat', 'class', 'jar', 'war',
    'ear', 'apk', 'ipa', 'aab', 'app', 'msi', 'deb', 'rpm', 'snap', 'flatpak',
    'o', 'obj', 'lib', 'a', 'out', 'elf', 'ko', 'sys', 'drv', 'vxd',
    'ttf', 'otf', 'woff', 'woff2', 'eot',
    'mp3', 'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm', 'ogg', 'wav',
    'flac', 'aac', 'wma', 'm4a', 'opus',
    'ico', 'icns', 'cur',
    'db', 'sqlite', 'sqlite3', 'mdb', 'accdb', 'frm', 'ibd',
    'pyc', 'pyo', 'pyd', 'pyc', 'rbc', 'class',
    'pak', 'asset', 'bundle', 'res', 'resources',
    'map', 'tsbuildinfo',
    'vsix', 'asar',
    'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp',
    'epub', 'mobi',
    'psd', 'ai', 'sketch', 'fig', 'xd', 'cdr',
    '3ds', 'blend', 'fbx', 'obj', 'stl', 'glb', 'gltf',
    'iso', 'img', 'dmg', 'vhd', 'vmdk', 'qcow2',
    'bak', 'tmp', 'temp', 'cache',
    'npy', 'npz', 'pkl', 'joblib', 'h5', 'hdf5', 'pb', 'tflite', 'onnx',
    'min.js', 'min.css', 'min.map',
  ]);
  return nonEditable.has(ext);
}

// ── 自定义 Monaco 浅色主题名称 ──
const THEME_NAME = 'officeagent-light';

// ── 通用编辑器配置 ──
const commonOptions: editor.IStandaloneEditorConstructionOptions = {
  fontSize: 14,
  fontFamily: CSS['--font-mono'],
  minimap: { enabled: true },
  lineNumbers: 'on' as const,
  wordWrap: 'on' as const,
  tabSize: 2,
  renderLineHighlight: 'line' as const,
  scrollBeyondLastLine: false,
  automaticLayout: true,
  padding: { top: 8 },
  folding: true,
  glyphMargin: false,
  lineDecorationsWidth: 8,
  lineNumbersMinChars: 3,
  matchBrackets: 'always' as const,
  autoClosingBrackets: 'always' as const,
  autoClosingQuotes: 'always' as const,
  bracketPairColorization: { enabled: true },
};

export function MonacoEditor({
  value,
  onChange,
  language,
  readOnly: readOnlyProp,
  filePath,
  onSave,
  original,
}: MonacoEditorProps) {
  const isDiffMode = original !== undefined;

  // 自动检测语言
  const resolvedLanguage =
    language || (filePath ? detectLanguage(filePath) : 'plaintext');

  // 自动检测只读
  const resolvedReadOnly =
    readOnlyProp ?? (filePath ? isNonEditableFile(filePath) : false);

  // 注册自定义主题
  const handleBeforeMount = useCallback(
    (monaco: typeof import('monaco-editor')) => {
      monaco.editor.defineTheme(THEME_NAME, {
        base: 'vs',
        inherit: true,
        rules: [
          { token: 'comment', foreground: '6b7280', fontStyle: 'italic' },
          { token: 'keyword', foreground: '0066b8' },
          { token: 'string', foreground: '059669' },
          { token: 'number', foreground: 'd97706' },
          { token: 'type', foreground: '7c3aed' },
          { token: 'function', foreground: '2563eb' },
          { token: 'variable', foreground: '28282c' },
          { token: 'identifier', foreground: '28282c' },
          { token: 'delimiter', foreground: '6b7280' },
          { token: 'tag', foreground: '0066b8' },
          { token: 'attribute.name', foreground: 'd97706' },
          { token: 'attribute.value', foreground: '059669' },
        ],
        colors: {
          'editor.background': '#ffffff',
          'editor.foreground': '#28282c',
          'editor.lineHighlightBackground': '#f4f5f7',
          'editor.selectionBackground': 'rgba(0, 102, 184, 0.15)',
          'editor.inactiveSelectionBackground': 'rgba(0, 102, 184, 0.08)',
          'editorLineNumber.foreground': '#9ca3af',
          'editorLineNumber.activeForeground': '#28282c',
          'editorCursor.foreground': '#0066b8',
          'editorBracketMatch.background': 'rgba(0, 102, 184, 0.12)',
          'editorBracketMatch.border': '#0066b8',
          'editorWidget.background': '#ffffff',
          'editorWidget.border': '#e4e4e7',
          'editorSuggestWidget.background': '#ffffff',
          'editorSuggestWidget.border': '#e4e4e7',
          'editorSuggestWidget.selectedBackground': 'rgba(0, 102, 184, 0.08)',
          'input.background': '#f4f5f7',
          'input.border': '#e4e4e7',
          'focusBorder': '#0066b8',
          'minimap.background': '#fafbfc',
          'scrollbar.shadow': '#00000000',
          'scrollbarSlider.background': 'rgba(0, 0, 0, 0.1)',
          'scrollbarSlider.hoverBackground': 'rgba(0, 0, 0, 0.18)',
          'scrollbarSlider.activeBackground': 'rgba(0, 0, 0, 0.25)',
        },
      });
    },
    [],
  );

  // Editor 挂载回调 — 注册 Ctrl+S
  const handleEditorMount: OnMount = useCallback(
    (editor, _monaco) => {
      if (onSave) {
        editor.addCommand(
          // monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS
          2048 | 49,
          () => onSave(),
        );
      }
    },
    [onSave],
  );

  // Diff 编辑器模式
  if (isDiffMode) {
    return (
      <DiffEditor
        height="100%"
        theme={THEME_NAME}
        original={original}
        modified={value}
        language={resolvedLanguage}
        beforeMount={handleBeforeMount}
        options={{
          ...commonOptions,
          readOnly: resolvedReadOnly,
          renderSideBySide: true,
          minimap: { enabled: false },
        }}
      />
    );
  }

  // 普通编辑器模式
  return (
    <Editor
      height="100%"
      theme={THEME_NAME}
      value={value}
      onChange={(v) => onChange?.(v ?? '')}
      language={resolvedLanguage}
      onMount={handleEditorMount}
      beforeMount={handleBeforeMount}
      options={{
        ...commonOptions,
        readOnly: resolvedReadOnly,
      }}
    />
  );
}