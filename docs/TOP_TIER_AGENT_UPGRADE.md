# FnixAgent 顶级 Agent 架构升级方案

> 版本: 2.0 | 日期: 2026-08-17
> 基于 11 个顶级开源 Agent 项目的深度研究

---

## 一、现状评估

### 1.1 已有优势

| 模块 | 现状 | 评级 |
|------|------|------|
| KTG 知识拓扑图 | 4层固定结构 + 6类节点 + 6类边 + 权重系统 | ⭐⭐⭐⭐ |
| STP 技能协议 | 拓扑绑定 + 三级权限 + 反馈机制 | ⭐⭐⭐⭐ |
| MFP 进化飞轮 | 4阶闭环（感知→固化→反思→爬坡） | ⭐⭐⭐⭐ |
| 三层记忆 | 短期/长期/实体 + 统一管理器 | ⭐⭐⭐ |
| Agent 基类 | 4步 ReAct + 双入口（同步/流式） | ⭐⭐⭐ |
| 工具系统 | 注册/执行/并行/DAG/沙箱 | ⭐⭐⭐⭐ |

### 1.2 待提升领域

| 领域 | 问题 | 参考标杆 |
|------|------|----------|
| 记忆系统 | 缺少 Markdown 源真相 + 检索门控 | EverOS / waku-agent |
| 技能进化 | 缺少 9 维评估 + 棘轮机制 | 达尔文.skill |
| Context Engineering | 缺少 Checkpoint + Token 预算 | DeerFlow / Raven |
| 执行可观测 | 缺少 Durable Timeline | amcp |
| 主动能力 | 缺少 Proactivity 系统 | Raven |
| 并行协作 | 缺少 Concurrent Agent Teams | OpenPencil |

---

## 二、顶级架构设计

### 2.1 七层架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ⑦ 交互层 Interaction                                                    │
│     Desktop(Tauri) · CLI · IM Bridge · API · MCP Server                  │
├─────────────────────────────────────────────────────────────────────────┤
│  ⑥ 编排层 Orchestration                                                  │
│     Super Agent · Concurrent Teams · Primary/Subagent · Handoff          │
├─────────────────────────────────────────────────────────────────────────┤
│  ⑤ 自进化层 Evolution (MFP)                                              │
│     飞轮1 感知执行 · 飞轮2 知识固化 · 飞轮3 元反思 · 飞轮4 爬坡进化        │
│     + Skill Evolver (9维评估 + 棘轮 + Human-in-the-Loop)                 │
├─────────────────────────────────────────────────────────────────────────┤
│  ④ 记忆层 Memory                                                         │
│     Markdown 源真相 + SQLite 索引 + Vector 语义检索                       │
│     + Retrieval Gate (智能门控) + Consolidation (定期提炼)                │
│     + Reflection (离线进化) + Knowledge Wiki                             │
├─────────────────────────────────────────────────────────────────────────┤
│  ③ 推理层 Reasoning                                                      │
│     KTG 拓扑推理 + ReAct/Plan&Execute + Context Engineering              │
│     + Checkpoint (delta + snapshot) + Token Budget                       │
├─────────────────────────────────────────────────────────────────────────┤
│  ② 技能层 Skills (STP)                                                   │
│     Agent Skills 协议兼容 + 多级发现 + 拓扑权重驱动                       │
│     + Skill Marketplace + Auto-evolution                                 │
├─────────────────────────────────────────────────────────────────────────┤
│  ① 执行层 Execution                                                      │
│     Tool Registry + Sandbox + Durable Timeline + Hooks                   │
│     + Proactivity (Sentinel + Nudge + Scheduler)                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心设计原则

1. **Markdown-first**: 记忆以 Markdown 为源真相，索引与存储分离
2. **Retrieval Gate**: 智能判断是否需要检索，节省 Token
3. **Skill Evolution**: 9 维评估 + 棘轮机制，只保留改进
4. **Context Engineering**: Checkpoint + Token Budget，精确控制上下文
5. **Durable Execution**: 可审计的执行时间线，中断可恢复
6. **Proactivity**: Sentinel 主动观察 + Nudge 推动机制
7. **Concurrent Teams**: 空间分解 + 并行 Agent 团队

---

## 三、核心升级方案

### 3.1 记忆系统升级 (EverOS-inspired)

