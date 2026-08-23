---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'f62ae3ea-809b-4f8b-8c4b-2cb58a04583e'
  PropagateID: 'f62ae3ea-809b-4f8b-8c4b-2cb58a04583e'
  ReservedCode1: '7cc60696-df36-4dff-ba53-010d3723dcc9'
  ReservedCode2: '7cc60696-df36-4dff-ba53-010d3723dcc9'
---

# 二轮深度调研报告

> 调研日期：2026-08-24
> 调研范围：OpenHands / SWE-agent / Aider / Cline / AutoGPT / Cursor
> 聚焦：Heal 修复循环文件版本管理 · 前端流式 UX 空状态 · 审查层完整性检查

---

## 一、Heal 修复循环的文件版本管理

### 1.1 各项目方案对比

#### 1.1.1 OpenHands — 事件流驱动 + 状态持久化（无显式 heal 循环）

OpenHands 的核心架构与 FnixAgent 有本质区别：它**没有显式的 plan → execute → review → heal 循环**，而是采用 **AgentController + 事件流（EventStream）+ step() 驱动** 的模式。

**关键机制**（源码级分析）：

1. **AgentController 主循环**（`openhands/controller/agent_controller.py`）：
   - 通过 `_step()` 方法逐步驱动 Agent 前进，每一步都是 **LLM 生成 Action → Runtime 执行 → 返回 Observation** 的闭环
   - 没有独立的 "heal" 阶段——如果 LLM 生成了不完整的代码，它会在后续 step 中自行修正（因为 LLM 能看到上一步的 Observation 反馈）
   - `max_iterations` 控制最大步数，`StuckDetector` 检测循环卡死

2. **文件编辑的版本管理**：
   - 每次文件操作（`FileEditAction`）都是**基于磁盘当前状态的原子操作**
   - Runtime 执行 `FileEditAction` 时，先读取当前文件内容，再应用变更
   - **不存在多版本拼接问题**——因为每次编辑的基准是磁盘最新状态，而非内存中的历史版本
   - 事件流记录所有操作历史，但审查时看的是磁盘最终状态

3. **状态持久化**：
   - `State` 对象持久化到 `FileStore`，包含 `iteration_flag`、`budget_flag`、`metrics` 等
   - 支持从 checkpoint 恢复（`initial_state` 参数）

**核心设计理念**：**Agent 自己决定下一步做什么**，而非外部循环强制 heal。LLM 看到 Observation（如编译错误）后，自己决定是 edit 还是 rewrite。

#### 1.1.2 SWE-agent — ACI 命令化编辑 + 语法即时校验

SWE-agent 的 ACI（Agent-Computer Interface）设计是文件编辑版本管理的典范：

**关键机制**：

1. **文件编辑命令**（源码 `sweagent/tools/edit_tool.py` 等）：
   - `str_replace <path> --old_str <old> --new_str <new>`：**精确字符串替换**，old_str 必须在文件中唯一匹配
   - `create <path> --file_text <content>`：创建新文件
   - `view <path> --view_range <start> <end>`：查看文件指定行范围
   - `insert <path> --line <n> --text <content>`：在指定行插入

2. **即时语法校验**：
   - 每次 `str_replace` 或 `create` 后，**自动运行语法检查**（py_compile 或对应语言的 linter）
   - 如果语法错误，**立即返回错误给 Agent**，Agent 在下一步修复
   - 这是一种**隐式 heal**——不是外部循环，而是 Agent 看到错误后自行修正

3. **窗口化管理**：
   - `set_window_lines <start> <end>`：设置当前可见行范围
   - Agent 始终基于**当前窗口内的内容**做编辑，不会看到过时版本
   - 编辑后窗口自动跟随变更点，确保 Agent 看到的是最新状态

4. **版本管理策略**：
   - **无版本快照**——磁盘文件就是唯一真相源
   - 每次编辑前 `view` 确认当前内容，编辑后 `view` 确认结果
   - 如果 `str_replace` 的 old_str 匹配多处，报错要求 Agent 提供更多上下文使其唯一

**核心设计理念**：**编辑即状态**——磁盘文件始终是最新版本，Agent 必须先看到当前内容才能编辑。

#### 1.1.3 Aider — 多策略编辑 + Git 原子提交

Aider 是终端 AI 编程工具中文件编辑准确性的标杆：

**关键机制**：

1. **多种编辑策略**（`aider/coders/` 目录）：
   - `editblock_coder.py`（edit_format="diff"）：**搜索/替换块**——LLM 生成 `<<<<<<< SEARCH ... ======= ... >>>>>>>` 格式的编辑块，Aider 精确匹配并替换
   - `wholefile_coder.py`（edit_format="whole"）：**全文件替换**——LLM 生成完整文件内容，直接覆盖
   - `udiff_coder.py`（edit_format="udiff"）：**统一差异格式**——LLM 生成 unified diff，Aider 应用
   - `patch_coder.py`（edit_format="patch"）：**补丁格式**

2. **editblock 的精确匹配**（`aider/editblock.py` 核心逻辑）：
   - `find_original_find_replace()`：在文件中搜索 SEARCH 块的精确位置
   - 如果匹配不到，尝试**模糊匹配**（去除空白后比较）
   - 如果仍匹配不到，报错并提示用户
   - **核心原则**：宁可报错也不模糊替换，避免错误编辑

3. **Git 原子提交**：
   - 每次成功编辑后，**自动 git commit**（可配置 `auto_commits`）
   - 这就是版本管理——每次编辑都是一个 Git commit，可以 `git diff` 查看变更
   - 如果编辑出错，`git revert` 即可回滚
   - **不存在多版本内存堆积**——磁盘 + Git 就是唯一真相源

