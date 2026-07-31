# Fnix 六层实施报告 — 总索引

> 产品主设计：[`../FNIX_PRODUCT.md`](../FNIX_PRODUCT.md)  
> 双轨边界：[`COMMERCIAL.md`](./COMMERCIAL.md)  
> 更新：2026-07-18

## 进度

| 层 | 报告 | 状态 |
|----|------|------|
| L1 需求架构 | [L1-requirements.md](./L1-requirements.md) | ✅ |
| L2 底层引擎 | [L2-engine.md](./L2-engine.md) | ✅ |
| L3 编辑器内核 | [L3-editor.md](./L3-editor.md) | ✅ |
| L4 AI Harness | [L4-harness.md](./L4-harness.md) | ✅ |
| L4b 认知完善 | [L4b-cognition.md](./L4b-cognition.md) | ✅ |
| L4c 行业对照 | [L4c-industry-vs-fnix.md](./L4c-industry-vs-fnix.md) | ✅ Step1–5 |
| L4d Workbench UI | [L4d-workbench.md](./L4d-workbench.md) | ✅ `apps/workbench` |
| L4e ChatGPT 壳 | [L4e-chatgpt-desktop-shell.md](./L4e-chatgpt-desktop-shell.md) | ✅ 默认外观 |
| 仓库结构 | [../STRUCTURE.md](../STRUCTURE.md) | ✅ |
| L5 上层产品 | [L5-product.md](./L5-product.md) | ✅ |
| L6 商业化打包 | [L6-packaging.md](./L6-packaging.md) | ✅ |

## 运行时（冻结）

```text
Tauri Desktop → agentd :8000 → fnix-local :8710
              ↘ ~/.fnix + {workspace}/.fnix
```

## 验收汇总

- [x] L1：主文档六层专节 + 本索引互链
- [x] L2：引擎/策略 pytest；health + harness/status 字段
- [x] L3：`@file` + Diff Accept（`scripts/test-file-mentions.mjs`）
- [x] L4：AG-UI Work 流 + memory 测 + WorkPanel 修复
- [x] L5：e2e 4 passed（无登录 / 引导 / Work·Code）
- [x] L6：COMMERCIAL 定稿；Release/README 双轨

## 关键验证命令（汇总）

```bash
PYTHONPATH=src pytest tests/unit/test_engine_status.py \
  tests/unit/test_byok_harness_chain.py \
  tests/unit/test_llm_policy_api_only.py \
  tests/unit/test_harness_memory.py \
  tests/unit/test_ag_ui_mapper.py -q

node scripts/test-file-mentions.mjs
node scripts/test-ag-ui-stream.mjs

pnpm exec playwright test e2e/ui/login.spec.ts e2e/ui/onboarding.spec.ts --workers=1

# Code 全流程闭环（新建→写码→编译→修错）
pnpm smoke:code-loop
```

详见 [`../CODE_LOOP_SELFTEST.md`](../CODE_LOOP_SELFTEST.md)。

## 报告模板（每层四块）

1. **目标与边界**
2. **实现清单**
3. **验收命令与证据**
4. **下一层入口**