#### 3.1.1 三层存储架构

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Markdown 源真相 (人类可读可编辑)                    │
│  ~/.fnix/memory/                                            │
│  ├── MEMORY.md          # 策展的长期事实                      │
│  ├── HISTORY.md         # 追加式活动历史                      │
│  ├── SOUL.md            # 人格与身份                          │
│  ├── USER.md            # 用户画像                            │
│  └── knowledge/         # 知识 Wiki                          │
│      ├── topics/        # 按主题组织                          │
│      └── index.md       # 知识索引                            │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: SQLite + FTS5 (可查询)                             │
│  ~/.fnix/memory.db                                          │
│  ├── facts            # 事实表 (FTS5 全文索引)                │
│  ├── episodes         # 情景事件                              │
│  ├── entities         # 实体记忆                              │
│  └── reflections      # 反思记录                              │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Vector 语义检索 (LanceDB/FAISS)                    │
│  ~/.fnix/vectors/                                           │
│  ├── long_term        # 长期记忆向量                          │
│  ├── knowledge        # 知识库向量                            │
│  └── skills           # 技能向量                              │
└─────────────────────────────────────────────────────────────┘
```

#### 3.1.2 Retrieval Gate (智能检索门控)

```python
class RetrievalGate:
    """智能判断是否需要检索记忆。
    
    避免不必要的检索开销（waku-agent 核心设计）。
    """
    
    def should_retrieve(self, query: str, context: dict) -> bool:
        """判断是否需要检索。
        
        检索条件（满足任一即检索）：
        1. 查询包含时间/人物/地点等实体词
        2. 查询包含"记得"/"之前"/"上次"等记忆指示词
        3. 上下文缺少相关实体信息
        4. 查询复杂度 > 阈值
        
        不检索条件：
        1. 简单问候/闲聊
        2. 纯计算/格式化任务
        3. 上下文中已有充分信息
        """
        # 快速路径：简单任务不检索
        if self._is_simple_task(query):
            return False
        
        # 记忆指示词检测
        if self._has_memory_indicators(query):
            return True
        
        # 实体词检测
        if self._has_entity_keywords(query):
            return True
        
        # 上下文完整性检查
        if not self._context_sufficient(context, query):
            return True
        
        return False
```

#### 3.1.3 Memory Consolidation (定期提炼)

```python
class MemoryConsolidator:
    """定期提炼记忆事实。
    
    每 N 次对话后自动 consolidate，提取关键事实写入 MEMORY.md。
    """
    
    async def consolidate(self, session_id: str, threshold: int = 10):
        """提炼记忆。
        
        流程：
        1. 读取最近 N 条对话
        2. LLM 提取关键事实/决策/偏好
        3. 去重合并到 MEMORY.md
        4. 更新 SQLite 索引
        5. 更新向量索引
        """
        # 获取待提炼的对话
        episodes = await self._get_recent_episodes(session_id, threshold)
        
        # LLM 提取事实
        facts = await self._extract_facts(episodes)
        
        # 合并到 MEMORY.md
        await self._merge_to_memory_md(facts)
        
        # 更新索引
        await self._update_indices(facts)
```

#### 3.1.4 Reflection (离线记忆进化)

```python
class MemoryReflector:
    """离线记忆进化。
    
    定期分析记忆，合并相似项，提炼模式，更新知识 Wiki。
    """
    
    async def reflect(self):
        """执行记忆反思。
        
        流程：
        1. 聚类相似 episodes
        2. 提炼高频模式
        3. 更新 Knowledge Wiki
        4. 衰减低频记忆
        5. 生成反思报告
        """
        # 聚类相似事件
        clusters = await self._cluster_episodes()
        
        # 提炼模式
        patterns = await self._extract_patterns(clusters)
        
        # 更新知识 Wiki
        await self._update_knowledge_wiki(patterns)
        
        # 衰减低频记忆
        await self._decay_low_frequency_memories()
