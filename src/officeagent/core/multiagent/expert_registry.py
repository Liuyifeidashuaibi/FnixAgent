"""专家注册表 —— P0-03。

借鉴 kaoyan-ai-platform 的专家注册机制:用配置化方式管理多个领域专家,
每个专家关联专属 system_prompt 和工具白名单。

设计要点:
  1. ExpertDefinition 用 @dataclass 声明专家元信息
  2. ExpertRegistry 单例管理全部已注册专家,线程安全(threading.Lock)
  3. 默认专家兜底:route 未命中时回到 default_expert
  4. 标准库 only(re, dataclasses, threading),无第三方依赖
  5. 模块级单例:get_registry() 双重检查锁

与 P0-03 ExpertRouter 的关系:
  - ExpertRouter 路由后返回 expert_key
  - ExpertRegistry 根据 expert_key 取出 ExpertDefinition
  - 上层用 ExpertDefinition.system_prompt / tools_whitelist 配置 Agent

用例:
    from officeagent.core.multiagent import get_registry, ExpertDefinition
    registry = get_registry()
    expert = registry.get("search")
    print(expert.display_name, expert.tools_whitelist)
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ExpertDefinition
# ---------------------------------------------------------------------------


@dataclass
class ExpertDefinition:
    """专家定义。

    Attributes:
        expert_key:      唯一标识(如 "search", "word", "pdf")
        display_name:    显示名称(如 "论文文献检索")
        system_prompt:   专属系统提示词(注入到 Agent 的 system message)
        tools_whitelist: 允许使用的工具名列表(白名单;空表示不限制)
        description:     专家描述(用于日志/调试/可视化)
    """

    expert_key: str
    display_name: str = ""
    system_prompt: str = ""
    tools_whitelist: list[str] = field(default_factory=list)
    description: str = ""


# ---------------------------------------------------------------------------
# ExpertRegistry
# ---------------------------------------------------------------------------


class ExpertRegistry:
    """专家注册表 —— 管理所有已注册专家。

    职责:
      - register(expert):         注册一个专家
      - get(expert_key):          按 key 取专家;未找到返回 None
      - get_default():            取默认兜底专家
      - set_default(expert_key):  设置默认兜底专家
      - list_experts():           列出全部 expert_key
      - __contains__(key):        支持 `in` 语法判断是否已注册

    并发安全:所有读写操作加 self._lock 保护(普通 Lock 即可,
    内部无嵌套调用)。

    用法:
        registry = get_registry()
        registry.register(ExpertDefinition(expert_key="custom", display_name="自定义"))
        if "custom" in registry:
            expert = registry.get("custom")
    """

    def __init__(self) -> None:
        self._experts: dict[str, ExpertDefinition] = {}
        self._default_key: Optional[str] = None
        # 普通锁足够:本类内部方法无嵌套调用(不调用其他持锁方法)
        self._lock = threading.Lock()

    # -- 注册 / 查询 ------------------------------------------------------

    def register(self, expert: ExpertDefinition) -> None:
        """注册一个专家。

        若 expert_key 已存在则覆盖。

        Args:
            expert: ExpertDefinition 实例

        Raises:
            ValueError: expert_key 为空
        """
        if not isinstance(expert, ExpertDefinition):
            raise ValueError("expert must be an ExpertDefinition instance")
        if not expert.expert_key or not expert.expert_key.strip():
            raise ValueError("expert_key must be a non-empty string")
        key = expert.expert_key
        with self._lock:
            self._experts[key] = expert
            # 首个注册的专家自动设为默认(若当前无默认)
            if self._default_key is None:
                self._default_key = key
        logger.debug("registered expert: %s (%s)", key, expert.display_name)

    def get(self, expert_key: str) -> Optional[ExpertDefinition]:
        """按 key 取专家;未找到返回 None。"""
        with self._lock:
            return self._experts.get(expert_key)

    def get_default(self) -> ExpertDefinition:
        """取默认兜底专家。

        若默认 key 未设置或已失效,自动取注册表中第一个专家;
        若注册表为空,返回一个内置的 generate 兜底专家
        (expert_key="generate",避免上层处理空值)。

        Returns:
            ExpertDefinition 实例(永远非空)
        """
        with self._lock:
            # 1. 默认 key 命中
            if self._default_key and self._default_key in self._experts:
                return self._experts[self._default_key]
            # 2. 取注册表中第一个专家
            if self._experts:
                first_key = next(iter(self._experts))
                self._default_key = first_key
                return self._experts[first_key]
        # 3. 注册表为空,返回内置兜底(不写入注册表,避免隐式状态变更)
        logger.warning(
            "expert registry is empty, returning built-in fallback 'generate'"
        )
        return _BUILTIN_FALLBACK

    def set_default(self, expert_key: str) -> None:
        """设置默认兜底专家。

        Args:
            expert_key: 已注册的 expert_key

        Raises:
            KeyError: expert_key 未注册
        """
        with self._lock:
            if expert_key not in self._experts:
                raise KeyError(
                    f"cannot set default: expert_key '{expert_key}' not registered"
                )
            self._default_key = expert_key
        logger.info("default expert set to: %s", expert_key)

    def list_experts(self) -> list[str]:
        """列出全部已注册的 expert_key。"""
        with self._lock:
            return list(self._experts.keys())

    def __contains__(self, key: str) -> bool:
        """支持 `key in registry` 语法。"""
        with self._lock:
            return key in self._experts

    def __len__(self) -> int:
        with self._lock:
            return len(self._experts)


# ---------------------------------------------------------------------------
# 内置兜底专家(注册表为空时使用,避免上层处理空值)
# ---------------------------------------------------------------------------

_BUILTIN_FALLBACK = ExpertDefinition(
    expert_key="generate",
    display_name="内容生成(兜底)",
    description="内置兜底专家,在注册表为空时返回",
)


# ---------------------------------------------------------------------------
# 默认专家预注册(OfficeAgent 内置 8 类专家)
# ---------------------------------------------------------------------------


def _build_default_experts() -> list[ExpertDefinition]:
    """构建 OfficeAgent 默认专家列表。

    Returns:
        8 个内置专家的 ExpertDefinition 列表
    """
    return [
        ExpertDefinition(
            expert_key="search",
            display_name="论文文献检索",
            tools_whitelist=["search_paper", "search_by_doi", "format_citation"],
            description="学术论文检索、DOI 查询、引用格式化",
            system_prompt=(
                "你是一名论文文献检索专家,擅长使用学术数据库(arxiv、知网等)"
                "检索论文,并通过 DOI 精确定位文献。"
            ),
        ),
        ExpertDefinition(
            expert_key="word",
            display_name="Word文档编辑",
            tools_whitelist=["create_docx", "edit_docx", "apply_style"],
            description="Word 文档创建、编辑、样式排版",
            system_prompt=(
                "你是一名 Word 文档编辑专家,擅长创建、编辑 docx 文档,"
                "并进行排版、页眉目录、批注修订等操作。"
            ),
        ),
        ExpertDefinition(
            expert_key="converter",
            display_name="格式转换",
            tools_whitelist=["convert_document"],
            description="文档格式转换(doc/md/pdf 互转)",
            system_prompt=(
                "你是一名文档格式转换专家,擅长在 doc/docx/md/pdf 等格式间转换。"
            ),
        ),
        ExpertDefinition(
            expert_key="chart",
            display_name="图表生成",
            tools_whitelist=["generate_chart", "plot_from_table"],
            description="数据可视化、图表生成(柱状图/折线图/饼图/散点图)",
            system_prompt=(
                "你是一名数据可视化专家,擅长根据数据或表格生成各类图表。"
            ),
        ),
        ExpertDefinition(
            expert_key="pdf",
            display_name="PDF生成",
            tools_whitelist=["generate_pdf_report"],
            description="PDF 报告/简历/海报生成",
            system_prompt=(
                "你是一名 PDF 生成专家,擅长生成报告、简历、海报等 PDF 文档。"
            ),
        ),
        ExpertDefinition(
            expert_key="parser",
            display_name="文档解析",
            tools_whitelist=["extract_tables", "ocr_image"],
            description="文档解析、表格提取、OCR 图片识别",
            system_prompt=(
                "你是一名文档解析专家,擅长从文档中提取表格、识别图片中的"
                "文字与公式(OCR)。"
            ),
        ),
        ExpertDefinition(
            expert_key="learning",
            display_name="学习辅助",
            tools_whitelist=["summarize", "qa_doc", "make_flashcards"],
            description="文档摘要、问答、笔记、抽认卡",
            system_prompt=(
                "你是一名学习辅助专家,擅长生成摘要、回答文档相关问题、"
                "制作笔记与抽认卡。"
            ),
        ),
        ExpertDefinition(
            expert_key="generate",
            display_name="内容生成(默认)",
            description="通用内容生成专家,作为默认兜底",
            system_prompt=(
                "你是一名通用内容生成专家,能够撰写论文、报告、方案等各类文本。"
            ),
        ),
    ]


def register_default_experts(registry: ExpertRegistry) -> None:
    """将 OfficeAgent 默认 8 类专家注册到 registry。

    若某 expert_key 已存在则覆盖。注册后将 "generate" 设为默认兜底专家。

    Args:
        registry: ExpertRegistry 实例
    """
    for expert in _build_default_experts():
        registry.register(expert)
    # 显式设置默认兜底专家为 generate
    registry.set_default("generate")
    logger.info(
        "registered %d default experts, default='%s'",
        len(registry), "generate",
    )


# ---------------------------------------------------------------------------
# 模块级单例(双重检查锁)
# ---------------------------------------------------------------------------

_registry_instance: Optional[ExpertRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> ExpertRegistry:
    """获取全局 ExpertRegistry 单例(双重检查锁)。

    首次调用时创建实例并预注册默认专家。

    Returns:
        ExpertRegistry 单例
    """
    global _registry_instance
    # 双重检查锁:第一次检查避免无竞争时加锁开销
    if _registry_instance is None:
        with _registry_lock:
            # 第二次检查:防止多线程同时通过第一次检查
            if _registry_instance is None:
                inst = ExpertRegistry()
                register_default_experts(inst)
                _registry_instance = inst
    return _registry_instance


def reset_registry() -> None:
    """重置全局单例(主要用于测试)。

    清空已注册专家,下次 get_registry() 时重新创建并预注册默认专家。
    """
    global _registry_instance
    with _registry_lock:
        _registry_instance = None


__all__ = [
    "ExpertDefinition",
    "ExpertRegistry",
    "register_default_experts",
    "get_registry",
    "reset_registry",
]
