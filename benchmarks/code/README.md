# Fnix Code Benchmark (FCS)

千级写码工程任务包，配合 `docs/CODE_BENCHMARK.md` 使用。

## 快速开始

```bash
# 生成/刷新 1000 任务
python scripts/generate-code-tasks.py --count 1000

# 离线验证框架 + 已有正确解的 generated 任务
python scripts/run-code-benchmark.py --dry-checks --limit 50

# CI 冒烟（9 个 seed，需 agentd + LLM）
python scripts/run-code-benchmark.py --tag smoke --limit 9 --base http://127.0.0.1:8003

# 全量（建议 nightly）
python scripts/run-code-benchmark.py --limit 1000 --parallel 4
```

## 目录

| 路径 | 说明 |
|------|------|
| `schema/task.schema.json` | 任务 JSON Schema |
| `seed/` | 9 个精选任务（10 能力覆盖） |
| `generated/` | 模板生成 ~991 任务 |
| `manifest.json` | 任务索引 |

## 评分

见 `docs/CODE_BENCHMARK.md` — **FCS** 按难度加权，单任务含 correctness / completeness / process / safety / speed。
