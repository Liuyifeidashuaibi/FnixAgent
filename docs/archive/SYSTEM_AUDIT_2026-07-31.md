# FnixAgent 系统全面审计报告

> 审计日期：2026-07-31
> 审计范围：`apps/`（desktop-tauri / fnix-local / workbench）、`packages/`（protocol / sdk）、Python 后端（`apps/desktop-tauri/resources/fnixagent-py/`）、根构建配置
> 方法：静态分析 + 编译期检查 + 模式扫描 + 关键文件人工走查

---

## 0. 总体结论

| 维度 | 结论 |
|------|------|
| TS 类型检查（workbench） | ✅ `tsc -b` 通过，0 错误（24s） |
| Python 语法编译（后端） | ✅ `compileall` 通过，0 语法错误 |
| 架构分层 | ✅ 引擎/业务解耦清晰，FSM 守卫规范 |
| 错误处理 | ⚠️ **系统性问题**：后端 100+ 文件存在宽泛 `except`/`except: pass`，吞没错误 |
| 仓库卫生 | ⚠️ 2423 文件 vendored OSS、300 个 `__pycache__`、重复配置目录、生成物入库 |
| 文档一致性 | ⚠️ `ARCHITECTURE.md` 描述的根级 Python 单体与实际 Tauri+嵌套 Python 布局不符 |

**核心判断**：编译层健康，**真正的风险在运行时健壮性与可观测性**（错误被静默吞没），以及**仓库冗余膨胀**（_references 占比过大）。无致命编译错误，但存在若干会在生产中表现为"Agent 静默失败 / 无输出"的逻辑缺陷。

---

## 1. HIGH 严重度问题

### 1.1 后端系统性错误吞没（影响：可靠性 / 可观测性）
Python 后端 **100+ 文件**含 `bare except:` / `except Exception:` / `except: pass`。典型热点：
- `services/work_agent.py`（17 处）、`services/work_pipeline.py`（13 处）
- `office/word.py`（11）、`office/powerpoint.py`（9）、`office/parser.py`（15）、`office/excel.py`（8）
- `core/security/sandbox.py`（10）、`core/security/signing.py`（9）

**具体证据**（`core/agent/loop.py:452-471`）：
```python
async def _call_llm(self, messages):
    try:
        ...  # 含 tools 调用
        return result
    except Exception as e:
        # 任何异常都退化为"不带 tools 重试"，再失败返回 None
        try:
            return await self._llm(messages)
        except Exception:
            return None
```
- 编程错误（如 AttributeError、配置错误）被当作"LLM 不支持 tools"处理，**完全静默**，调用方只拿到 `None`，最终用户看到"（无文本输出）"。
- `loop.py:544-552` 持久化 `session_store.save_session` 用 `except Exception: pass`，会话可能丢失且无日志。

**建议**：将宽泛 except 收窄为具体异常；所有 except 分支必须 `logger.warning(...)` 带 trace_id；关键路径（持久化/计费/安全）禁止 `pass`。

### 1.2 Agent 流式循环与非流式循环不一致（`core/agent/loop.py`）
- `run()`（228-373）：每次工具调用追加 `self.traces`、`self.messages`，结束调用 `_trigger_evolution_hook`。
- `run_stream()`（379-446）：**不追加** traces/messages，**不触发**进化钩子；且 done 事件里 `len(self.traces)` 恒为 0（415 行）。

后果：流式路径下执行轨迹/进化飞轮完全失效，与 `run()` 行为分叉。两条路径应抽取共享的"步进处理"逻辑。

### 1.3 LLM 工具参数 JSON 解析无防护（`loop.py:322, 429`）
```python
tool_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
```
LLM 偶发返回畸形 JSON 时，`json.JSONDecodeError` 直接中断**整个循环**（`run()` 内被外层 catch 兜成失败；`run_stream()` 兜成 error 退出）。应改为**逐工具** `try/except`，畸形参数记日志后跳过该工具调用，而非终止整轮。

### 1.4 硬编码占位 API Key（安全 / 配置）
- `core/llm/providers/openai.py:43` → `api_key="your-key"`
- `core/llm/providers/deepseek.py:18` → `api_key="your-key"`

作为默认值会掩盖"未配置密钥"的真实错误。应改为：仅从环境/配置读取，缺失时抛出明确异常（前端已有 BYOK 校验，后端兜底应一致）。

---

## 2. MEDIUM 严重度问题

### 2.1 前端 artifact 去重逻辑自相矛盾（`useChatFlow.ts:105-128`）
`mergeArtifacts` 的 basename/fullpath 去重规则不对称：
- L118：`prev` 含 `/`、`incoming` 不含、`prev` 以 `/base` 结尾 → **保留** prev（`return true`）
- L119：`incoming` 含 `/`、`prev` 不含、`incoming` 以 `/prev` 结尾 → **删除** prev（`return false`）

两个互为镜像的分支一个保留一个删除，加上后续 L122-127 的二次判断，可能在同 key 下产生重复条目或误删。建议简化为"规范化 key 集合去重"并补单测。

### 2.2 `stop()` 与 `send()` finally 的状态覆盖（`useChatFlow.ts:625-632, 793-805`）
`stop()` 调 `useRunStore.getState().finish(false)`，随后 abort 触发 `send()` 的 finally 又调 `reset()`。`finish(false)` 设定的终态会被 `reset()` 立即清掉。若 `FnixStatusBar` 订阅 runStore，可能看不到"已停止"状态。需确认 `finish` vs `reset` 的预期时序，或在 stop 后让 finally 跳过 reset。

