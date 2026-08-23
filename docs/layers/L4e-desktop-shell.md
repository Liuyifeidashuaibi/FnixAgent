# L4e — Fnix Desktop（Fnix Desktop style · Tauri）

**产品形态**：Tauri 桌面窗（不是浏览器页）。外观Fnix Desktop；运行时走本机 **agentd** + BYOK。

## 一键启动（推荐）

```bash
pnpm dev:all:tauri
```

会拉起：fnix-local + agentd + `@fnixagent/workbench` Tauri 窗。

若 agentd 已在 `http://127.0.0.1:8003`：

```bash
# PowerShell
$env:VITE_API_BASE="http://127.0.0.1:8003"
$env:FNIXAGENT_PROFILE="standalone"
pnpm --filter @fnixagent/workbench tauri:dev
```

## 测试清单

1. 窗口标题 **Fnix**，默认 **Fnix Work** 浅色壳（非 IDE）
2. 底栏齿轮 → Providers → 填 API Key → Save
3. Work：输入框发一句，应出现流式回复 / 状态条
4. 侧栏 **Open project** → 选本地文件夹
5. 切到 **Code** → 对项目发编码任务
6. 底栏显示 `agentd online`

经典 IDE（调试用）：URL `?shell=ide` 或 `localStorage.fnix.ui.shell=ide`

## 接线

| UI | API |
|----|-----|
| Work | `POST /api/v1/work/stream` |
| Code | `POST /api/v1/chat/agent` |

代码：`apps/workbench/src/shell/desktop/`
CSP 已允许 `http://127.0.0.1:*` 连接 agentd。
