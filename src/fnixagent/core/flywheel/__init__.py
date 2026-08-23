"""
四阶段进化飞轮 (MFP, Four-stage Evolution Flywheel) 模块。

MFP 是自进化 Agent 的核心驱动引擎,四个飞轮循环执行形成自驱动闭环:

    ① 感知-执行 (Perception-Execution)
       任务理解 → 概念路径检索 → 工具调用 → 结果收集 → 产出 TraceRecord

    ② 知识固化 (Knowledge Solidification)
       案例归并(相似度聚类) → 规则提取(LLM 抽取) → 写入 KTG(L3/L4 节点)

    ③ 元反思 (Meta-Reflection)
       评估策略效果 → 识别短板(低权重路径/高失败率技能) → 生成改进建议

    ④ 爬山进化 (Hill-Climbing Evolution)
       试探性变异(权重微调/技能增删) → 对比基线 → 保留改进/回滚回退

子模块(按 Day4-5 计划):
    - perception:        飞轮 ① 感知-执行(对接 LangGraph 编排)
    - solidification:    飞轮 ② 知识固化(对接 KTG 写入)
    - meta_reflection:   飞轮 ③ 元反思(对接 LLM 评估)
    - hill_climbing:     飞轮 ④ 爬山进化(对接快照/回滚)
    - snapshot:          进化快照管理(EvolutionSnapshot 持久化)

设计原则:
    - 每个飞轮独立可测,不依赖前一飞轮的运行时状态(仅消费其产出)
    - 飞轮 ④ 必须支持回滚,任何进化步骤失败不影响系统可用性
    - 进化是"试探性"的:小步快跑,每步可验证,失败即回滚
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.
