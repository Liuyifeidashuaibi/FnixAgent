"""
LangGraph 编排层 (State Orchestration) 模块。

基于 LangGraph 的 StateGraph 实现有状态循环图编排,
替代原有 orchestrator/scheduler 的命令式调度,提供:
    - 声明式节点定义(每个节点是纯函数: State → State)
    - 条件边(基于 State 字段动态决定下一节点)
    - 循环支持(ReAct/Plan&Execute 的迭代循环天然适配)
    - 检查点(checkpointing,支持中断恢复)

核心 State 定义(MFP ① 阶段产出):
    - messages:           对话历史(ShortTermMemory 同步)
    - current_goal:       当前任务目标(L1 节点)
    - concept_path:       命中的 L2 概念序列
    - tool_calls:         待执行/已执行的工具调用
    - tool_results:       工具返回结果
    - trace:              执行轨迹(累积 ThoughtStep)
    - iteration:          当前迭代轮次
    - should_continue:    是否继续循环(条件边判断)

节点函数(按 Day4 计划):
    - perceive_node:      感知节点,理解用户意图 → 写入 current_goal
    - search_node:        检索节点,KTG 路径搜索 → 写入 concept_path
    - skill_select_node:  技能选择节点,STP 调度 → 写入 tool_calls
    - execute_node:       执行节点,调用 ToolExecutor → 写入 tool_results
    - reflect_node:       反思节点,评估结果 → 决定 should_continue

条件边:
    - should_continue == True  → 回到 perceive_node(下一轮迭代)
    - should_continue == False → 结束(产出 TraceRecord 给飞轮 ②)

与 core/orchestrator 的关系:
    本模块是新架构的状态编排层,逐步替代 orchestrator/scheduler。
    过渡期内两者并存,通过 services/service.py 工厂选择。
"""
