# Fnix Harness — 顶级产品优化方案（落地版）

> **目标用户体验（唯一北极星）**  
> 下载 → 填自己的 API Key → 选文件夹 → **真正完成工作**（办公交付 / 代码工程），无需账号、无需懂端口。  
> 对标形态：Hermes（本机 BYOK）+ Trae（Work|Code）+ Cursor（Diff Accept）+ Codex（Agent Loop）。  
> **Fnix 必须赢在**：本地可控 + Work 办公厚 + 可量化迭代；代码 Agent 交付达到「能用」再谈「顶级」。

---

## 0. 当前真相（以实测为准，不以文档为准）

| 层 | 现状 | 结论 |
|----|------|------|
| 下载即用（路径 A） | Release 未发首包；开发者仍需端口/三进程 | **开箱未闭环** |
| BYOK | Settings + `~/.fnix` 可用 | ✅ 可用 |
| Work Ask/Plan | 能跑 | ✅ |
| Work Craft | 能写盘，artifact 易超标 | ⚠️ 交付粗糙 |
| Code Preview→Accept | 链路通 | ✅ |
| Code 真实交付 | FCS 冒烟 ≈ **59**；multi_file / test_gen / heal 弱 | ❌ **不能自称顶级** |
| KTG/STP/MFP | 在 Work 主路径有挂接 | ⚠️ **用户感知弱** → 易成摆设 |
| 全链路 `/benchmark` | 后端 100；前端依赖正确 API 端口 | ⚠️ 端口/代理易踩坑 |
| 大仓索引 | fnix-local 可降级 | ⚠️ 未成 Cursor 级优势 |

**原则**：凡文档写了「已有」但 FCS / e2e / 用户任务跑不过的，一律按 **未完成** 排期。

---

## 1. 产品定义（冻结，所有优化围绕它）

### 1.1 一句话

**Fnix = 本机 AI 工作台：自己的 Key，Work 交产物，Code 审完再写盘。**

### 1.2 三条用户路径（优先级）

| 优先级 | 路径 | 成功标准（可验收） |
|--------|------|-------------------|
| P0 | **A 最终用户**：Release 安装包 | 双击打开 → 5 分钟内用 BYOK 完成 1 个 Work Craft + 1 个 Code Accept |
| P1 | **B 开发者**：`pnpm setup && pnpm doctor && pnpm dev` | 一条命令起三进程；doctor 红灯可自愈提示 |
| P2 | **C 贡献者**：`verify:beta` | CI 含全链路 + FCS smoke |

### 1.3 明确不做（防稀释）

- 不做「又一个 VS Code 分叉」抢 Cursor 扩展生态  
- 不做账号墙 / 托管模型订阅  
- 不做 Telegram 网关类 Hermes 外延  
- 不做只存在于 docs 的能力（见 §6 防摆设法则）

### 1.4 Fnix 必须发挥的优势（护城河，要「可见可验」）

| 优势 | 用户可感知的表现 | 验收 |
|------|------------------|------|
| BYOK + 零账号 | 首次引导 3 步完成；Key 不出本机 | e2e onboarding |
| Work 办公厚 | Craft 产出可打开的 docx/xlsx/html | `e2e-work-*` + 人工抽检 |
| Diff Accept | Code 默认预览，Accept 才写盘，可 Rollback | `e2e-code-projects` |
| KTG/STP/MFP | Work 任务条显示「用了哪条路径/技能」；同任务二次更快 | UI 可见 + status API |
| 可量化 | Settings「全链路测试」+ FCS 分数 | `/benchmark` + `run-code-benchmark --tag smoke` |

---

## 2. 北极星指标（数字说话）

| 指标 | 当前（约） | Beta 门槛 | 顶级门槛 |
|------|------------|-----------|----------|
| **开箱成功率**（装包→首任务） | 未测 | ≥ 80% | ≥ 95% |
| **全链路分**（无 LLM） | 100（本机） | ≥ 95 | ≥ 98 |
| **FCS smoke（≥9 seed）hard_pass** | ~40% | ≥ **70%** | ≥ **85%** |
| **FCS 加权总分** | ~59 | ≥ **75** | ≥ **85** |
| **Work Craft 任务成功率**（固定 10 场景） | 未固化 | ≥ 80% | ≥ 90% |
| **首任务时延**（简单 Craft） | — | ≤ 90s | ≤ 45s |
| **用户感知进化**（KTG 命中可见） | 弱 | 每次 Work 可见 | 可解释「为何更快」 |

未达 Beta 门槛：**禁止**对外宣称「对标 Cursor/Trae」。

---

## 3. 六大战役（按依赖排序）