4. **测试驱动验证**：
   - 编辑后自动运行测试（`auto_lint` + `--test` 参数）
   - 测试失败时，Aider 将错误信息反馈给 LLM，LLM 在下一轮修复
   - 这是**对话式 heal**——不是外部循环，而是 LLM 看到测试输出后自行修复

**核心设计理念**：**Git 即版本管理**——每次编辑原子提交，Git 保证版本一致性。

#### 1.1.4 Cline — Plan & Act + 增量编辑

Cline（VS Code 插件）的文件编辑机制：

**关键机制**：

1. **Plan & Act 工作流**：
   - Plan 阶段：LLM 制定计划，用户确认
   - Act 阶段：逐步执行，每步可选择 `write_to_file` 或 `replace_in_file`

2. **文件编辑操作**：
   - `write_to_file`：**全文件覆盖**——LLM 生成完整文件内容，直接写入磁盘
   - `replace_in_file`：**增量搜索替换**——LLM 生成 SEARCH/REPLACE 块，精确替换
   - 两种方式都**直接操作磁盘文件**，无内存版本

3. **版本管理**：
   - Cline 不维护内存中的文件版本——**磁盘就是唯一真相**
   - 每次编辑前，LLM 可以 `read_file` 获取当前内容
   - 编辑后，VS Code 的文件系统监听器自动更新编辑器视图

4. **多轮编辑同一文件**：
   - Cline 的做法是：**每次编辑前先 read 当前内容**，然后做增量替换
   - 如果 LLM 在同一轮中多次编辑同一文件，每次都基于磁盘最新状态
   - 不存在"多个版本拼接"的问题

**核心设计理念**：**先读后写**——每次编辑基于磁盘当前状态，避免版本冲突。

### 1.2 FnixAgent 当前问题分析

通过源码分析（`src/fnixagent/core/code/agent.py`），FnixAgent 当前的文件版本管理存在以下问题：

#### 问题 1：内存版本与磁盘版本脱节

```python
# agent.py:1697-1712 — _check_task_completeness 中的版本收集
latest_code_by_file: dict[str, str] = {}
for step in steps:
    if action not in ("write", "edit"):
        continue
    content = str(step.result.get("content") or "")
    target = (step.target or "").strip()
    if content.strip() and target:
        # 后写入的覆盖先写入的（模拟最终文件状态）
        latest_code_by_file[target] = content
```

**问题**：这里用 `step.result.content` 模拟"最终文件状态"，但在 preview 模式下文件未落盘，`step.result.content` 可能不完整。而且 heal 轮次的新步骤和旧步骤混在一个 `steps` 列表里，覆盖逻辑依赖步骤顺序，如果顺序不对就会取到错误版本。

#### 问题 2：diff 收集的多版本问题（已部分修复）

```python
# agent.py:1787-1814 — _collect_diff 的改进
# 改进：对同一文件的多次变更，只取最终版本
latest_diff_by_path: dict[str, str] = {}
for cs, _ in self._tools._diff.get_history():
    if cs.id not in id_set:
        continue
    for ch in getattr(cs, "changes", None) or []:
        path = ch.path or ""
        latest_diff_by_path[path] = diff  # 后出现的覆盖先出现的
```

**问题**：虽然用了"后覆盖前"策略，但 DiffEngine 的 `get_history()` 返回的是**每次 apply 的变更集**，如果一个文件在同一轮中被先 CREATE 后 MODIFY，`to_diff()` 生成的 diff 可能不连贯——CREATE 的 diff 从空到内容A，MODIFY 的 diff 从内容A到内容B，但最终 LLM 审查看到的是 MODIFY 的 diff（A→B），看不到 CREATE 的完整内容。

#### 问题 3：file_change 事件的前端合并问题

```typescript
// useChatFlow.ts:112-121 — mergeFileChanges
function mergeFileChanges(prev: CodeFileChange[], incoming: CodeFileChange[]): CodeFileChange[] {
  const map = new Map<string, CodeFileChange>();
  for (const ch of prev) {
    if (ch.path) map.set(ch.path, ch);
  }
  for (const ch of incoming) {
    if (ch.path) map.set(ch.path, { ...map.get(ch.path), ...ch });
  }
  return [...map.values()];
}
```

**问题**：用 `{ ...map.get(ch.path), ...ch }` 合并——后到的 change 展开覆盖先到的。但如果后来的 change 只有 `diff` 字段没有 `content` 字段，合并后会丢失 content。前端的 DiffBlock 组件可能需要 content 来渲染预览。

#### 问题 4：changeset 累积策略导致 review 混乱

```python
# agent.py:818-825 — BUG-4 修复
# 累积而非覆盖。heal/多轮 _execute 时, 阶段1(plan) 与
# 阶段2(heal) 的变更集都要保留
existing = self._task_changesets.get(task.id, [])
self._task_changesets[task.id] = existing + [i for i in new_ids if i not in seen]
```

**问题**：虽然注释说"累积而非覆盖"，但 `_collect_diff` 中又用"后覆盖前"取最终版本。这两个逻辑存在矛盾——累积了所有 changeset ID，但最终只取最后一个的 diff。如果 heal 阶段只编辑了文件A，而 plan 阶段创建了文件B，那 review 时只能看到文件A的 diff，文件B被遗漏。

### 1.3 具体改进建议（含代码示例）

#### 建议 1：引入"磁盘即真相源"原则（高优先级）

**核心思路**：review 和 completeness 检查时，不从 step.result 或 DiffEngine 历史中收集内容，而是**直接读取磁盘文件**（非 preview 模式）或**维护一个虚拟文件系统快照**（preview 模式）。

