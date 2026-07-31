# FnixAgent 前端 · 世界顶级体验升级计划

> 目标：把 `apps/workbench` 前端做到世界级 —— 顶级视觉、顶级效率、顶级易用性。
> 范围：生产 shell（`src/shell/chatgpt-desktop/`，`ChatGptDesktopApp`）及其挂载的全部面板。
> 不在范围：`App.tsx`（4057 行 legacy IDE，仅 `?shell=ide&fnix_dev=1` 加载）——本次只做隔离，不投入。

---

## 0. 现状诊断（审计结论）

| # | 硬伤 | 证据 |
|---|------|------|
| 1 | 三套 token 体系并行，无单一事实源 | `shell/tokens.css`(6767行,纯浅色) / `ui/glass/tokens.css`(897行,含dark) / `styles/app/01-tokens-reset.css`(Catppuccin) |
| 2 | 暗色模式未接线 | `theme.ts` 支持 light/dark/system，但 `ChatGptDesktopApp.tsx:181` 硬编码 `themeResolved = "light"`；shell tokens.css 无 `.theme-dark` 选择器 |
| 3 | 770 处硬编码 hex 颜色散落 31 个文件 | 最多：AiFixPreviewModal(105)、ArchitectureRulesEditor(61)、TechnicalDebtDashboard(59) |
| 4 | 零动效系统 | 无动画库；29 个 CSS 文件 99 个临时 keyframes，时长 0.12s–6s 无规范 |
| 5 | 零字体策略 | `index.html` 无字体加载，全靠系统回退 |
| 6 | 生产 shell 零代码分割 | SkillManager / JobsPanel / CanvasDock / ReviewPane / OnboardingWizard 全静态导入 |
| 7 | 大量 polish CSS 投错了地方 | `polish.css`(1948行)、`16-cinematic-theme-final`(1450行) 全部服务 legacy IDE，生产 shell 未受益 |

**已有的好底子**：5 个 zustand store 选择器订阅模式健康；有 skip-link / focus-visible / reduced-motion 兜底；`useShellHotkeys` 快捷键雏形；`ui/glass/` 组件库雏形；a11y e2e 骨架（`e2e/ui/shell-a11y.spec.ts`）。

---

## Phase 0 · 护栏与度量基线（先行，保护后续所有改动）

| 任务 | 内容 | 验收 |
|------|------|------|
| 0.1 视觉回归基线 | 用现有 Playwright 对 shell 关键界面截图存档（消息流/设置/任务面板/交付布局） | baseline 截图入库，后续每 Phase 结束对比 |
| 0.2 硬编码颜色门禁 | 加一个 `scripts/check-design-tokens.mjs`：扫描 src 下新增 hex 颜色即报警 | pnpm 脚本可跑，CI 可挂 |
| 0.3 包体积基线 | `vite build` 记录当前 chunk 体积清单，作为 Phase 2 优化对照 | 基线数据写入 reports/ |

## Phase 1 · 设计系统统一（地基）

