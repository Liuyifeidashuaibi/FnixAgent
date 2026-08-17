# 性能工程 / Performance Engineering

> 本文件定义 FnixAgent 的性能预算、测量实践、优化指南。

---

## 一、性能预算 / Performance Budgets

### 启动性能

| 阶段 | 目标 | 实测(参考) |
| --- | --- | --- |
| 冷启动 → 首屏可交互 | < 1500 ms | 1100 ms |
| 冷启动 → agentd ready | < 2500 ms | 1800 ms |
| 冷启动 → LLM 可用 | < 5000 ms (本地) | 3500 ms |
| 热启动 → 首屏 | < 500 ms | 320 ms |

### 运行时性能

| 指标 | 目标 | 备注 |
| --- | --- | --- |
| 内存(空闲) | < 250 MB | 不含 LLM 进程 |
| 内存(运行中) | < 800 MB | 不含 LLM 进程 |
| CPU(空闲) | < 1% | macOS M1 |
| WebView 帧率 | ≥ 60 FPS | 长列表滚动 |
| LLM 首 token | < 500 ms (云) / < 200 ms (本地) | streaming |
| Tool 调用往返 | < 100 ms | 进程内 |
| 文件搜索 | < 200 ms | 10k 文件 |

### 网络性能

| 场景 | 目标 |
| --- | --- |
| 单次 LLM 请求 | < 1.5 s (云) |
| 100k 上下文 prompt | < 5 s (云) |
| 记忆检索 (RRF) | < 300 ms |
| 嵌入生成(本地 bge-small-zh) | < 100 ms/query |

---

## 二、测量方法 / Measurement

### 1. 启动时间

```typescript
// apps/workbench/src/lib/perf/startup.ts
import { performance } from 'perf_hooks'

export class StartupProfiler {
  private marks: Map<string, number> = new Map()

  mark(name: string): void {
    this.marks.set(name, performance.now())
  }

  measure(from: string, to: string): number {
    const a = this.marks.get(from)
    const b = this.marks.get(to)
    if (a === undefined || b === undefined) {
      throw new Error(`missing mark: ${from} or ${to}`)
    }
    return b - a
  }

  report(): Record<string, number> {
    return {
      boot_to_dom: this.measure('boot', 'dom_ready'),
      dom_to_interactive: this.measure('dom_ready', 'interactive'),
      boot_to_interactive: this.measure('boot', 'interactive'),
    }
  }
}
```

### 2. 运行时火焰图

```bash
# 安装 py-spy
uv tool install py-spy

# 录制 30s 火焰图
py-spy record -o flame.svg --duration 30 -- python -m fnixagent

# 内存
mprof run -- python -m fnixagent
mprof plot
```

### 3. CI 性能回归

`.github/workflows/perf-regression.yml`:

```yaml
- name: Bench startup
  uses: benchmark-action/github-action-benchmark@v1
  with:
    tool: 'customBiggerIsBetter: false'
    output-file-path: bench/startup.json
    alert-threshold: 110%
```

### 4. LLM 调用性能

```python
# src/fnixagent/observability/llm_metrics.py
from opentelemetry import metrics

meter = metrics.get_meter("fnixagent.llm")

llm_latency = meter.create_histogram(
    name="llm.request.duration",
    unit="ms",
    description="LLM request latency",
)

llm_tokens = meter.create_counter(
    name="llm.tokens.total",
    description="Total tokens",
)
```

---

## 三、性能优化 / Optimization

### 3.1 启动优化

#### WebView 侧

```typescript
// apps/workbench/src/main.tsx
import { lazy, Suspense } from 'react'

// ❌ 全部同步加载
import Heavy from './components/Heavy'

// ✅ 路由级 lazy
const Heavy = lazy(() => import('./components/Heavy'))

function App() {
  return (
    <Suspense fallback={<Skeleton />}>
      <Routes />
    </Suspense>
  )
}
```

#### Rust 侧