```python
# 新增：VirtualFileSystem — preview 模式下的文件状态管理
# src/fnixagent/core/code/vfs.py

from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class VirtualFileSystem:
    """Preview 模式下的虚拟文件系统 — 模拟磁盘状态。
    
    原则：每次 write 覆盖该文件的完整内容；
    每次 edit 基于当前 VFS 内容做替换；
    review/completeness 检查从 VFS 读取最终内容。
    """
    _files: dict[str, str] = field(default_factory=dict)
    
    def write(self, path: str, content: str) -> None:
        """写入完整文件内容（覆盖）。"""
        norm = path.replace("\\", "/").lstrip("./")
        self._files[norm] = content
    
    def edit(self, path: str, old_text: str, new_text: str) -> tuple[bool, str]:
        """基于当前 VFS 内容做精确替换。"""
        norm = path.replace("\\", "/").lstrip("./")
        current = self._files.get(norm, "")
        if old_text not in current:
            return False, f"old_text not found in {path}"
        # 只替换第一处匹配（与 SWE-agent str_replace 一致）
        updated = current.replace(old_text, new_text, 1)
        self._files[norm] = updated
        return True, ""
    
    def read(self, path: str) -> str:
        """读取 VFS 中的文件内容。"""
        norm = path.replace("\\", "/").lstrip("./")
        return self._files.get(norm, "")
    
    def exists(self, path: str) -> bool:
        norm = path.replace("\\", "/").lstrip("./")
        return norm in self._files
    
    def snapshot(self) -> dict[str, str]:
        """返回所有文件的当前快照（深拷贝）。"""
        return dict(self._files)
```

**在 CodingAgent 中集成**：

```python
# agent.py 改进 — _execute 中每次 write/edit 同步更新 VFS

class CodingAgent:
    def __init__(self, ...):
        # ...
        self._vfs = VirtualFileSystem()  # preview 模式的虚拟文件系统
    
    async def _execute_step(self, step: TaskStep) -> None:
        action = step.action.strip().lower()
        
        if action == "write":
            content = self._extract_source_content(step.description)
            # 同步到 VFS（无论是否 preview）
            self._vfs.write(step.target, content)
            if not preview:
                result = await self._tools.write(step.target, content)
            else:
                result = ToolResult(success=True, output={"content": content})
            
        elif action == "edit":
            old_text, new_text = self._parse_edit_payload(step.description)
            # 先在 VFS 中验证替换可行性
            ok, err = self._vfs.edit(step.target, old_text, new_text)
            if not ok:
                step.status = "failed"
                step.error = err
                return
            # 再写磁盘
            if not preview:
                result = await self._tools.edit(step.target, old_text, new_text)
```

#### 建议 2：review 阶段从 VFS/磁盘读取最终内容（高优先级）

```python
# agent.py 改进 — _check_task_completeness 从 VFS 读取

def _check_task_completeness(
    self, task: CodingTask, steps: list[TaskStep]
) -> tuple[bool, str]:
    # ...（函数名提取逻辑保持不变）...
    
    if not mentioned_funcs:
        return True, ""
    
    # 改进：从 VFS（preview）或磁盘（非 preview）读取最终内容
    # 而非从 step.result.content 拼接
    code_contents: list[str] = []
    preview = bool(getattr(self._tools, "preview_mode", False))
    
    if preview:
        # 从 VFS 读取所有 .py 文件
        for path, content in self._vfs.snapshot().items():
            if path.endswith(".py"):
                code_contents.append(content)
    else:
        # 从磁盘读取
        from pathlib import Path
        root = Path(getattr(self._tools, "_root", None) or ".")
        for req_file in self._infer_required_files(task.description):
            p = root / req_file
            if p.is_file():
                code_contents.append(p.read_text(encoding="utf-8", errors="replace"))
    
    if not code_contents:
        return True, ""
    
    all_code = "\n".join(code_contents)
    # ...（后续检查逻辑保持不变）...
```

#### 建议 3：file_change 事件合并策略改进（中优先级）

```typescript
// useChatFlow.ts 改进 — mergeFileChanges 增强合并逻辑

function mergeFileChanges(prev: CodeFileChange[], incoming: CodeFileChange[]): CodeFileChange[] {
  const map = new Map<string, CodeFileChange>();
  for (const ch of prev) {
    if (ch.path) map.set(ch.path, ch);
  }
  for (const ch of incoming) {
    if (!ch.path) continue;
    const existing = map.get(ch.path);
    if (!existing) {
      map.set(ch.path, ch);
      continue;
    }
    // 智能合并：content 优先取非空值，diff 取最新
    map.set(ch.path, {
      path: ch.path,
      action: ch.action || existing.action,
      content: ch.content ?? existing.content,  // 非空覆盖
      diff: ch.diff || existing.diff,             // 非空覆盖
      old_content: ch.old_content ?? existing.old_content,
      preview: ch.preview !== false,
    });
  }
  return [...map.values()];
}
```

#### 建议 4：heal 阶段注入当前文件状态（中优先级）

借鉴 SWE-agent 的"先读后写"原则，在 heal 计划生成时注入当前文件内容：

```python
# agent.py 改进 — _plan_heal 注入当前文件状态

async def _plan_heal(
    self, task: CodingTask, failure_notes: str, *, todos_block: str = ""
) -> list[TaskStep]:
    # ...（原有逻辑）...
    
    # 新增：注入当前文件状态（VFS 快照），让 LLM 看到完整文件而非 diff 片段
    vfs_snapshot = self._vfs.snapshot()
    if vfs_snapshot:
        file_context = "\n\n".join(
            f"--- {path} ---\n{content}" 
            for path, content in vfs_snapshot.items()
        )
        messages.append({
            "role": "system",
            "content": f"当前文件状态（请基于此修复，不要重写已有内容）：\n{file_context[:8000]}",
        })
    
    # ...（原有 user message 逻辑）...
```

