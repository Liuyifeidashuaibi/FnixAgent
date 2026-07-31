# 自进化内核（必做护城河，不是可选项）

FnixAgent 相对 **TRAE Work / WorkBuddy / Cursor** 的差异化，来自三大原创机制。
它们必须出现在 **Work 产品主路径**（`/api/v1/work/stream`），不能只活在旁路 API。

| 机制 | 作用 | 代码 |
|---|---|---|
| **KTG** | 四层知识拓扑 + 权重路径搜索，替代纯向量 RAG | `core/topology/` |
| **STP** | L2 概念 ↔ 技能突触，权重驱动工具优先级 | `core/skills/` |
| **MFP** | ①感知执行 → ②知识固化 → ③元反思 → ④爬山进化 | `core/flywheel/` |

## README 9 步流水线（已落地）

实现：`services/work_pipeline.py` → `/api/v1/work/stream`

1. 安全校验（`SecurityEngine.check_input`）
2. 短期记忆加载
3. 长期/实体记忆召回
4. ReasoningSelector（ReAct / Plan&Execute / Self-Reflect）
5. KTG 路径 + STP 技能排序
6. AgenticLoop 工具执行（流式）
7. （模式驱动）反思提示注入
8. 输出审核 / 脱敏
9. 记忆保存 + MFP ②③④ + KTG 快照 + TraceId 审计

## 产品原则

1. **默认开启**：`FNIXAGENT_MODE=both`
2. **启动播种**：`services/evolution_seed.py`
3. **KTG 持久化**：`data/topology/` JSON 快照
4. **Desktop**：Work 顶栏显示 KTG/STP/MFP/记忆/安全/推理状态

## 请求流

```
Desktop WorkPanel
  → POST /api/v1/work/stream
  → WorkPipeline 9 步
  → NDJSON: evolution / pipeline / thought / action / artifact / done
```

状态查询：`GET /api/v1/work/status`
