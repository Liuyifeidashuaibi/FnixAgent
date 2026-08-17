---
name: webapp-testing
description: Playwright UI 验证 — 视觉/交互/响应式/a11y 自动检查
version: 1.0.0
license: Apache-2.0
level: REASONING
output_format: json
tags:
  - testing
  - playwright
  - ui
  - a11y
  - code
  - verification
resources:
  - core/code/agent.py
---

# Webapp Testing Skill

Web 应用 UI 验证技能，基于 Playwright 做视觉/交互/响应式/a11y 自动检查。是 `frontend-design` 与 `artifacts-builder` 的「look → fix」闭环中的 look 环。

## 何时使用

- 用户在 `frontend-design` / `artifacts-builder` 完成构建后做验证
- 用户报告 UI bug / 视觉不一致 / 交互卡顿
- 用户要做响应式测试（mobile / tablet / desktop 多视口）
- 用户要做 a11y（无障碍）扫描
- 用户要做 E2E 测试用例（点击 / 表单 / 路由）

不要用于：纯单元测试（用 pytest）、性能基准测试（用 benchmarks/）。

## 工作流程

1. **目标识别**：从用户输入提取 URL / 本地文件路径 / 测试场景（visual / interaction / responsive / a11y）。
2. **用例生成**：按场景生成 Playwright 脚本（spec.ts）；视觉测试附 baseline 截图路径。
3. **执行**：在沙箱中跑 Playwright（headless）；超时 30s/用例；失败截图落 `.fnix/artifacts/_test_failures/`。
4. **报告**：返回 JSON 报告（passed / failed / skipped + 失败原因 + 截图路径）。
5. **修复闭环**：失败用例自动转入 `frontend-design` 或 `artifacts-builder` 的 fix 阶段，最多 2 轮。

## 输出契约

- `output_format: json`
- 产物路径：测试报告 `.fnix/artifacts/_test_reports/<slug>.json`；失败截图 `.fnix/artifacts/_test_failures/<slug>/*.png`
- 报告 schema：
  ```json
  {
    "total": int,
    "passed": int,
    "failed": int,
    "skipped": int,
    "duration_ms": int,
    "failures": [{"case": str, "reason": str, "screenshot": str}]
  }
  ```
- 视口矩阵：默认 mobile(375) / tablet(768) / desktop(1280)
- a11y 标准：WCAG 2.1 AA（color contrast ≥ 4.5:1, alt text, focus visible）
- 失败时不阻塞产物交付，但报告必须明确标注

## Fnix 集成点

- 底层实现：Playwright（外部依赖，可通过 `core/code/tools.py` 调用）
- 工具注册：`webapp-testing.run_visual` / `webapp-testing.run_interaction` / `webapp-testing.run_responsive` / `webapp-testing.run_a11y` / `webapp-testing.run_e2e`
- 协作：被 `frontend-design` / `artifacts-builder` 调用为 look 阶段；失败转回 fix
- 模式：Code 模式 — 测试报告写入 `.fnix/artifacts/_test_reports/`；不直接修改用户源码
- 持久化：失败截图保留 7 天，便于回溯

## 示例

**用户**：测试 `.fnix/artifacts/saas_landing/index.html` 的响应式 + a11y。

**Skill 执行**：
1. `webapp-testing.run_responsive(target=".fnix/artifacts/saas_landing/index.html", viewports=[375, 768, 1280])`
2. `webapp-testing.run_a11y(target=..., standard="wcag2.1-aa")`
3. 执行 Playwright（headless）：3 视口截图 + axe-core 扫描
4. 输出报告：
   ```json
   {"total": 8, "passed": 7, "failed": 1, "failures": [{"case": "a11y: hero-button-contrast", "reason": "contrast 3.2:1 < 4.5:1", "screenshot": ".fnix/artifacts/_test_failures/saas_landing/hero.png"}]}
   ```
5. 失败用例自动转给 `frontend-design` 的 fix 阶段