```

---

### 3.2 技能系统升级 (达尔文-inspired)

#### 3.2.1 9 维评估体系

```python
class SkillEvaluator:
    """技能 9 维评估器。
    
    参考达尔文.skill 的评估体系。
    """
    
    DIMENSIONS = [
        "structure_quality",      # 结构质量
        "executive_effectiveness", # 执行效果
        "failure_mode_encoding",  # 失败模式编码
        "actionable_specificity", # 可执行具体性
        "context_appropriateness", # 上下文适当性
        "edge_case_handling",     # 边界情况处理
        "resource_efficiency",    # 资源效率
        "user_feedback",          # 用户反馈
        "regression_safety",      # 回归安全性
    ]
    
    # 高风险行动黑名单（禁止出现）
    HIGH_RISK_BLACKLIST = [
        "rm -rf /",
        "DROP TABLE",
        "sudo chmod 777",
        # ... 更多
    ]
    
    async def evaluate(self, skill: Skill, trace: TraceRecord) -> SkillScore:
        """执行 9 维评估。
        
        返回：
        - 总分 (0-100)
        - 各维度分数
        - 失败模式检测
        - 改进建议
        """
        scores = {}
        for dim in self.DIMENSIONS:
            scores[dim] = await self._evaluate_dimension(skill, trace, dim)
        
        # 失败模式检测
        failure_modes = self._detect_failure_modes(trace)
        
        # 黑名单检查
        blacklist_violations = self._check_blacklist(skill)
        
        # 计算总分
        total = self._calculate_total(scores, failure_modes, blacklist_violations)
        
        return SkillScore(
            total=total,
            dimensions=scores,
            failure_modes=failure_modes,
            blacklist_violations=blacklist_violations,
            suggestions=self._generate_suggestions(scores, failure_modes),
        )
```

#### 3.2.2 棘轮机制 (Ratchet)

```python
class SkillEvolver:
    """技能进化器（棘轮机制）。
    
    只保留改进，自动回滚退步。
    """
    
    async def evolve(self, skill: Skill) -> EvolutionResult:
        """执行技能进化。
        
        流程：
        1. 基线评估（当前版本）
        2. 生成改进版本
        3. 测试改进版本
        4. 对比评估
        5. 棘轮决策：保留改进 / 回滚
        """
        # 基线评估
        baseline_score = await self.evaluator.evaluate(skill, skill.last_trace)
        
        # 生成改进版本
        improved = await self._generate_improvement(skill, baseline_score)
        
        # 测试改进版本
        test_trace = await self._test_skill(improved)
        improved_score = await self.evaluator.evaluate(improved, test_trace)
        
        # 棘轮决策
        if improved_score.total > baseline_score.total:
            # 保留改进
            await self._commit_improvement(improved, improved_score)
            return EvolutionResult(accepted=True, score_delta=improved_score.total - baseline_score.total)
        else:
            # 回滚
            return EvolutionResult(accepted=False, reason="improved_score <= baseline_score")
```

#### 3.2.3 Human-in-the-Loop 三层守关

```python
class HumanInTheLoop:
    """Human-in-the-Loop 守关机制。
    
    关键阶段强制暂停等用户确认。
    """
    
    GATES = [
        "before_high_risk_action",  # 高风险操作前
        "before_skill_evolution",   # 技能进化前
        "before_memory_deletion",   # 记忆删除前
    ]
    
    async def check_gate(self, gate: str, context: dict) -> GateResult:
        """检查守关。
        
        返回：
        - approved: 是否批准
        - reason: 原因
        - user_feedback: 用户反馈
        """
        if gate not in self.GATES:
            return GateResult(approved=True)
        
        # 暂停等待用户确认
        response = await self._wait_for_user_confirmation(gate, context)
        
        return GateResult(
            approved=response.approved,
            reason=response.reason,
            user_feedback=response.feedback,
        )
```

---

### 3.3 Context Engineering 升级 (DeerFlow-inspired)

#### 3.3.1 Checkpoint 机制

```python
class CheckpointManager:
    """上下文 Checkpoint 管理器。
    
    支持 delta + snapshot 两种模式。
    """
    
    async def create_checkpoint(self, state: AgentState, mode: str = "delta") -> Checkpoint:
        """创建 Checkpoint。
        
        delta 模式：只保存变化的部分
        snapshot 模式：保存完整状态
        """
        if mode == "delta":
            # 计算与上一个 checkpoint 的差异
            diff = self._compute_diff(state, self._last_checkpoint)
            return Checkpoint(mode="delta", data=diff, timestamp=time.time())
        else:
            # 完整快照
            return Checkpoint(mode="snapshot", data=state.to_dict(), timestamp=time.time())
    
    async def restore_checkpoint(self, checkpoint_id: str) -> AgentState:
        """恢复 Checkpoint。
        
        支持恢复到任意历史状态。
        """
        checkpoint = await self._load_checkpoint(checkpoint_id)
        
        if checkpoint.mode == "snapshot":
            return AgentState.from_dict(checkpoint.data)
        else:
            # delta 模式需要链式恢复
            return await self._apply_delta_chain(checkpoint)