---

## 二、前端流式 UX 空状态设计

### 2.1 各项目方案对比

#### 2.1.1 OpenHands — 事件驱动的实时状态更新

OpenHands 前端（React + TypeScript + Vite）采用**事件流订阅**模式：

- **状态变更事件**：`AgentStateChangedObservation` 实时推送到前端，状态包括 `RUNNING`、`IDLE`、`PAUSED`、`AWAITING_USER_INPUT`、`FINISHED`、`ERROR`、`LOADING`
- **动作事件**：每个 Action（如 `CmdRunAction`、`FileEditAction`）都有对应的前端展示卡片
- **观察事件**：每个 Observation（命令输出、文件操作结果）实时显示
- **空状态处理**：OpenHands 不存在"Connecting"长等待问题——因为它的**第一个事件是 `MessageAction`（用户消息确认）**，紧接着是 Agent 的第一个 Action。LLM 思考期间，前端显示 Agent 的"thinking"状态（从 Action 的 `thought` 字段提取）

**关键设计**：前端永远有内容显示——要么是用户消息，要么是 Agent 的 thinking/action/observation。不存在"发送后 30s 空白"的情况，因为 AgentController 在 LLM 响应前就发布了 `AgentStateChangedObservation(RUNNING)` 事件。

#### 2.1.2 Cline — 计时器 + API 请求状态指示

Cline（VS Code 插件）的等待状态设计：

- **API 请求计时器**：发送请求后启动计时器，显示"API 请求已耗时 Xs"
- **思维链展示**：LLM 的 `<thinking>` 标签内容实时流式展示在聊天界面
- **工具执行动画**：每个工具调用（read_file、write_to_file 等）有独立的进度指示
- **逐步确认**：Plan & Act 模式下，每个步骤执行前显示"等待用户确认"状态

**关键设计**：Cline 不会让用户盯着空白等待——它显示**计时器**让用户知道"系统在工作"，同时展示 LLM 的 thinking 内容。即使 LLM 30s 不输出，用户也看到计时器在走。

#### 2.1.3 Cursor — 分阶段状态展示

Cursor 的连接状态 UX 设计：

- **Composer 模式**：发送后立即显示"Thinking..."状态，伴随微妙的脉冲动画
- **Agent 模式**：分阶段显示——"分析需求 → 搜索代码 → 生成方案 → 应用变更"，每个阶段有对应的图标和文字
- **代码生成中**：流式展示生成的代码 diff，用户可以实时看到变更
- **长时间等待**：超过 10s 后显示"这可能需要一些时间..."的柔和提示

**关键设计**：Cursor 将"等待"拆分为**有意义的阶段标签**，而非笼统的"Connecting"。

#### 2.1.4 ChatGPT Code Interpreter — 分析中状态

ChatGPT 的等待状态设计：

- **"Analyzing"**：代码分析阶段显示脉冲动画 + "Analyzing..."文字
- **"Working"**：代码执行阶段显示旋转图标 + "Working..."文字
- **流式输出**：代码执行结果逐步流式展示
- **无空白期**：每个阶段切换都有过渡动画，不会出现完全空白的状态

### 2.2 最佳实践总结

综合以上项目，前端流式 UX 空状态的最佳实践是：

| 实践 | 说明 | 采用项目 |
|------|------|----------|
| **1. 立即反馈** | 发送后立即显示状态（不等后端响应） | OpenHands, Cline, Cursor |
| **2. 分阶段标签** | 用有意义的阶段标签替代"Connecting" | Cursor, OpenHands |
| **3. 计时器** | 显示已耗时秒数，让用户知道系统在工作 | Cline |
| **4. 微动画** | 脉冲/旋转动画暗示"系统在思考" | Cursor, ChatGPT |
| **5. 预设期望** | 超过阈值后显示"可能需要一些时间" | Cursor |
| **6. 事件驱动** | 每个后端事件都触发前端状态更新 | OpenHands |
| **7. 永不空白** | 前端永远有内容（thinking/动画/计时器） | 所有项目 |

### 2.3 FnixAgent 改进建议

#### 当前问题

FnixAgent 当前在 `useChatFlow.ts:697` 设置 `setStatus("正在连接…")`，然后等待后端 NDJSON 流式响应。如果后端 LLM 调用耗时 30s，用户会一直看到"正在连接…"状态。

`ThinkingBlock.tsx` 有动画（`Loader2 spin`），但只在收到 `thinking` 事件后才会渲染。在第一个事件到达前，用户只看到 `WorkTaskBar` 中的 `"正在连接…"` 状态文本。

#### 建议 1：引入分阶段状态 + 计时器（高优先级）

