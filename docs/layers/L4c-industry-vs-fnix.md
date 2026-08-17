# L4c — Codex / Cursor / Trae 必备层次 × Fnix 对照与实施计划

> 原则：学参考、定自己的产品（见 [`FNIX_PRODUCT.md`](../FNIX_PRODUCT.md)）。  
> 不抄 `.codex` / 云订阅 / Electron；对齐能力，落在 `~/.fnix` + Work/Code。

---

## 1. 做一款 Codex / Cursor / Trae 级产品需要哪些环节

三款产品外壳不同，**内核层次高度重合**：

```text
L0  产品壳          CLI / IDE / 双模式工作台
L1  运行时宿主       进程拉起、PTY、配置同步、健康检查
L2  Agent Loop       指令→Prompt→推理→工具→回灌→迭代
L3  工具协议         文件/Shell/Git/测试 + MCP 扩展
L4  上下文与规则     AGENTS.md / 记忆 / Skills / 压缩
L5  任务与持久化     会话 JSON、后台长任务、向量经验
L6  安全沙箱         工作区边界、命令黑名单、Diff/回滚
L7  交付与双轨       安装包、BYOK、OSS vs 企业
```

| 层次 | Codex | Cursor | Trae | Fnix 对标 |
|------|-------|--------|------|-----------|
| L0 壳 | CLI(+多端) | IDE/Composer | Work+Code | **Living Workbench** |
| L1 宿主 | `~/.codex` | 云+本地 | 云+本地 | **Tauri→agentd→fnix-local→`~/.fnix`** |
| L2 Loop | ReAct 循环 | Composer Agent | Work/Code Agent | **Work ReAct + Code plan/exec/review** |
| L3 工具 | Shell/文件/MCP | 编辑器+终端+MCP | 办公+代码工具 | **workspace/CodeTools；MCP 待接入 loop** |
| L4 规则 | AGENTS.md 分层 | Rules/.cursorrules | 项目约定 | **`.fnix/rules.md` + AGENTS.md 兼容** |
| L5 记忆 | 会话+记忆+Skills | 索引+记忆 | 会话 | **SOUL/MEMORY/skills/sessions** |
| L6 安全 | 沙箱+审批 | Accept Diff | — | **路径沙箱+Diff Accept；回滚增强** |
| L7 商业 | OpenAI 绑定 | 订阅 | 云账号 | **Community BYOK；Enterprise JWT** |

---

## 2. 标准实施步骤（行业通用 → Fnix 映射）

| # | 行业步骤 | Fnix 状态 | 本计划动作 |
|---|----------|-----------|------------|
| S1 | 固定 Agent Loop | ✅ 已有 | 不重写；只扩注入与工具 |
| S2 | 原生工具集 | ✅ + delete_file | 已补 |
| S3 | MCP 进 loop | ✅ Work 挂载 | 空配置零回归 |
| S4 | 项目规则 AGENTS.md | ✅ 已注入 | Step 1 完成 |
| S5 | 会话落盘可回溯 | ✅ | 保持 |
| S6 | 长任务后台队列 | ✅ `/work/jobs` + worker | Step 5 完成 |
| S7 | 上下文压缩/分片 | ✅ context_budget trim | Step 4 完成 |
| S8 | 向量长期记忆 | ✅ Python IndexStore 降级召回 | Step 4 完成 |
| S9 | Diff Accept + 回滚 | ✅ Accept + rollback API/UI | Step 3 完成 |
| S10 | 多端同 Harness | ✅ Tauri+CLI | 保持 |

---

## 3. Fnix 分步实施（保护 Work/Code 闭环）

### Step 1 — 项目规则注入（最低风险）✅
- 模块：`harness/project_rules.py`
- 读 `{workspace}/.fnix/rules.md` + 根→cwd 链上的 `AGENTS.md` / `AGENTS.override.md`
- 经 `local_context_prompt` 注入 Work/Code
- 测：`tests/unit/test_project_rules.py`

### Step 2 — MCP 接入 Work Agent Loop ✅（空配置零回归）
- `attach_mcp_tools_to_registry` → `build_work_agent_loop`
- 空 `mcp.json` / `FNIX_MCP_IN_LOOP=0` / 连接失败：静默跳过

### Step 3 — 工具与回滚 ✅
- `delete_file`（工作区限定，禁删目录）
- Shell 黑名单加固
- `POST /chat/agent/rollback` + `{workspace}/.fnix/changesets`
- Composer「撤销上次写盘」

### Step 4 — 上下文升级 ✅
- `harness/context_budget.py` trim + tokens_est
- `local_context`：sidecar 无命中 → Python `IndexStore` 召回
- mission 事件带 `context_budget`

### Step 5 — 可脱离流的后台 Work 任务 ✅
- `POST /work/jobs` + worker（lifespan 启动）
- `GET /work/jobs/{id}/events` 重连
- WorkPanel「后台挂机」勾选

### 明确不做（Community）
- 云端隔离容器执行（企业另轨）
- 登录墙 / 托管 LLM
- 重写为单一 Codex CLI 产品

---

## 4. 验收闸门（每步必绿）

```bash
PYTHONPATH=src pytest tests/unit/test_project_rules.py \
  tests/unit/test_harness_memory.py -q

pnpm smoke:code-loop   # Step 2+ 后仍必跑
```

---

## 5. 与上一轮「Codex 模块清单」的对应

| 你列的模块 | 落点 |
|------------|------|
| Agent Loop | S1 已有 → 不改内核 |
| MCP 工具协议 | Step 2–3 |
| 任务状态机+后台队列 | Code FSM 已有；后台 = Step 5 |
| 多层级上下文 | Step 4 |
| AGENTS.md | **Step 1** |
| `~/.codex` 持久化 | 已用 `~/.fnix` |
| 安全沙箱+回滚 | 部分有 → Step 3 |
| 多端载体 | L5 已交付 |