```

#### 3.3.2 Token Budget

```python
class TokenBudget:
    """Token 预算管理。
    
    精确控制上下文各部分的 Token 分配。
    """
    
    # 默认预算分配
    DEFAULT_BUDGET = {
        "system_prompt": 1000,
        "memory": 2000,
        "tools": 1500,
        "history": 4000,
        "response": 2000,
    }
    
    def __init__(self, total_budget: int = 128000):
        self.total = total_budget
        self.budgets = dict(self.DEFAULT_BUDGET)
    
    def allocate(self, section: str, content: str) -> str:
        """分配 Token 预算。
        
        如果内容超出预算，自动压缩/截断。
        """
        budget = self.budgets.get(section, 1000)
        tokens = self._count_tokens(content)
        
        if tokens > budget:
            # 压缩策略
            return self._compress(content, budget)
        
        return content
    
    def _compress(self, content: str, target_tokens: int) -> str:
        """压缩内容到目标 Token 数。
        
        策略：
        1. 移除冗余空白
        2. 缩写长词
        3. 摘要长段落
        4. 截断（最后手段）
        """
        # 实现压缩逻辑
        ...
```

---

### 3.4 Durable Execution Timeline (amcp-inspired)

```python
class DurableTimeline:
    """可审计的执行时间线。
    
    每会话 2000 条事件元数据，支持中断恢复。
    """
    
    @dataclass
    class TimelineEvent:
        event_id: str
        timestamp: float
        event_type: str  # thought, action, observation, tool_call, etc.
        data: dict
        metadata: dict
    
    def __init__(self, session_id: str, max_events: int = 2000):
        self.session_id = session_id
        self.max_events = max_events
        self.events: list[self.TimelineEvent] = []
    
    def record(self, event_type: str, data: dict, metadata: dict = None):
        """记录事件。"""
        event = self.TimelineEvent(
            event_id=uuid.uuid4().hex,
            timestamp=time.time(),
            event_type=event_type,
            data=data,
            metadata=metadata or {},
        )
        self.events.append(event)
        
        # 超出上限时，压缩旧事件
        if len(self.events) > self.max_events:
            self._compress_old_events()
    
    async def export(self) -> TimelineExport:
        """导出时间线。
        
        用于审计、回放、调试。
        """
        return TimelineExport(
            session_id=self.session_id,
            events=self.events,
            duration=self.events[-1].timestamp - self.events[0].timestamp if self.events else 0,
        )
    
    async def resume_from(self, event_id: str) -> AgentState:
        """从指定事件恢复执行。
        
        支持中断后恢复。
        """
        # 找到事件位置
        idx = next(i for i, e in enumerate(self.events) if e.event_id == event_id)
        
        # 重建状态
        state = AgentState()
        for event in self.events[:idx + 1]:
            state = self._apply_event(state, event)
        
        return state
```

---

### 3.5 Proactivity 系统 (Raven-inspired)

```python
class ProactivitySystem:
    """主动能力系统。
    
    Sentinel 观察 + Nudge 推动 + 调度工作。
    """
    
    class Sentinel:
        """主动观察者。
        
        持续监控系统状态，发现需要处理的事项。
        """
        
        async def observe(self, context: dict) -> list[Observation]:
            """执行观察。
            
            观察项：
            - 未读邮件/消息
            - 日历事件提醒
            - 任务截止日期
            - 系统状态异常
            - 记忆中的待办事项
            """
            observations = []
            
            # 检查日历
            calendar_events = await self._check_calendar(context)
            observations.extend(calendar_events)
            
            # 检查任务
            task_reminders = await self._check_tasks(context)
            observations.extend(task_reminders)
            
            # 检查记忆中的待办
            todo_reminders = await self._check_memory_todos(context)
            observations.extend(todo_reminders)
            
            return observations
    
    class Nudge:
        """推动机制。
        
        在适当时机提醒用户。
        """
        
        async def should_nudge(self, observation: Observation) -> bool:
            """判断是否应该推动。
            
            条件：
            - 紧急事项（< 2 小时）
            - 用户在线且空闲
            - 距离上次推动 > 30 分钟
            """
            if observation.urgency >= Urgency.HIGH:
                return True
            
            if observation.deadline and observation.deadline < time.time() + 7200:
                return True
            
            return False
    
    class Scheduler:
        """调度工作。
        
        定时执行后台任务。
        """
        
        async def schedule(self, task: ScheduledTask):
            """调度任务。
            
            支持：
            - 一次性任务 (at)
            - 周期性任务 (every)
            - Cron 表达式 (cron)
            """
            ...