```text
战役 1 开箱闭环 ──► 战役 2 黄金交付 ──► 战役 3 Code 交付
         │                    │                 │
         └──────────► 战役 4 优势可见（KTG/STP/MFP）
                              │
                     战役 5 索引与上下文 ──► 战役 6 发布与增长
```

---

### 战役 1 — 开箱闭环（Hermes 级）：「下载就能用」

**问题**：产品叙事是路径 A，现实仍是「懂端口的开发者工具」。

| # | 动作 | 产出 | 验收 |
|---|------|------|------|
| 1.1 | **首次引导向导**（非 Settings 藏深处） | 打开 → Key → 测连通 → 选文件夹 → 进 Home | Playwright：无 Key 时不能发消息；有 Key 后一键通 |
| 1.2 | **Tauri 托管三进程** | Desktop 启动自动起 agentd + fnix-local；退出杀干净 | `doctor` + 冷启动 e2e |
| 1.3 | **API 基址单一来源** | UI / Vite proxy / agent 同读 `VITE_API_BASE` 或 Tauri 注入；禁硬编码 8000/8003 漂移 | 全链路面板从 UI 跑通 |
| 1.4 | **Release 首包** | Windows NSIS（优先）内嵌 Python runtime | GitHub Release `v0.9.0-beta`；新人机器零 Python 可装 |
| 1.5 | **Doctor 产品化** | Settings → Diagnostics 显示红黄绿 + 一键修复提示 | 端口占用、无 Key、sidecar 挂 均有文案 |

**完成定义**：陌生用户只读 README 一页，15 分钟内完成「写一个 hello.html + Accept 修一个 bug」。

---

### 战役 2 — Work 真实交付（Trae Work 级）

**问题**：Ask/Plan OK，Craft 产物多且乱，办公优势未变成「打得开的文件」。

| # | 动作 | 产出 | 验收 |
|---|------|------|------|
| 2.1 | **固定 10 个黄金 Work 场景** | 写进 `benchmarks/work/golden/`（docx / xlsx / html 站 / md 报告…） | 脚本跑 10/10 或标明失败原因 |
| 2.2 | **Craft 写盘契约** | 默认只写 `.fnix/artifacts/<task_id>/`；禁止散落根目录 | e2e 断言路径前缀 |
| 2.3 | **Results 面板 = 唯一真相** | Artifacts 列表可一键打开；重复路径合并 | UI + e2e-mbti 类场景 |
| 2.4 | **Ask/Plan/Craft 硬边界** | Ask/Plan 零写盘（已有则加强测试） | `e2e-work-modes` 必须绿 |
| 2.5 | **办公工具可观测** | 任务条显示「正在 create_docx…」 | 过程时间线非空 |

**完成定义**：用户说「做一份周报 xlsx」→ Results 里有可打开的 `.xlsx`，无需切 Code。

---

### 战役 3 — Code 真实交付（Cursor/Codex 级底线）

**问题**：链路通 ≠ 交付对。FCS 59 / hard_pass 40% 是产品级红灯。

| # | 动作 | 产出 | 验收 |
|---|------|------|------|
| 3.1 | **先打 seed 闸门** | 9 个 smoke seed 进 CI；**hard_pass ≥ 7/9** | `run-code-benchmark --tag smoke` |
| 3.2 | **强制「产物清单」** | Plan 阶段输出 files_to_create/edit；Execute 对照清单；缺文件再 heal | multi_file / fibonacci 过 |
| 3.3 | **Heal 闭环** | compile/pytest 失败 → 自动读错误 → ≤3 轮改 → 再验 | `seed.heal.syntax_error` hard_pass |
| 3.4 | **test_gen 模板** | 有实现无测试时默认补 `test_*.py` | `seed.test_gen.*` / fibonacci |
| 3.5 | **Accept UX** | Review 侧栏：文件树 + hunk + Reject/Accept；默认不自动 Accept | 人工走查 + e2e-code |
| 3.6 | **FCS 爬坡** | 每周跑 smoke；月跑 100 任务；季跑 1000 | 报告入库 `reports/` |

**完成定义**：用户 Open project →「修 subtract bug / 加 fib + 测试」→ Accept 后 pytest 绿。

**禁止**：在 Code 未达 Beta FCS 前，把精力花在换皮肤、玻璃组件、更多模板图。

---

### 战役 4 — 优势可见（防 KTG/STP/MFP 变摆设）

**问题**：内核在管道里，用户看不到 → 等于没有优势。

