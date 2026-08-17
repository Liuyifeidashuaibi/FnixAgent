# L1 — 需求架构报告

## 1. 目标与边界

冻结 Fnix 产品契约与六层实施顺序，消除平行计划漂移。

| 硬约束 | 说明 |
|--------|------|
| 无强制账号 | Desktop 打开即用；standalone 网关匿名 |
| BYOK / API-only | `FNIX_API_ONLY=1`；无服务端代付 LLM |
| Tauri-only | 主壳；Electron 非主路径 |
| 本地数据 | `~/.fnix` + `{workspace}/.fnix` |

**本层不做**：实现引擎/UI/打包代码（仅契约与文档）。

## 2. 实现清单

| 项 | 路径 | 状态 |
|----|------|------|
| 产品主设计六层专节 | [`docs/FNIX_PRODUCT.md`](../FNIX_PRODUCT.md) §9 | ✅ |
| 报告总索引 | [`00-INDEX.md`](./00-INDEX.md) | ✅ |
| 本报告 | `L1-requirements.md` | ✅ |
| 双轨草案 | [`COMMERCIAL.md`](./COMMERCIAL.md) | ✅ |

### 六层职责（契约）

```text
L1 需求架构     产品定位、验收、OSS/企业边界
L2 底层引擎     KTG/STP/MFP + PDG + LLM adapter
L3 编辑器内核   Monaco · @file · Diff Accept
L4 AI Harness   会话/工具/skills/CLI/AG-UI
L5 上层产品     Work/Code · 引导 · 设置
L6 商业化打包   Community 安装包 + Enterprise 部署
```

## 3. 验收命令与证据

```bash
# 文档互链存在即可
test -f docs/FNIX_PRODUCT.md
test -f docs/layers/00-INDEX.md
test -f docs/layers/COMMERCIAL.md
rg -n "六层架构" docs/FNIX_PRODUCT.md
rg -n "L1-requirements" docs/layers/00-INDEX.md
```

证据（本轮）：`FNIX_PRODUCT.md` 已增加 §9 六层架构并链到 `docs/layers/`；COMMERCIAL 草案已立。

## 4. 下一层入口

→ **L2 底层引擎**：补齐内核健康字段、fnix-local 降级断言、BYOK 解析链回归。  
关键代码：`services/engine.py`、`work_pipeline.py`、`llm_policy.py`、`harness/local_bridge.py`。