### 2.3 文档与实际布局漂移
`ARCHITECTURE.md` 把仓库根描述为 Python 单体（`src/fnixagent/...`、`pyproject.toml` 在根等），实际：
- 根是 Tauri2 + React + pnpm monorepo（`apps/*`、`packages/*`）
- Python 后端嵌在 `apps/desktop-tauri/resources/fnixagent-py/src/fnixagent/`
- 根 `pyproject.toml`/`alembic.ini` 与嵌套包并存，职责边界不清

建议重写 ARCHITECTURE 的"目录结构"一节对齐现状，或拆分为 per-app 文档。

### 2.4 重复配置目录
根同时存在 `config/`（20 yaml + rego + json）与 `configs/`（3 json），命名近似、职责未区分，易混淆。应合并其一并明确约定。

### 2.5 生成物 / 字节码入库
- 根 `__pycache__/_verify_spec6.cpython-313.pyc` 已提交
- 300 个 `__pycache__` 目录散落（排除 node_modules/_references）
- `.fnix/artifacts/` 54 个生成测试产物入库

`.gitignore` 存在但未覆盖上述路径。建议补全 ignore 规则并 `git rm --cached` 清理。

---

## 3. LOW / 仓库卫生 / 冗余清单

| 项 | 量级 | 处置建议 |
|----|------|----------|
| `_references/` vendored OSS（chatgpt-desktop-oss 等） | **2423 文件**，无任何 build/config 引用 | 迁出为独立 repo 或 git submodule；本地 `.gitignore` 排除，避免污染 IDE 搜索与仓库体积 |
| 根 `package.json` 重复脚本 | `dev`/`dev:tauri`/`dev:desktop` 均=`tauri:dev`；`build`/`build:packaging`；`bundle:python`/`bundle:python:tauri`；`dev:all`/`dev:all:tauri` | 保留主名，其余删除或改 alias |
| `demos/` | 空目录 | 删除 |
| `skill_audit/` | 空目录 | 删除 |
| Python TODO/FIXME | ~15 处，`core/skills/market.py` 单文件 15 处 | 评估是否废弃的 marketplace 功能，废弃则删文件 |
| 前端 `console.log` | 6 文件（AnthropicProvider/Logger/tauri/EmbeddingOrchestrator/chatDb/TreeSitterSymbolExtractor） | 生产构建剥离或换结构化日志 |
| 前端 `any`/`as any` | 仅 3 文件（observability/worker/tauri） | 量小可接受，逐步收紧 |
| `benchmarks/` 4.3M、`data/` 3.1M | 入库数据 | 评估是否改用 LFS 或外部存储 |

> TS/React 前端总体质量高：`sessionStore.ts` persist 迁移、`shellFsm.ts` 守卫、`useChatFlow.ts` 同步 ref 同步与单次持久化均为良好实践。前端未发现高危 bug。

---

## 4. 整体优化建议（按优先级）

### P0 — 可靠性（1-2 周）
1. **错误处理专项治理**：脚本扫描所有 `except.*(pass|:)`，逐文件收窄异常类型 + 补 `logger`。先从 `core/agent/loop.py`、`services/work_agent.py`、`services/work_pipeline.py` 三个核心路径开始。
2. **统一 Agent 循环**：抽取 `run()`/`run_stream()` 共享步进逻辑（traces/messages 追加 + 进化钩子），消除行为分叉。
3. **工具调用健壮性**：`json.loads(arguments)` 包 per-tool try/except；限制 tool_result 长度（当前 `run_stream` 已截 500，`run` 未截）。

### P1 — 安全与配置（1 周）
4. 移除 `openai.py`/`deepseek.py` 的 `"your-key"` 默认值，缺失即抛异常。
5. 合并 `config/` 与 `configs/`，明确单一配置入口。
6. 补全 `.gitignore`：`__pycache__/`、`*.pyc`、`.fnix/artifacts/`、`test-results/`，并 `git rm --cached` 已入库生成物。

### P2 — 仓库瘦身（1 周）
7. `_references/` 迁出仓库（submodule 或独立 repo），2423 文件不入主仓。
8. 删除空目录 `demos/`、`skill_audit/`；清理根 `package.json` 重复脚本。
9. 评估 `core/skills/market.py`（15 TODO）是否废弃。

### P3 — 文档与工程化（持续）
10. 更新 `ARCHITECTURE.md` 对齐实际 monorepo 布局。
11. CI 增加：后端 `ruff` + `mypy`（至少 `--ignore-missing-imports`）+ 前端 typecheck（已绿）作为门禁。
12. 为 `mergeArtifacts`、`AgenticLoop.run`/`run_stream` 补单元测试（当前逻辑分叉正是缺测试的代价）。

---

## 5. 本次未覆盖（透明度声明）
- 未对 Rust 侧（`apps/*/src-tauri`）做 `cargo check`（需完整 toolchain，耗时较长），仅做了配置层巡视。
- 未执行运行时/e2e 测试（需起 agentd + 数据库），结论基于静态分析。
- `_references/`（2423 文件 vendored OSS）未逐文件审计，按"未被引用"整体处置。
- Python 后端仅深入走查了 `core/agent/loop.py` 等核心文件，其余 100+ 文件的 except 问题以模式扫描定位、未逐一定位根因。

建议后续按 P0 清单逐文件深入，并补一次 `cargo check` + e2e 冒烟以闭环。