| 任务 | 内容 | 涉及文件 | 验收 |
|------|------|---------|------|
| 1.1 Tokens v2 | 在 shell tokens.css 建立完整刻度：语义色（success/warning/danger/info）、4pt 间距刻度 `--space-1..12`、圆角 `--r-xs..pill`、阴影 `--shadow-1..4`、动效 `--dur-*`/`--ease-*`、字阶 `--text-xs..2xl` | `shell/chatgpt-desktop/tokens.css` | 所有刻度 token 化，旧 `--shadow` 等别名保留兼容 |
| 1.2 真暗色 | 补齐 `.oai-root.theme-dark` 全套变量覆盖；`ChatGptDesktopApp.tsx:181` 改为 `resolveShellTheme(config.theme)` + system 时监听 matchMedia 变化 | tokens.css、ChatGptDesktopApp.tsx、theme.ts | 设置里切 light/dark/system 全局即时生效，无未接线区域 |
| 1.3 字体排印 | index.html 字体加载策略（系统栈优先 + font-display: swap）；字阶/字重/行高落到 token | index.html、tokens.css | 正文/标题/代码三级字体层级清晰 |
| 1.4 硬编码清剿 | shell 目录 hex → token 引用（codemod + 人工复核）；再推进高频面板 | shell/*.tsx | shell 目录 grep hex = 0（除 tokens.css） |
| 1.5 Glass 归一 | `ui/glass/tokens.css` 改为引用 shell 语义 token，消除第二套色板 | ui/glass/tokens.css | glass 组件随 shell 主题联动 |

## Phase 2 · 性能与效率（速度感 + 跟手感）

| 任务 | 内容 | 验收 |
|------|------|------|
| 2.1 面板级懒加载 | SkillManager / JobsPanel / ReviewPane / CanvasDock / OnboardingWizard / BenchmarkPanel → `React.lazy` + Suspense 骨架屏 | 首屏 JS 较基线减少 ≥30% |
| 2.2 大依赖分包 | vite `manualChunks` 拆分 mermaid / monaco / xyflow 等重依赖 | 首屏不加载未用面板依赖 |
| 2.3 Motion 系统 | 基于 `--dur-*`/`--ease-*` 落地：消息入场、面板开合、hover 微交互、骨架屏呼吸；统一 150–300ms 区间 | 全部交互动效走 token，60fps，reduced-motion 全兼容 |
| 2.4 ⌘K 命令面板 | 全局命令面板：会话搜索 + 命令（新建任务/打开设置/切换主题/切换模式）+ 最近项目跳转 | ⌘K 一键可达所有核心功能，全键盘可操作 |
| 2.5 快捷键地图 | `?` 呼出快捷键速查表；补齐面板开关快捷键 | 速查表与实际实现一致 |

## Phase 3 · 体验智能化（被照顾的感觉）

| 任务 | 内容 | 验收 |
|------|------|------|
| 3.1 三态设计 | MessageList / ThreadSidebar / JobsPanel / ReviewPane / ProjectsPane 各自的空状态（插画+引导动作）、加载态（骨架屏）、错误态（原因+重试） | 每个面板三态齐全，无白屏/裸错误 |
| 3.2 流式体验 | 输出节奏感编排、工具调用过程可折叠、长任务确定性进度 | 等待过程可感知、可理解、可中断 |
| 3.3 微反馈体系 | 统一 toast（成功/失败/信息）、危险操作二次确认、操作可撤销（如删除会话） | 反馈语义统一，reduced-motion 降级优雅 |
| 3.4 Onboarding | 首次使用引导流打磨：3 步内完成核心价值体验 | 新用户 3 步内发出第一个任务 |

## Phase 4 · 功能 UX 增强（每个功能都好用）

> 原则：不推倒功能，只把每个功能的"最后一步体验"做到位。

| 功能 | 增强点 |
|------|--------|
| **Composer 输入区** | 拖拽文件/粘贴图片附件；草稿自动保存（刷新不丢）；⌘Enter 发送；↑ 调取上一条输入；附件缩略图预览 |
| **ThreadSidebar 会话** | 会话搜索；置顶；inline 重命名（双击）；删除可撤销（toast + Undo）；按时间分组（今天/昨天/7天内） |
| **JobsPanel 任务** | 完成/失败桌面通知（Tauri notification）；任务进度确定性百分比；失败一键重跑 |
| **Settings 设置** | 设置项搜索；修改即时生效；危险操作（清数据）二次确认 |
| **CanvasDock / Artifact** | 全屏模式；导出（复制/下载）；多版本切换 |
| **WorkModePicker** | 首次使用模式说明气泡（Ask/Plan/Craft 差异） |
| **全局** | 面板级 ErrorBoundary（单面板崩溃不拖垮全局）；右键上下文菜单；乐观更新 |

## Phase 5 · 度量与门禁（守住成果）

| 任务 | 内容 |
|------|------|
| 5.1 a11y 门禁 | axe 扫描接入 CI（现有 spec 补全后强制跑） |
| 5.2 包体积预算 | CI bundle budget：首屏 chunk 超限即失败 |
| 5.3 视觉回归 | 关键界面截图对比进入 release 流程 |

---

## 执行顺序与交付节奏

```
Phase 0 (护栏) → Phase 1 (设计系统) → Phase 2 (性能动效) → Phase 3 (体验智能) → Phase 4 (功能UX) → Phase 5 (门禁)
```

- 每个 Phase 结束：跑 `typecheck` + `lint` + 相关 e2e，交付可见成果并汇报。
- 每个 Phase 内的任务按表格顺序执行。
- 所有样式改动只动生产 shell 链路；legacy IDE 文件不碰（避免投入浪费）。

## 风险与原则

1. **不破坏现有功能**：Phase 0 截图基线就是为了兜住这一点。
2. **token 先行**：任何新样式必须引用 token，门禁脚本保证不回退。
3. **reduced-motion / prefers-contrast 全兼容**：世界级 = 对所有人世界级。
4. **暗色不是反色**：暗色 palette 单独设计（对比度、阴影改环境光），不是简单 invert。
