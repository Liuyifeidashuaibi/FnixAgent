---
name: artifacts-builder
description: React+Tailwind+shadcn artifacts 构建，多组件状态管理
version: 1.0.0
license: Apache-2.0
level: REASONING
output_format: html
tags:
  - artifacts
  - react
  - tailwind
  - shadcn
  - code
resources:
  - core/code/agent.py
  - core/code/indexer.py
---

# Artifacts Builder Skill

复杂 artifacts 构建技能，目标：用 React + Tailwind + shadcn/ui 构建带状态管理、路由、多组件协作的 elaborate artifact。区别于 `frontend-design` 侧重「设计系统」，本 skill 侧重「功能复杂度」。

## 何时使用

- 用户要构建带状态管理的多组件 artifact（如待办 / 看板 / 计算器 / 编辑器）
- 用户要构建带路由的 SPA（多视图切换）
- 用户要构建需要 shadcn/ui 复杂组件（Dialog / Sheet / Combobox / DataTable）的 artifact
- 用户要构建可交互 demo / 数据可视化应用

不要用于：单一静态页面（用 frontend-design）、纯视觉海报（用 canvas-design）。

## 工作流程

1. **意图识别**：从用户输入拆出 feature list、状态需求、数据来源。
2. **架构设计**：先输出组件树（ComponentTree）+ 状态模型（StateModel）+ 路由表，让用户确认。
3. **骨架实现**：按架构生成 `App.tsx` + 组件文件 + `tailwind.config.js` + `package.json`（如需）；优先用 shadcn/ui CLI 拉组件。
4. **功能填充**：逐组件填充逻辑，使用 React hooks（useState/useReducer/useContext）；状态复杂时引入 zustand。
5. **质量自检**：调用 `webapp-testing` skill 做 Playwright 验证；用 `core/code/indexer.py` 做代码静态检查。
6. **交付**：写入 `.fnix/artifacts/<slug>/`，返回路径与 `{ "components": int, "routes": int, "state_stores": int }`。

## 输出契约

- `output_format: html`（产物为多文件目录，含 `index.html` 入口）
- 产物路径：`.fnix/artifacts/<task_slug>/`（含 `index.html` / `App.tsx` / `components/` 等）
- 元数据：`{ "components": int, "routes": int, "state_stores": int, "lines_of_code": int }`
- 依赖约束：必须用 React 18+ / Tailwind 3+ / shadcn/ui 最新版；状态管理 ≤1 个外部库（zustand 优先）
- 可运行性：产物必须能在浏览器中直接打开运行（CDN 加载 React/Babel，或自带 vite 配置）
- 失败时不写盘，返回错误说明

## Fnix 集成点

- 底层实现：`fnixagent.core.code.agent.CodeAgent` + `fnixagent.core.code.indexer`
- 工具注册：`artifacts-builder.scaffold` / `artifacts-builder.add_component` / `artifacts-builder.add_route` / `artifacts-builder.add_state` / `artifacts-builder.add_shadcn`
- 设计语言：与 `frontend-design` skill 协作（design tokens 共享）
- 主题：与 `theme-factory` skill 协作
- 验证：与 `webapp-testing` skill 协作做 Playwright UI 验证
- 模式：Code 模式 — 写盘前 diff 给用户审阅

## 示例

**用户**：做一个待办应用，支持分类、优先级、过滤、本地存储。

**Skill 执行**：
1. `artifacts-builder.scaffold(name="todo-app", stack="react+tailwind+shadcn")`
2. 输出组件树：`App` / `TodoList` / `TodoItem` / `AddTodo` / `FilterBar`；状态模型：`{ todos: [], filter: "all" }`
3. `artifacts-builder.add_shadcn(components=["Button", "Input", "Select", "Checkbox"])`
4. `artifacts-builder.add_state(store="useTodoStore", lib="zustand", persist=true)`
5. 逐组件实现，调用 `webapp-testing` 验证：添加 / 编辑 / 删除 / 过滤 / 持久化
6. 返回 `.fnix/artifacts/todo-app/`