| # | 动作 | 用户可见 | 验收 |
|---|------|----------|------|
| 4.1 | **Evolution 条** | Work 任务条：KTG 命中路径数 / STP 选用技能 / MFP 第几帧 | UI 有真实数据非占位 |
| 4.2 | **同任务对比** | 第二次同类任务显示「复用技能 X，步数 −N」 | 日志 + UI 文案 |
| 4.3 | **Skills 可编辑** | Settings / 工作区 `.fnix/skills/*.md` 改完立刻影响 STP | 改 skill → 下轮工具优先级变 |
| 4.4 | **SOUL / MEMORY** | 引导页写一句「你是谁」→ 后续语气一致 | harness memory e2e |
| 4.5 | **关闭对照** | `FNIXAGENT_MODE=agent_only` 时提示「进化关闭，质量可能下降」 | status 字段可测 |

**完成定义**：演示 3 分钟能讲清「Fnix 和 Cursor 不一样」且**屏幕上有证据**。

---

### 战役 5 — 上下文与索引（缩小大仓差距）

| # | 动作 | 验收 |
|---|------|------|
| 5.1 | Open project 自动 index；进度条 | harness/index 事件上 UI |
| 5.2 | Code `@file` + 搜索命中优先于盲读 | FCS search 类任务 ↑ |
| 5.3 | context_budget 超限可见（裁剪提示） | mission 带 budget |
| 5.4 | sidecar 挂了仍可工作（已有降级）→ UI 标明「降级模式」 | doctor 黄灯 |

---

### 战役 6 — 发布、口碑与增长

| # | 动作 | 验收 |
|---|------|------|
| 6.1 | `v0.9.0-beta` Release + 一页「5 分钟上手」 | 外链可装 |
| 6.2 | 演示视频：BYOK → Work 周报 → Code Accept | README 置顶 |
| 6.3 | 公开 FCS 分数板（可选） | 诚实展示，建立信任 |
| 6.4 | Issue 模板：「任务失败请贴 benchmark 报告」 | 反馈可复现 |

---

## 4. 90 天落地排期（建议）

### Phase 0（第 1–2 周）— 止血 + 闸门

1. 修端口/代理单一来源；UI 全链路必绿  
2. FCS smoke 进 CI（fail 则红）  
3. 首次引导 MVP（Key + 测连通 + 选文件夹）  
4. Craft 写盘契约（artifacts 前缀）  

**出口**：陌生开发者 `pnpm doctor && pnpm dev` 跑通；smoke hard_pass ≥ 5/9。

### Phase 1（第 3–5 周）— 「能完成工作」

1. Code：产物清单 + heal + test_gen → smoke ≥ **7/9**，FCS ≥ **75**  
2. Work：10 黄金场景 ≥ 8/10  
3. Evolution 条可见  
4. Windows Release 内测包  

**出口**：对内宣称 Beta；对外「可用的本机 Work+Code」。

### Phase 2（第 6–9 周）— 「像产品」

1. Tauri 托管进程 + 首包公开  
2. Results / Review UX 打磨  
3. Skills + MEMORY 引导  
4. FCS 100 任务周报  

**出口**：路径 A 用户无需 clone。

### Phase 3（第 10–12 周）— 「发挥优势」

1. KTG/MFP 二次任务加速可演示  
2. 索引体验 + `@file`  
3. FCS ≥ 85（smoke）；选跑 500+  
4. 对比页诚实发布（Cursor/Trae/Fnix）  

**出口**：可讲「顶级本机工作台」叙事且指标支撑。

---

## 5. 组织方式：每个功能必须带「三件套」

```text
设计（docs） + 实现（src/apps） + 验收（tests/scripts/benchmark）
缺一 → 不算完成；只写 docs → 叫摆设，PR 拒绝合并。
```

| 类型 | 强制验收 |
|------|----------|
| Work 能力 | `e2e-work-modes` 或 golden 场景 |
| Code 能力 | FCS seed 或 `e2e-code-projects` |
| 系统能力 | `/api/v1/benchmark/run` 对应 stage |
| UI 能力 | Playwright 或手动清单（写入 PR） |
| 「进化」能力 | UI 可见字段 + status JSON 断言 |

---

## 6. 防摆设法则（写进评审）

1. **用户路径优先于架构洁癖** — 开箱 > 新抽象层  
2. **分数优先于截图** — FCS / 全链路分不动，不合并大 UI  
3. **主路径挂载** — KTG/STP/MFP 必须影响 `/work/stream` 的工具选择或步数，禁止只打 log  
4. **失败可诊断** — 任何红灯 → Diagnostics / doctor 有下一步  
5. **默认安全** — Code 默认 Preview；Craft 沙箱在 artifacts  
6. **一个季度一个叙事** — 本季叙事：「本机 BYOK 工作台，Work 交文件，Code 审完再改」；不并行十个方向  

---

## 7. 技术落点清单（直接对应仓库）