```rust
// src-tauri/src/lib.rs
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // 后台初始化非关键模块
    tauri::async_runtime::spawn(async {
        load_skill_registry().await;
        warm_embedding_model().await;
    });

    tauri::Builder::default()
        .setup(|app| {
            // 只初始化关键模块
            app.manage(create_agentd_client());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### 3.2 内存优化

#### Python 端

```python
# ❌ 全局缓存无界
import functools
_cache = {}
@functools.lru_cache(maxsize=None)  # 内存爆炸
def get_embedding(text): ...

# ✅ 显式 LRU
@functools.lru_cache(maxsize=1024)
def get_embedding(text): ...
```

#### Rust 端

```rust
use moka::future::Cache;

let cache: Cache<String, Vec<f32>> = Cache::builder()
    .max_capacity(10_000)
    .time_to_live(Duration::from_secs(3600))
    .build();
```

### 3.3 LLM 性能

#### 流式响应

```typescript
// 永远不要等完整响应
const stream = await llm.stream(prompt)
for await (const chunk of stream) {
  ui.appendChunk(chunk)
}
```

#### Prompt 缓存

```yaml
llm:
  providers:
    anthropic:
      cache_control:
        enabled: true
        ttl: 5m  # 5 分钟内重复 prompt 命中缓存
        break_points: ["system", "tools"]
```

#### 并行调用

```python
import asyncio

# ❌ 串行
for q in queries:
    result = await llm.run(q)

# ✅ 并行
results = await asyncio.gather(*[llm.run(q) for q in queries])
```

### 3.4 记忆检索优化

```python
# src/fnixagent/memory/retriever.py
class HybridRetriever:
    def __init__(self):
        self.bm25 = BM25Okapi()
        self.vector_index = sqlite_vec.Index("~/.fnix/memory/semantic/index.sqlite")

    async def retrieve(self, query: str, k: int = 10) -> list[MemoryChunk]:
        # 并行执行 BM25 + 向量
        bm25_task = asyncio.create_task(self._bm25(query, k=k))
        vec_task = asyncio.create_task(self._vector(query, k=k))
        bm25_results, vec_results = await asyncio.gather(bm25_task, vec_task)

        # RRF 融合
        return reciprocal_rank_fusion([bm25_results, vec_results], k=k)
```

---

## 四、性能监控 / Monitoring

### Prometheus 暴露

```
GET http://127.0.0.1:7891/metrics

# HELP fnixagent_llm_request_duration_seconds
# TYPE fnixagent_llm_request_duration_seconds histogram
fnixagent_llm_request_duration_seconds_bucket{provider="openai",model="gpt-4o",le="0.5"} 12
fnixagent_llm_request_duration_seconds_bucket{provider="openai",model="gpt-4o",le="1.0"} 45
fnixagent_llm_request_duration_seconds_bucket{provider="openai",model="gpt-4o",le="2.0"} 89

# HELP fnixagent_memory_count
# TYPE fnixagent_memory_count gauge
fnixagent_memory_count{type="core"} 42
fnixagent_memory_count{type="episodic"} 1287
```

### 仪表盘

`deploy/grafana/fnixagent-dashboard.json` — 预制 16 个面板:
- 请求延迟 P50/P95/P99
- LLM token 消耗速率
- 记忆增长速率
- Skill 调用频次
- 内存 / CPU 使用

---

## 五、性能测试 / Benchmarks

`bench/` 目录持续维护:

- `bench/startup.bench.ts` — 启动时间
- `bench/llm-latency.bench.py` — LLM 调用延迟
- `bench/memory-search.bench.py` — 记忆检索
- `bench/skill-execution.bench.ts` — Skill 执行

跑:

```bash
make bench
# 或
uv run pytest bench/ -v --benchmark
```

---

## 六、PR 性能审查

任何 PR 如果**改了核心路径**(`agentd`, `workbench` 启动, LLM 调用),必须:

1. 跑 `make bench` 前后对比
2. 在 PR 描述里贴出对比结果
3. 超过 10% 退化需要 Core Maintainer 评审

---

## 七、参考

- [Web Vitals](https://web.dev/vitals/)
- [Tauri Performance Tips](https://tauri.app/v1/guides/features/performance)
- [Python asyncio Performance](https://docs.python.org/3/library/asyncio-dev.html)

---

© 2024-2026 FnixAgent. All Rights Reserved.