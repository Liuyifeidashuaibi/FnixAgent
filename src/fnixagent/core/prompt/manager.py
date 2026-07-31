"""
Prompt 模板管理。

功能:
  - 模板注册/查询/激活/列表
  - 变量替换({{variable}} 占位符)
  - 版本管理(同名多版本,激活其中一个)
  - 内置默认模板(角色/ReAct/Plan/Reflection)

线程安全: threading.RLock。
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 模板数据结构
# ---------------------------------------------------------------------------


@dataclass
class PromptTemplate:
    """Prompt 模板。"""

    name: str
    version: str
    layer: str  # role/constraint/tools/memory/format/reflection
    content: str
    is_active: bool = False
    variables: list[str] = field(default_factory=list)

    def render(self, variables: dict[str, str]) -> str:
        """用变量字典替换 {{key}} 占位符。"""
        result = self.content
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result


# ---------------------------------------------------------------------------
# 内置默认模板
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_ROLE = """你是 fnixagent,一个专业的办公智能助手。
你的核心能力包括:论文文献检索、Word文档编辑、格式转换、图表生成、PDF生成、文档解析、学习辅助。

## 行为准则
1. 理解用户意图后,优先使用可用工具完成任务
2. 每次行动前说明你的思考过程
3. 工具调用失败时,分析原因并尝试替代方案
4. 涉及敏感操作(删除/覆盖文件)时,先征得用户确认
5. 输出结果时附带简要说明

## 当前上下文
- 用户: {{user_name}}
- 日期: {{date}}
"""

DEFAULT_REACT_TEMPLATE = """## 思考-行动-观察循环

请按以下格式回答:

Thought: 你对当前情况的思考和分析
Action: 你决定调用的工具名
Action Input: 工具的入参(JSON格式)

(等待工具返回后)

Observation: 工具返回的结果
Thought: (基于观察结果继续思考...)
... (重复直到得出最终答案)

Final Answer: 最终答案
"""

DEFAULT_PLAN_TEMPLATE = """## 任务计划

请将用户的高层目标拆解为可执行的子任务计划:

目标: {{goal}}

计划:
1. [步骤1描述] - 工具: (tool_name) - 依赖: (无/步骤号)
2. [步骤2描述] - 工具: (tool_name) - 依赖: (步骤号)
...

要求:
- 每个步骤应只调用一个工具
- 标注步骤间的依赖关系(可并行的步骤无依赖)
- 计划应覆盖从开始到完成的完整流程
"""

DEFAULT_REFLECTION_TEMPLATE = """## 结果校验

请检查上一步执行结果:

1. 完整性: 工具是否返回了预期的所有字段?
2. 正确性: 结果是否逻辑合理、数值正确?
3. 副作用: 是否产生了意外的文件修改或状态变更?

校验结果:
- 通过/不通过: (PASS/FAIL)
- 问题描述: (如有)
- 修复建议: (如不通过,建议如何修正)

如不通过,请重新规划并执行修复步骤。
"""


# ---------------------------------------------------------------------------
# 模板管理器
# ---------------------------------------------------------------------------


class PromptManager:
    """
    Prompt 模板管理器。

    用法:
        mgr = PromptManager()
        mgr.register(PromptTemplate(name="system_role", version="1.0", ...))
        text = mgr.render("system_role", {"user_name": "张三", "date": "2025-01-01"})
    """

    _VAR_RE = re.compile(r"\{\{(\w+)\}\}")

    def __init__(self):
        # (name, version) -> template
        self._templates: dict[tuple[str, str], PromptTemplate] = {}
        # name -> active version
        self._active: dict[str, str] = {}
        self._lock = threading.RLock()
        self._load_defaults()

    def _load_defaults(self) -> None:
        """加载内置默认模板。"""
        defaults = [
            PromptTemplate(
                name="system_role",
                version="1.0",
                layer="role",
                content=DEFAULT_SYSTEM_ROLE,
                is_active=True,
                variables=["user_name", "date"],
            ),
            PromptTemplate(
                name="react",
                version="1.0",
                layer="reflection",
                content=DEFAULT_REACT_TEMPLATE,
                is_active=True,
            ),
            PromptTemplate(
                name="plan_execute",
                version="1.0",
                layer="constraint",
                content=DEFAULT_PLAN_TEMPLATE,
                is_active=True,
                variables=["goal"],
            ),
            PromptTemplate(
                name="reflection",
                version="1.0",
                layer="reflection",
                content=DEFAULT_REFLECTION_TEMPLATE,
                is_active=True,
            ),
        ]
        for t in defaults:
            self._templates[(t.name, t.version)] = t
            self._active[t.name] = t.version

    # -- 注册 --------------------------------------------------------------

    def register(self, template: PromptTemplate) -> None:
        """注册模板。若同名同版本已存在则覆盖。"""
        with self._lock:
            key = (template.name, template.version)
            self._templates[key] = template
            if template.is_active:
                self._active[template.name] = template.version

    def activate(self, name: str, version: str) -> bool:
        """激活指定版本的模板。"""
        with self._lock:
            key = (name, version)
            if key not in self._templates:
                return False
            # 取消同名的其他版本激活
            for (n, v), t in self._templates.items():
                if n == name:
                    t.is_active = v == version
            self._active[name] = version
            return True

    # -- 查询 --------------------------------------------------------------

    def get(self, name: str, version: str | None = None) -> PromptTemplate | None:
        """获取模板。不指定版本则取激活版本。"""
        with self._lock:
            if version is None:
                version = self._active.get(name)
            if version is None:
                return None
            return self._templates.get((name, version))

    def list_templates(self, layer: str | None = None) -> list[PromptTemplate]:
        """列出所有模板(可按层过滤)。"""
        with self._lock:
            templates = list(self._templates.values())
            if layer:
                templates = [t for t in templates if t.layer == layer]
            return templates

    # -- 渲染 --------------------------------------------------------------

    def render(self, name: str, variables: dict[str, str] | None = None) -> str:
        """加载模板并替换变量。模板不存在则返回空串。"""
        template = self.get(name)
        if template is None:
            return ""
        return template.render(variables or {})

    def extract_variables(self, content: str) -> list[str]:
        """从模板内容中提取 {{variable}} 占位符列表。"""
        return [m.group(1) for m in self._VAR_RE.finditer(content)]