```typescript
// 新增：useStreamStatus.ts — 流式状态管理 hook

import { useEffect, useRef, useState } from "react";

export type StreamPhase = 
  | "connecting"    // 正在连接后端
  | "thinking"      // LLM 思考中
  | "planning"      // 生成计划
  | "executing"     // 执行中
  | "reviewing"     // 审查中
  | "healing"       // 修复中
  | "done"          // 完成
  | "error";        // 错误

const PHASE_LABELS: Record<StreamPhase, string> = {
  connecting: "正在连接…",
  thinking: "正在思考…",
  planning: "正在规划…",
  executing: "正在执行…",
  reviewing: "正在审查…",
  healing: "正在修复…",
  done: "完成",
  error: "出错",
};

export function useStreamStatus(status: string | null, streaming: boolean) {
  const [phase, setPhase] = useState<StreamPhase>("connecting");
  const [elapsed, setElapsed] = useState(0);
  const startTime = useRef<number | null>(null);
  const timerRef = useRef<number | null>(null);

  // 从后端 status 字符串推断 phase
  useEffect(() => {
    if (!streaming) {
      setElapsed(0);
      startTime.current = null;
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    if (startTime.current === null) {
      startTime.current = Date.now();
      timerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - (startTime.current || Date.now())) / 1000));
      }, 1000);
    }
    
    // 从 status 推断 phase
    const s = (status || "").toLowerCase();
    if (s.includes("connect")) setPhase("connecting");
    else if (s.includes("think")) setPhase("thinking");
    else if (s.includes("plan")) setPhase("planning");
    else if (s.includes("execut") || s.includes("run")) setPhase("executing");
    else if (s.includes("review")) setPhase("reviewing");
    else if (s.includes("heal")) setPhase("healing");
    else if (!status) setPhase("connecting");  // 无状态时默认连接中
    else setPhase("thinking"); // 有状态但未匹配时默认思考中
    
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [status, streaming]);

  // 超过 10s 显示柔和提示
  const longWait = elapsed >= 10;
  const label = PHASE_LABELS[phase];
  
  return { phase, label, elapsed, longWait };
}
```

#### 建议 2：WorkTaskBar 集成计时器和分阶段标签

```tsx
// WorkTaskBar.tsx 改进 — 添加计时器和长等待提示

import { useStreamStatus } from "./useStreamStatus";

export function WorkTaskBar({
  // ...原有 props
  status,
  streaming,
}: Props) {
  const { phase, label, elapsed, longWait } = useStreamStatus(status, streaming);
  
  // ...原有逻辑...
  
  return (
    <div className="wb-task-bar" aria-live="polite">
      <div className="wb-task-top">
        {/* ...原有内容... */}
        {streaming ? (
          <span className="wb-task-live">
            <i className="wb-pulse-dot" />  {/* 脉冲动画点 */}
            {label}
            {elapsed > 0 && <span className="wb-elapsed">{elapsed}s</span>}
          </span>
        ) : null}
      </div>
      {/* ...步骤条... */}
      {streaming && longWait && phase === "connecting" ? (
        <div className="wb-task-hint">
          正在连接后端服务，这可能需要一些时间…
        </div>
      ) : null}
      {status ? <div className="wb-task-status">{status}</div> : null}
    </div>
  );
}
```

#### 建议 3：CSS 脉冲动画

```css
/* WorkTaskBar.css 新增 */

.wb-pulse-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--fnix-primary, #3b82f6);
  animation: fnix-pulse 1.5s ease-in-out infinite;
  margin-right: 6px;
  vertical-align: middle;
}

@keyframes fnix-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.8); }
}

.wb-elapsed {
  color: var(--fnix-text-dim, #999);
  font-size: 11px;
  margin-left: 4px;
  font-variant-numeric: tabular-nums;
}

.wb-task-hint {
  font-size: 12px;
  color: var(--fnix-text-dim, #999);
  padding: 4px 0;
  font-style: italic;
}

@media (prefers-reduced-motion: reduce) {
  .wb-pulse-dot { animation: none; opacity: 0.6; }
}
```

#### 建议 4：发送后立即插入"思考中"占位 block

```typescript
// useChatFlow.ts 改进 — send 函数中发送后立即插入 thinking block

const send = useCallback(async (text: string, attachments?: ChatAttachment[]) => {
  // ...原有逻辑...
  
  setStatus("正在连接…");
  useRunStore.getState().start("正在连接…");
  
  // 新增：立即在 assistant 消息中插入 thinking block
  // 让用户马上看到"正在思考"的反馈，而非空白
  const initialBlock: StructuredBlock = {
    kind: "thinking",
    content: "正在分析你的需求…",
    isStreaming: true,
    isComplete: false,
  };
  commitMessages(
    messagesRef.current.map((m) =>
      m.id === assistantId 
        ? { ...m, blocks: [initialBlock] } 
        : m
    )
  );
  
  // ...后续流式逻辑...
```

---

## 三、审查层完整性检查设计

### 3.1 各项目方案对比

#### 3.1.1 OpenHands — 无显式完整性检查

OpenHands **没有**类似 FnixAgent 的"从任务描述提取函数名 → 检查代码中是否有 def"的完整性检查。它的设计哲学是：

- **LLM 自我验证**：Agent 看到 Observation（编译/测试结果）后自行判断是否完成
- **测试驱动**：如果用户提供了测试用例，Agent 运行测试通过即为完成
- **AgentFinishAction**：LLM 自己决定何时发出 `AgentFinishAction` 结束任务
- **StuckDetector**：检测 Agent 是否陷入循环（反复执行相同操作），而非检查代码完整性

**没有 AST 解析或函数名提取**——OpenHands 信任 LLM + 测试结果的组合验证。

#### 3.1.2 SWE-agent — 语法检查 + 测试验证

SWE-agent 的任务完成验证机制：

1. **即时语法检查**：
   - 每次 `str_replace` 或 `create` 后，自动运行语法检查
   - 语法错误立即返回给 Agent，Agent 在下一步修复
   - 这是一种**分布式验证**——不是最后统一检查，而是每步即时验证

2. **测试运行验证**：
   - SWE-agent 的任务是修复 GitHub Issue，所以验证方式是**运行项目的测试套件**
   - `python -m pytest <test_file>` 运行测试
   - 测试通过即认为任务完成

3. **self_eval 机制**（可选）：
   - 部分配置支持 `self_eval`：LLM 自己评估修改是否解决了问题
   - 但这不是默认行为，需要配置开启

