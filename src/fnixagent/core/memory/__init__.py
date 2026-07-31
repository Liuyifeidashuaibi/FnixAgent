"""
三层记忆引擎 (Memory Engine)。

记忆分工:
  1. ShortTermMemory  — 短期会话记忆(滑动窗口裁剪,控制 token 上限)
  2. LongTermMemory   — 长期向量记忆(文档分块→向量化→检索→过期清理)
  3. EntityMemory     — 实体记忆(结构化业务数据:用户画像/论文/项目)
  4. MemoryManager    — 统一管理器(组合三层,统一注入 Prompt)

安全防护(参考 OWASP ASI06 记忆投毒):
  - 长期记忆写入时做内容校验(防投毒)
  - 实体记忆更新时做权限检查
  - 记忆检索结果做来源标记
"""

from fnixagent.core.memory.entity import EntityMemory
from fnixagent.core.memory.long_term import LongTermMemory
from fnixagent.core.memory.manager import MemoryManager
from fnixagent.core.memory.short_term import ShortTermMemory

__all__ = [
    "EntityMemory",
    "LongTermMemory",
    "MemoryManager",
    "ShortTermMemory",
]
