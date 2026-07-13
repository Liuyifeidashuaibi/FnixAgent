"""L3 任务场景:垂直落地方案(Phase 7)。

每个场景集成任务引擎各模块,提供端到端处理能力。

模块:
  Phase 7.1 题库处理:
    - question_bank.QuestionBankScenario: 题库/试卷处理场景
      (解析题目 → 检测乱码 → 恢复答案 → 填入括号 → 删题号/答案行
       → 统一格式 → 验证 → 导出pending清单)
"""
from officeagent.tasks.scenarios.question_bank import (
    ProcessOptions,
    QuestionBankScenario,
    QuestionInfo,
)

__all__ = [
    "QuestionBankScenario",
    "QuestionInfo",
    "ProcessOptions",
]