| 战役 | 主要落点 |
|------|----------|
| 开箱 | `apps/desktop-tauri` runtime、`apps/workbench` onboarding、`cli/doctor.py`、`vite`/`fnixBridge` 基址 |
| Work | `services/work_pipeline.py`、`work_agent.py`、`WorkResults.tsx`、`benchmarks/work/`（新建） |
| Code | `core/code/agent.py`、heal、`benchmarks/code/seed`、`run-code-benchmark.py` |
| 优势可见 | `work_pipeline` evolution 事件、`WorkTaskBar`、`harness/memory`、skills_loader |
| 索引 | `fnix-local`、`local_bridge`、`local_context` |
| 评估 | `core/benchmark/*`、`FullChainBenchmarkPanel`、CI workflow |

---

## 8. 资源聚焦建议（若人手有限）

**只做三件事也能成：**

1. **开箱**（引导 + 托管进程 + 一个 Windows 包）  
2. **Code FCS smoke ≥ 7/9**（否则无法对标 Cursor/Codex）  
3. **Work 10 黄金场景 ≥ 8/10**（否则无法对标 Trae Work）  

其余（玻璃 UI、千级任务生成、姊妹 Rust 大重构）全部降级为 P2。

---

## 9. 成功时的产品形态（用户故事）

```text
小王下载 Fnix.exe
  → 粘贴 DashScope Key，点「测试连接」绿
  → 打开「项目文件夹」
  → Work / Craft：「做一份本周销售汇总 xlsx」→ Results 打开文件
  → 切 Code：「subtract 用了加法，修好并补测试」→ Review Accept → 本地 pytest 过
  → Settings → 全链路测试 98 分；FCS smoke 8/9
  → 他不知道什么是 agentd，也不需要知道
```

这就是「真正发挥优势、设计不是摆设」的完成态。

---

## 10. 下一步（立即执行的第一刀）

建议按此顺序开工（不发散）：

1. **API 基址统一 + 引导向导 MVP**（战役 1.1–1.3）  
2. **Code 产物清单 + heal**（战役 3.2–3.3），冲 smoke 7/9  
3. **Work artifacts 契约 + 3 个黄金场景**（战役 2.1–2.2）  
4. **Evolution 条接真实事件**（战役 4.1）  

每完成一项：跑全链路 + FCS smoke + 对应 e2e，把分数写进 PR 描述。

---

## 11. Phase 0 落地进度（2026-07-19）

| 项 | 状态 | 证据 |
|----|------|------|
| API 基址统一 | ✅ | `fnixBridge` / `vite.config` 默认 `8003`；`.env.example` |
| 首次引导 MVP | ✅ | `OnboardingWizard`；无 Key 时弹出 |
| Settings 测连通 | ✅ | `testHarnessLlm`（修 OaiSettings 参数） |
| Code heal 不中断 | ✅ | `chat_agent` 单步失败 → continue → heal |
| 缺冒号 auto-fix | ✅ | `_edit_fallback` |
| 产物清单 / preview 编译 | ✅ | `_missing_deliverables` + `_preview_compile_check` |
| Code 勿写 artifacts | ✅ | prompt + `_normalize_code_target` |
| Work artifacts 契约 | ✅ | prompt + **强制改写** `coerce_craft_artifact_path` / office `_resolve` |
| Work 黄金 e2e（3） | ✅ | **3/3 PASS**（`qwen3.7-plus`，agentd `:8012`） |
| Evolution 条 | ✅ | `normalize_evolution_event` 合并快照；前端 `setEvolution` merge |
| LLM 错误透传 | ✅ | 额度/403 原文进 stream error（不再只显示「LLM 调用失败」） |
| Doctor 开箱 | ✅ | `cli/doctor.py` + `fnix-doctor.mjs` 探测 `/health` 与端口对齐 |
| 全链路（无 LLM） | ✅ | **100 / hard_pass=True** |
| FCS smoke（Phase 1） | ✅ | **FCS 99.25 · hard_pass 100%（8/8）** — `reports/fcs-*-phase1a.*` |
| FCS Beta 门槛 | ✅ | 已超过 hard_pass ≥70%、FCS ≥75 |

**本轮关键修复**：Craft 写盘强制 `.fnix/artifacts/`；默认/实测模型切到有额度的 `qwen3.7-plus`；LLM 错误透传；Evolution 字段稳定；doctor 健康检查。

**下一刀**：Work 黄金扩到 10 场景；Release 开箱包；FCS 回归（同模型）。

---

*本文与 `FNIX_PRODUCT.md`、`OPEN_SOURCE_DESIGN.md`、`CODE_BENCHMARK.md`、`EVOLUTION_CORE.md` 配套；冲突时以「用户能否完成工作」+ 本节北极星指标为准。*
