---
name: agent-browser
description: 脚本化浏览器操作：页面交互、截图、数据提取与自动化流程
version: 1.0.0
license: Apache-2.0
level: REASONING
output_format: json
tags:
  - browser
  - automation
  - playwright
  - trae-work
---
# Agent Browser Skill

脚本化浏览器操作：导航、点击、填表、截图、抽数据、回归验证。优先用项目已有的浏览器自动化工具（Playwright / agent-browser / 内置 browser MCP）。

## 何时使用

- 多步网页交互验证或数据抓取
- 响应式 / 视觉回归截图
- 需要 ref 快照后再批量操作以省 token

与 `webapp-testing` 分工：本 skill 偏「操作与采集」；`webapp-testing` 偏「断言与质量门禁」。

## 工作流程

1. **侦查**：打开目标 URL，先 snapshot / 可访问性树，识别可交互元素。
2. **计划**：列出最短操作序列；登录态与 cookie 提前说明。
3. **执行**：按 refs 点击/输入；每步大状态变化后重新 snapshot。
4. **取证**：关键步骤截图；失败时保存 DOM/控制台。
5. **交付**：操作日志 + 截图路径 + 提取的结构化数据。

## 约束

- 不绕过登录墙/验证码去撞库；用户需提供可用会话或测试账号。
- 不抓取违法/付费墙后未授权内容。
- 优先稳定选择器（role/text），少用脆弱 CSS。

