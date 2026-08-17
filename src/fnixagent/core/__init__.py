"""
fnixagent Core Engine
=======================
领域无关的 Agent 内核引擎层。

本包不依赖任何业务模块,提供完整的:
- LLM 基础服务 (多模型路由 / 限流 / 熔断 / 计费 / 缓存)
- 三层记忆系统 (短期 / 长期向量 / 实体)
- 工具执行平台 (元数据 / DAG 编排 / 安全沙箱)
- 合规与安全 (敏感词 / 注入防护 / 审核 / 脱敏)
- 规划与推理 (ReAct / Plan&Execute / Self-Reflection)
- 反思纠错
- Prompt 管理
- 向量检索 (Embedding / 混合检索)
- 调度中枢 (生命周期编排)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

__version__ = "1.0.0"
