# L5 — 上层产品功能报告

## 1. 目标与边界

无登录、可用的 Work/Code Living Workbench（引导 · 设置 · BYOK）。

| 做 | 不做 |
|----|------|
| 引导/工作台/关于页打磨 | 账号体系回流 |
| e2e：无登录 · 引导 · Work/Code | Electron 主路径 |

## 2. 实现清单

| 项 | 路径 | 状态 |
|----|------|------|
| FirstRunWizard / BootScreen（既有强化） | `FirstRunWizard.tsx` / `App.tsx` | ✅ |
| hydrate 超时，避免卡死加载 | `App.tsx` / `fnixConfigSync.ts` / `apiAuth.ts` | ✅ |
| Code 空态文案 | `LivingWorkbench.tsx` | ✅ |
| 关于：Apache-2.0 · 本地 · BYOK | `SettingsPanel.tsx` | ✅ |
| e2e onboarding | `e2e/ui/onboarding.spec.ts` | ✅ |
| e2e login/offline 选择器加固 | `e2e/ui/login.spec.ts` | ✅ |
| 修 `fileMentions` esbuild 语法 | `fileMentions.ts` | ✅ |

## 3. 验收命令与证据

```bash
pnpm exec playwright test e2e/ui/login.spec.ts e2e/ui/onboarding.spec.ts --workers=1
# → 4 passed (2026-07-18)
```

产品 §11 场景：

| # | 场景 | 证据 |
|---|------|------|
| 1 | 无登录打开 | e2e login |
| 2 | 引导可跳过 | e2e onboarding |
| 3–4 | Work/Code UI | e2e Work/Code 可见；流式需真 Key |
| 5 | 重启持久化 | `~/.fnix` + localStorage（L2/L4） |
| 6 | CLI | `fnixagent doctor`（L4） |

## 4. 下一层入口

→ **L6 商业化打包**：Community Release + COMMERCIAL 定稿 + INDEX 汇总。