4. **无函数名提取**：
   - SWE-agent 不从 Issue 描述中提取函数名
   - 它依赖测试套件验证——如果测试通过，说明所有必要函数都已实现

#### 3.1.3 Aider — 测试驱动 + Git diff 审查

Aider 的验证机制：

1. **自动测试**：
   - `auto_lint`：编辑后自动运行 linter（如 flake8, eslint）
   - `--test` 参数：编辑后自动运行测试命令（用户配置）
   - 测试失败时，Aider 将失败信息反馈给 LLM，LLM 在下一轮修复

2. **Git diff 审查**：
   - 每次编辑后自动 `git commit`
   - 用户可以随时 `git diff` 查看变更
   - 没有自动的"函数完整性检查"——依赖用户审查 diff

3. **无 AST 解析**：
   - Aider 不解析 AST 来验证函数完整性
   - 它依赖**测试 + linter** 的组合验证

#### 3.1.4 AutoGPT — LLM 自我评估

AutoGPT 的任务完成判定：

1. **LLM 判定**：
   - AutoGPT 让 LLM 自己判断任务是否完成
   - 每轮循环后，LLM 生成一个 "task_complete" 判断
   - 如果 LLM 认为完成，输出 `{"thoughts": {"text": "任务完成"}, "command": {"name": "task_complete"}}`

2. **无代码级验证**：
   - AutoGPT 不是专门的编码 Agent，没有 AST 解析或编译检查
   - 它依赖 LLM 的自我评估——这容易产生"过早宣布完成"的问题

3. **改进方向**：
   - 社区有讨论引入"验证步骤"——让另一个 LLM 实例检查任务是否真的完成
   - 类似 FnixAgent 的 CriticAgent 独立审查

### 3.2 FnixAgent 当前问题分析

FnixAgent 的完整性检查（`_check_task_completeness`，agent.py:1620-1743）存在以下问题：

#### 问题 1：正则提取函数名的误检