```

---

### 3.6 Concurrent Agent Teams (OpenPencil-inspired)

```python
class ConcurrentAgentTeam:
    """并行 Agent 团队。
    
    空间分解 + 并行流式生成。
    """
    
    async def execute(self, task: Task, agents: list[Agent]) -> TeamResult:
        """执行并行任务。
        
        流程：
        1. 编排器分解任务为子任务
        2. 按空间/功能分配给不同 Agent
        3. 并行执行
        4. 合并结果
        """
        # 任务分解
        subtasks = await self._decompose_task(task)
        
        # 分配给 Agent
        assignments = self._assign_to_agents(subtasks, agents)
        
        # 并行执行
        results = await asyncio.gather(*[
            agent.execute(assignment) 
            for agent, assignment in assignments
        ])
        
        # 合并结果
        return await self._merge_results(results)
    
    async def _decompose_task(self, task: Task) -> list[SubTask]:
        """分解任务。
        
        策略：
        - 空间分解（如页面不同区域）
        - 功能分解（如不同模块）
        - 依赖分解（如独立子任务）
        """
        ...
```

---

## 四、实施计划

### 4.1 优先级排序

| 优先级 | 升级项 | 工作量 | 价值 |
|--------|--------|--------|------|
| P0 | 记忆系统 Markdown-first | 中 | 高 |
| P0 | Retrieval Gate | 低 | 高 |
| P1 | Skill 9 维评估 | 中 | 高 |
| P1 | Checkpoint 机制 | 中 | 中 |
| P2 | Durable Timeline | 中 | 中 |
| P2 | Proactivity 系统 | 高 | 中 |
| P3 | Concurrent Teams | 高 | 低（当前场景少） |

### 4.2 实施步骤

#### Phase 1: 记忆系统升级 (Week 1-2)

1. 实现 Markdown 存储层
2. 实现 Retrieval Gate
3. 实现 Memory Consolidation
4. 集成测试

#### Phase 2: 技能系统升级 (Week 3-4)

1. 实现 9 维评估器
2. 实现棘轮机制
3. 实现 Human-in-the-Loop
4. 集成测试

#### Phase 3: Context Engineering (Week 5-6)

1. 实现 Checkpoint 管理器
2. 实现 Token Budget
3. 集成到 Agent 循环
4. 集成测试

#### Phase 4: 可观测与主动能力 (Week 7-8)

1. 实现 Durable Timeline
2. 实现 Proactivity 系统
3. 集成测试

---

## 五、测试策略

### 5.1 单元测试

- 每个新模块 100% 覆盖
- 边界条件测试
- 并发安全测试

### 5.2 集成测试

- 记忆系统闭环测试
- 技能进化闭环测试
- 飞轮闭环测试

### 5.3 性能测试

- Retrieval Gate 准确率 > 90%
- Checkpoint 恢复时间 < 1s
- Timeline 导出性能 > 1000 events/s

---

## 六、风险与缓解

| 风险 | 等级 | 缓解策略 |
|------|------|----------|
| Markdown 同步延迟 | 中 | 级联 Watcher + 增量同步 |
| 9 维评估成本高 | 中 | 异步执行 + 缓存结果 |
| Checkpoint 存储膨胀 | 低 | 定期压缩 + 过期清理 |
| Proactivity 打扰用户 | 高 | Nudge 策略 + 用户可配置 |

---

## 七、总结

本方案融合了 11 个顶级 Agent 项目的最佳实践：

1. **EverOS**: Markdown-first 记忆架构
2. **达尔文.skill**: 9 维评估 + 棘轮机制
3. **waku-agent**: Retrieval Gate + Consolidation
4. **DeerFlow**: Checkpoint + Context Engineering
5. **Raven**: Proactivity 系统
6. **amcp**: Durable Execution Timeline
7. **OpenPencil**: Concurrent Agent Teams

实施后，FnixAgent 将成为：
- **记忆更强**: Markdown 源真相 + 智能检索
- **技能更优**: 9 维评估 + 自动进化
- **上下文更精**: Checkpoint + Token Budget
- **执行更稳**: 可审计时间线 + 中断恢复
- **更主动**: Sentinel + Nudge

---

*文档版本: 2.0 | 生成日期: 2026-08-17*