```python
# agent.py:1644-1691 — 正则提取逻辑
sig_pattern = _re.compile(r"`([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)`")
def_pattern = _re.compile(r"\bdef\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")
call_pattern = _re.compile(
    r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\((?:[a-zA-Z_][a-zA-Z0-9_]*\s*(?:,\s*[a-zA-Z_][a-zA-Z0-9_]*)*)\)"
)
```

**问题**：
- `call_pattern` 过于宽泛，会匹配到 "print(x)"、"test()" 等非任务要求的函数名
- 虽然有 `_STOPWORDS` 过滤，但无法覆盖所有情况
- 任务描述中 "Identity" "Rules" 等大写开头的词被排除（line 1689-1690），但如果任务确实要求实现 `Identity` 类，会被漏检

#### 问题 2：检查模式不区分语言

```python
# agent.py:1725-1730 — 检查模式
patterns = [
    rf"\bdef\s+{_re.escape(func_name)}\s*\(",
    rf"\bclass\s+{_re.escape(func_name)}\b",
    rf"\b{_re.escape(func_name)}\s*=\s*lambda",
    rf"\b{_re.escape(func_name)}\s*=\s*def",
]
```

**问题**：只检查 Python 语法的 `def`/`class`/`lambda`。如果任务要求用 TypeScript 写函数（如 `add(a, b)`），这些模式都匹配不到。FnixAgent 的 bench 测试中有 Angular/React 任务，这些任务用 TypeScript，正则检查完全失效。

#### 问题 3：检查内容来源不可靠

```python
# agent.py:1699-1712 — 从 step.result.content 收集代码
latest_code_by_file: dict[str, str] = {}
for step in steps:
    content = str(step.result.get("content") or "")
    target = (step.target or "").strip()
    if content.strip() and target:
        latest_code_by_file[target] = content
```

**问题**：`step.result.content` 在 edit 操作时可能只有变更片段而非完整文件内容。如果 LLM 用 edit 操作添加了 `subtract` 函数，`step.result.content` 可能只有 `"old_text: ...new_text: def subtract(a, b): return a - b"`，而非完整的 calc.py 文件。

### 3.3 具体改进建议（含代码示例）

#### 建议 1：用 AST 解析替代正则检查（高优先级，Python 任务）

```python
# 新增：src/fnixagent/core/code/completeness.py

import ast
import re
from typing import NamedTuple

class CompletenessResult(NamedTuple):
    passed: bool
    notes: str
    missing: list[str]

def check_completeness_ast(
    task_description: str,
    code_contents: dict[str, str],  # {file_path: content}
) -> CompletenessResult:
    """用 AST 解析检查代码完整性（Python 专用）。
    
    比正则更可靠：
    1. 精确提取所有函数/类定义名
    2. 不受注释/字符串中的 "def" 干扰
    3. 能检测嵌套定义
    """
    # 1. 从任务描述提取要求的函数/类名
    required_names = _extract_required_names(task_description)
    if not required_names:
        return CompletenessResult(True, "", [])
    
    # 2. 用 AST 解析收集所有已定义的函数/类名
    defined_names: set[str] = set()
    for path, content in code_contents.items():
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    defined_names.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    defined_names.add(node.name)
        except SyntaxError:
            continue  # 语法错误由编译检查单独报告
    
    # 3. 检查缺失
    missing = sorted(required_names - defined_names)
    if missing:
        return CompletenessResult(
            False,
            f"任务要求的函数/类未实现: {', '.join(missing)}。"
            "请确保所有要求的函数都有对应的 def/class 定义。",
            missing,
        )
    return CompletenessResult(True, "", [])


def _extract_required_names(task_description: str) -> set[str]:
    """从任务描述提取要求的函数/类名 — 改进版。
    
    策略优先级：
    1. 反引号包裹的函数签名 `func_name(args)` — 最可靠
    2. def func_name( — 任务描述中直接写了 def
    3. class ClassName — 任务描述中直接写了 class
    4. 明确的 "实现 X 函数" / "创建 X 类" 中文模式
    """
    text = task_description or ""
    names: set[str] = set()
    
    # 模式1: `func_name(args)` — 反引号包裹
    for m in re.finditer(r"`([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)`", text):
        names.add(m.group(1))
    
    # 模式2: def func_name( — 直接写了 def
    for m in re.finditer(r"\bdef\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", text):
        names.add(m.group(1))
    
    # 模式3: class ClassName — 直接写了 class
    for m in re.finditer(r"\bclass\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", text):
        names.add(m.group(1))
    
    # 模式4: 中文模式 "实现 add 函数" / "创建 Calculator 类"
    for m in re.finditer(r"(?:实现|创建|编写|定义)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:函数|方法|类)", text):
        names.add(m.group(1))
    
    # 模式5: "add(a, b)" 不带反引号但带参数 — 仅在前4种无结果时使用
    if not names:
        for m in re.finditer(
            r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\((?:[a-zA-Z_][a-zA-Z0-9_]*\s*(?:,\s*[a-zA-Z_][a-zA-Z0-9_]*)*)\)",
            text,
        ):
            name = m.group(1)
            # 过滤通用词
            if name.lower() in {"print", "test", "assert", "return", "range", "len", "type", "isinstance"}:
                continue
            names.add(name)
    
    # 过滤编程关键字
    STOPWORDS = {"write", "read", "edit", "compile", "test", "import", "from", "print"}
    return {n for n in names if n.lower() not in STOPWORDS and len(n) >= 2}
```

#### 建议 2：多语言支持 — TypeScript/JavaScript 检查（中优先级）

```python
# completeness.py 续 — TypeScript/JavaScript 支持

def check_completeness_ts(
    task_description: str,
    code_contents: dict[str, str],
) -> CompletenessResult:
    """TypeScript/JavaScript 完整性检查。
    
    不用 AST（TS 的 AST 需要额外依赖），用增强正则：
    1. function funcName(
    2. const funcName = (
    3. const funcName = function
    4. class ClassName
    5. funcName = (params) =>  (箭头函数)
    """
    required_names = _extract_required_names(task_description)
    if not required_names:
        return CompletenessResult(True, "", [])
    
    defined_names: set[str] = set()
    for path, content in code_contents.items():
        if not path.endswith((".ts", ".tsx", ".js", ".jsx", ".vue")):
            continue
        
        # function funcName(
        for m in re.finditer(r"\bfunction\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(", content):
            defined_names.add(m.group(1))
        
        # const/let/var funcName = ( | function
        for m in re.finditer(r"\b(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:\(|function)", content):
            defined_names.add(m.group(1))
        
        # class ClassName
        for m in re.finditer(r"\bclass\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\b", content):
            defined_names.add(m.group(1))
        
        # funcName(params): return_type {  — 类方法
        for m in re.finditer(r"\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{", content):
            defined_names.add(m.group(1))
    
    missing = sorted(required_names - defined_names)
    if missing:
        return CompletenessResult(
            False,
            f"任务要求的函数/类未实现: {', '.join(missing)}。",
            missing,
        )
    return CompletenessResult(True, "", [])


def check_completeness(
    task_description: str,
    code_contents: dict[str, str],
) -> CompletenessResult:
    """多语言完整性检查入口。"""
    # 根据文件扩展自动选择检查器
    has_py = any(p.endswith(".py") for p in code_contents)
    has_ts = any(p.endswith((".ts", ".tsx", ".js", ".jsx", ".vue")) for p in code_contents)
    
    results: list[CompletenessResult] = []
    if has_py:
        results.append(check_completeness_ast(task_description, code_contents))
    if has_ts:
        results.append(check_completeness_ts(task_description, code_contents))
    
    if not results:
        return CompletenessResult(True, "", [])
    
    # 合并结果：任一语言检查失败即失败
    all_missing: list[str] = []
    all_notes: list[str] = []
    for r in results:
        if not r.passed:
            all_missing.extend(r.missing)
            all_notes.append(r.notes)
    
    if all_missing:
        return CompletenessResult(False, " ".join(all_notes), all_missing)
    return CompletenessResult(True, "", [])
```

#### 建议 3：LLM 辅助验证 — 混合策略（中优先级）

当 AST/正则检查通过但 LLM 审查有疑虑时，引入"二次确认"机制：

```python
# agent.py 改进 — _review 中的分层验证

async def _review(self, task: CodingTask, steps: list[TaskStep]) -> tuple[bool, str]:
    # ...（原有逻辑）...
    
    # 3. 完整性检查：用改进的 AST/多语言检查
    # 从 VFS/磁盘读取最终内容，而非 step.result
    code_contents = self._collect_final_code()  # 新方法：从 VFS 或磁盘读取
    completeness_result = check_completeness(task.description, code_contents)
    if not completeness_result.passed:
        notes_parts.append(completeness_result.notes)
    
    # 4. LLM 审查（仅在前3步通过时运行，避免浪费 token）
    diff_text = self._collect_diff(task.id)
    llm_passed = True
    if diff_text and compile_passed and test_passed and not missing and completeness_result.passed:
        llm_passed, llm_notes = await self._llm_review(task, diff_text)
        # ...（原有逻辑）...
    
    # 5. 综合判定
    passed = (
        compile_passed
        and test_passed
        and llm_passed
        and completeness_result.passed
        and not failed
        and not missing
    )
    return passed, "\n".join(notes_parts)

def _collect_final_code(self) -> dict[str, str]:
    """收集最终代码内容 — 从 VFS（preview）或磁盘（非 preview）读取。"""
    preview = bool(getattr(self._tools, "preview_mode", False))
    if preview:
        return self._vfs.snapshot()
    
    # 非 preview：从磁盘读取
    from pathlib import Path
    root = Path(getattr(self._tools, "_root", None) or ".")
    code_contents: dict[str, str] = {}
    for path_str in self._vfs.snapshot().keys():
        p = root / path_str
        if p.is_file():
            code_contents[path_str] = p.read_text(encoding="utf-8", errors="replace")
    return code_contents
```

---

## 四、综合优化路线图（按优先级排序）

### P0 — 立即落地（1-2 天）

| 序号 | 改进项 | 影响范围 | 预期效果 |
|------|--------|----------|----------|
| P0-1 | 引入 VirtualFileSystem，preview 模式下管理文件最终状态 | `agent.py` + 新增 `vfs.py` | 消除多版本拼接问题，review/completeness 检查基于唯一真相源 |
| P0-2 | `_check_task_completeness` 改用 AST 解析（Python） | `agent.py` → `completeness.py` | 消除正则误检（Identity/Rules 等非函数词），精确提取函数/类定义 |
| P0-3 | review/completeness 从 VFS/磁盘读取最终内容 | `agent.py` | 不再依赖 `step.result.content` 的不可靠拼接 |
| P0-4 | 前端发送后立即插入 "thinking" 占位 block | `useChatFlow.ts` | 消除"发送后空白"体验问题 |

### P1 — 短期改进（3-5 天）

| 序号 | 改进项 | 影响范围 | 预期效果 |
|------|--------|----------|----------|
| P1-1 | 前端引入流式状态计时器 + 分阶段标签 | `useStreamStatus.ts` + `WorkTaskBar.tsx` | LLM 思考 30s 期间用户看到计时器+阶段标签 |
| P1-2 | file_change 事件合并逻辑改进 | `useChatFlow.ts` | 避免后到的 change 丢失 content 字段 |
| P1-3 | heal 阶段注入当前文件状态（VFS 快照） | `agent.py` `_plan_heal` | LLM 修复时看到完整文件而非 diff 片段 |
| P1-4 | 多语言完整性检查（TypeScript/JavaScript） | `completeness.py` | 支持 Angular/React 任务的函数完整性检查 |

### P2 — 中期优化（1-2 周）

| 序号 | 改进项 | 影响范围 | 预期效果 |
|------|--------|----------|----------|
| P2-1 | 长等待柔和提示（>10s 显示"可能需要一些时间"） | `WorkTaskBar.tsx` | 设置用户预期，减少焦虑 |
| P2-2 | LLM 辅助验证 — 分层审查策略 | `agent.py` `_review` | AST 通过后 LLM 二次确认，提高准确性 |
| P2-3 | DiffEngine 改进 — 支持 VFS 模式 | `diff.py` | preview 模式下 diff 基于 VFS 而非磁盘 |
| P2-4 | 脉冲动画 + prefers-reduced-motion 降级 | CSS | 视觉反馈增强，无障碍兼容 |

### P3 — 长期演进（后续迭代）

| 序号 | 改进项 | 影响范围 | 预期效果 |
|------|--------|----------|----------|
| P3-1 | 参考 OpenHands 事件流架构，逐步迁移到事件驱动模型 | 全局 | 消除显式 heal 循环，Agent 自主决定下一步 |
| P3-2 | 参考 SWE-agent ACI 设计，引入"先读后写"编辑协议 | `agent.py` + 前端 | 每次编辑基于磁盘最新状态，根本消除版本冲突 |
| P3-3 | 参考 Aider 多策略编辑，支持 editblock/wholefile/udiff 切换 | `agent.py` | 不同任务场景选择最优编辑策略 |

---

## 附录：各项目核心设计理念对比

| 维度 | OpenHands | SWE-agent | Aider | Cline | FnixAgent（当前） | FnixAgent（建议） |
|------|-----------|-----------|-------|-------|------------------|------------------|
| **文件版本管理** | 事件流+磁盘即真相 | ACI 命令+磁盘即真相 | Git 原子提交 | 先读后写 | step.result 内存拼接 | VFS + 磁盘即真相 |
| **heal 机制** | 无显式 heal | 无显式 heal（即时语法检查） | 对话式修复 | 无显式 heal | 外部循环 heal | 保留 heal + VFS |
| **完整性检查** | 无（信任 LLM + 测试） | 语法检查 + 测试 | linter + 测试 | 无 | 正则提取函数名 | AST 解析 + 多语言 |
| **前端空状态** | 事件驱动实时更新 | N/A（CLI 工具） | N/A（CLI 工具） | 计时器 + thinking | "正在连接…" | 分阶段标签 + 计时器 |
| **验证策略** | LLM 自主 + 测试 | 语法 + 测试 | linter + 测试 | 用户审查 | 正则 + LLM 审查 | AST + 编译 + 测试 + LLM |

---

*报告基于 OpenHands (All-Hands-AI/OpenHands)、SWE-agent (princeton-nlp/SWE-agent)、Aider (Aider-AI/aider)、Cline (cline/cline)、AutoGPT 的公开源码、文档和技术分析文章撰写。FnixAgent 的分析基于本地源码 `src/fnixagent/core/code/agent.py`、`src/fnixagent/core/code/diff.py`、`apps/workbench/src/shell/desktop/useChatFlow.ts` 等文件。*

> AI生成