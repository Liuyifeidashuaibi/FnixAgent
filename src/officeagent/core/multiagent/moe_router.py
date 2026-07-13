"""MoE 专家路由器 —— P0-03。

借鉴 kaoyan-ai-platform 的 router.py:用纯关键词匹配(零 LLM 调用)
将用户意图快速路由到对应专家。

设计要点:
  1. 零 LLM 调用:纯关键词 + 正则子串匹配,O(n) 复杂度
  2. 优先级有序匹配:按 _ROUTING_KEYWORDS 顺序,首次命中即返回
  3. "任务类型：xxx" 行精确映射优先于关键词匹配
  4. 默认兜底专家:全部未命中时回到 registry.get_default()
  5. 标准库 only(re, threading),无第三方依赖
  6. 模块级单例:get_router() 双重检查锁
  7. 与 ExpertRegistry 解耦:route 仅返回 expert_key 字符串

匹配策略(route 方法,按优先级):
  1. 提取"任务类型：xxx"行,精确映射(_TASK_TYPE_MAP)
  2. 任务类型行关键词子串匹配(_ROUTING_KEYWORDS)
  3. 全文关键词子串匹配(_ROUTING_KEYWORDS)
  4. 默认兜底专家

用例:
    from officeagent.core.multiagent import get_router
    router = get_router()
    expert_key = router.route("任务类型：论文检索\\n帮我找 arxiv 上的 LLM 综述")
    # expert_key == "search"

    expert_key = router.route_by_user_input("帮我把这份 docx 转成 pdf")
    # expert_key == "converter"
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Optional

from officeagent.core.multiagent.expert_registry import (
    ExpertRegistry,
    get_registry,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 任务类型 → 专家 key 精确映射
# ---------------------------------------------------------------------------

# "任务类型：xxx" 行的 xxx 部分精确匹配到 expert_key
# 注:精确匹配时对 key 做去空白与大小写归一化(英文小写)
_TASK_TYPE_MAP: dict[str, str] = {
    # search - 论文文献检索
    "论文": "search",
    "paper": "search",
    "文献": "search",
    "检索": "search",
    "搜索": "search",
    # word - Word 文档编辑
    "word": "word",
    "文档编辑": "word",
    "docx": "word",
    # converter - 格式转换
    "格式转换": "converter",
    "转换": "converter",
    "convert": "converter",
    # chart - 图表生成
    "图表": "chart",
    "chart": "chart",
    "可视化": "chart",
    # pdf - PDF 生成
    "pdf": "pdf",
    "PDF生成": "pdf",
    # parser - 文档解析
    "解析": "parser",
    "提取": "parser",
    "OCR": "parser",
    # learning - 学习辅助
    "摘要": "learning",
    "问答": "learning",
    "笔记": "learning",
    # generate - 内容生成(兜底)
    "生成": "generate",
    "撰写": "generate",
    "写": "generate",
}


# ---------------------------------------------------------------------------
# 路由关键词(按优先级排序,首次命中即返回)
# ---------------------------------------------------------------------------

# 每个 tuple: (expert_key, [关键词列表])
# 关键词按子串匹配(中文子串 / 英文小写子串)
_ROUTING_KEYWORDS: list[tuple[str, list[str]]] = [
    ("search", ["论文", "文献", "检索", "搜索", "arxiv", "知网", "search", "doi", "引用格式"]),
    ("word", ["word", "docx", "文档编辑", "排版", "页眉", "目录", "批注", "修订"]),
    ("converter", ["格式转换", "转换格式", "doc转", "转pdf", "转md", "convert"]),
    ("chart", ["图表", "柱状图", "折线图", "饼图", "散点图", "可视化", "chart", "plot"]),
    ("pdf", ["pdf生成", "生成pdf", "报告pdf", "简历pdf", "海报"]),
    ("parser", ["解析", "提取表格", "OCR", "图片识别", "公式识别", "extract"]),
    ("learning", ["摘要", "总结", "问答", "笔记", "抽认卡", "概念图", "flashcard"]),
    ("generate", ["生成", "撰写", "写论文", "写报告", "总结", "方案", "generate"]),
]


# ---------------------------------------------------------------------------
# 预编译正则:匹配"任务类型：xxx"行
# ---------------------------------------------------------------------------

# 匹配 "任务类型：xxx" 或 "任务类型:xxx",捕获冒号后到行尾的内容
# 注:支持中英文冒号,允许冒号后有空白
_TASK_TYPE_PATTERN = re.compile(r"任务类型[：:]\s*([^\n\r]+)")


# ---------------------------------------------------------------------------
# ExpertRouter
# ---------------------------------------------------------------------------


class ExpertRouter:
    """专家路由器 —— 根据 analyze 输出文本或用户输入激活专家。

    零 LLM 调用,纯关键词 + 正则匹配。

    匹配策略(route 方法,按优先级,命中即返回):
      1. 提取"任务类型：xxx"行,精确映射(_TASK_TYPE_MAP)
      2. 任务类型行关键词子串匹配(_ROUTING_KEYWORDS)
      3. 全文关键词子串匹配(_ROUTING_KEYWORDS)
      4. 默认兜底专家(registry.get_default())

    线程安全:本类核心路由方法无可变状态(仅持有不可变映射 + registry 引用),
    多线程并发调用 route 安全。registry 自身线程安全。
    运行时关键词扩展(add_keyword)通过 threading.Lock 保护 _extra_keywords。
    """

    def __init__(self, registry: Optional[ExpertRegistry] = None) -> None:
        """初始化路由器。

        Args:
            registry: ExpertRegistry 实例;None 表示使用全局单例 get_registry()
        """
        self._registry = registry if registry is not None else get_registry()
        # P2-03 热更新:运行时追加的关键词(expert_key -> [keywords])
        # 命中判断时与模块级 _ROUTING_KEYWORDS 合并查询
        self._extra_keywords: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    # -- 属性 --------------------------------------------------------------

    @property
    def registry(self) -> ExpertRegistry:
        """关联的 ExpertRegistry。"""
        return self._registry

    # -- P2-03 热更新:运行时关键词扩展 -----------------------------------

    def add_keyword(self, expert_key: str, keywords: list[str]) -> None:
        """运行时为指定专家追加路由关键词(线程安全,P2-03 热更新)。

        关键词追加到实例级 _extra_keywords,与模块级 _ROUTING_KEYWORDS 合并查询。
        重复关键词会被忽略(去重保序)。

        Args:
            expert_key: 专家 key(如 "search")
            keywords: 要追加的关键词列表
        """
        if not expert_key or not keywords:
            return
        with self._lock:
            existing = self._extra_keywords.get(expert_key, [])
            for kw in keywords:
                kw = kw.strip()
                if kw and kw not in existing:
                    existing.append(kw)
            self._extra_keywords[expert_key] = existing
        logger.info(
            "追加专家路由关键词: expert=%s keywords=%s", expert_key, keywords
        )

    def remove_keyword(self, expert_key: str, keywords: list[str]) -> int:
        """移除运行时追加的关键词(线程安全,P2-03 热更新回滚支持)。

        仅移除实例级 _extra_keywords 中的关键词,不影响模块级默认关键词。

        Args:
            expert_key: 专家 key
            keywords: 要移除的关键词列表

        Returns:
            实际移除的关键词数量
        """
        if not expert_key or not keywords:
            return 0
        removed = 0
        with self._lock:
            existing = self._extra_keywords.get(expert_key)
            if not existing:
                return 0
            for kw in list(keywords):
                if kw in existing:
                    existing.remove(kw)
                    removed += 1
            if not existing:
                self._extra_keywords.pop(expert_key, None)
            else:
                self._extra_keywords[expert_key] = existing
        return removed

    def list_extra_keywords(self) -> dict[str, list[str]]:
        """返回运行时追加关键词的快照(线程安全)。"""
        with self._lock:
            return {k: list(v) for k, v in self._extra_keywords.items()}

    # -- 路由 --------------------------------------------------------------

    def route(self, analyze_text: str) -> str:
        """根据分析文本返回专家 expert_key。

        匹配策略(按优先级,命中即返回):
          1. 提取"任务类型：xxx"行,精确映射(_TASK_TYPE_MAP)
          2. 任务类型行关键词子串匹配(_ROUTING_KEYWORDS)
          3. 全文关键词子串匹配(_ROUTING_KEYWORDS)
          4. 默认兜底专家

        Args:
            analyze_text: analyze 阶段输出的文本
                          (含"任务类型：xxx"行 + 任务描述)

        Returns:
            专家 expert_key(如 "search", "word", "pdf", "generate" 等)
        """
        if not analyze_text or not analyze_text.strip():
            logger.debug("route: empty text, returning default expert")
            return self._default_key()

        # -- 步骤 1 & 2:提取任务类型行,精确映射 + 行内关键词匹配 ----------
        task_type_line = self._extract_task_type_line(analyze_text)
        if task_type_line:
            # 1. 精确映射(去空白、英文小写)
            exact_key = self._exact_match(task_type_line)
            if exact_key:
                logger.debug(
                    "route: task_type exact match '%s' -> '%s'",
                    task_type_line, exact_key,
                )
                return exact_key
            # 2. 任务类型行内关键词子串匹配
            kw_key = self._keyword_match(task_type_line)
            if kw_key:
                logger.debug(
                    "route: task_type keyword match '%s' -> '%s'",
                    task_type_line, kw_key,
                )
                return kw_key

        # -- 步骤 3:全文关键词子串匹配 ------------------------------------
        kw_key = self._keyword_match(analyze_text)
        if kw_key:
            logger.debug("route: full-text keyword match -> '%s'", kw_key)
            return kw_key

        # -- 步骤 4:默认兜底 ----------------------------------------------
        default_key = self._default_key()
        logger.debug("route: no match, returning default '%s'", default_key)
        return default_key

    def route_by_user_input(self, user_input: str) -> str:
        """直接根据用户原始输入路由(无需 analyze 阶段)。

        与 route() 的区别:
          - route() 期望 analyze 阶段输出(含"任务类型：xxx"行)
          - route_by_user_input() 直接处理用户原始输入
            (一般无"任务类型"行,主要走全文关键词匹配)

        实现上直接复用 route() 的全文匹配逻辑:
          1. 若用户输入恰好含"任务类型：xxx"行(罕见),按 route 处理
          2. 否则走全文关键词子串匹配
          3. 全部未命中 → 默认兜底专家

        Args:
            user_input: 用户原始输入文本

        Returns:
            专家 expert_key
        """
        # route() 已覆盖"任务类型行 + 全文关键词 + 默认兜底"全部策略,
        # 此处直接复用,保持匹配逻辑一致,避免维护两套规则。
        return self.route(user_input)

    # -- 内部方法 ----------------------------------------------------------

    @staticmethod
    def _extract_task_type_line(text: str) -> Optional[str]:
        """从文本中提取"任务类型：xxx"行的 xxx 部分。

        Args:
            text: 待提取的文本

        Returns:
            任务类型字符串(去首尾空白);未匹配返回 None
        """
        match = _TASK_TYPE_PATTERN.search(text)
        if not match:
            return None
        # group(1) 是冒号后到行尾的内容,去首尾空白
        return match.group(1).strip()

    @staticmethod
    def _exact_match(task_type: str) -> Optional[str]:
        """任务类型行精确映射。

        归一化策略:
          - 去首尾空白
          - 英文小写
          - 多个候选用 / 或 , 分隔时,逐个尝试

        Args:
            task_type: 任务类型行内容(如 "论文检索" 或 "search/retrieval")

        Returns:
            命中的 expert_key;未命中返回 None
        """
        # 用 / , 、 | 等常见分隔符拆分,逐个尝试精确匹配
        # 例:"论文/search" → ["论文", "search"]
        parts = re.split(r"[/,.、|，]+", task_type)
        for part in parts:
            key = part.strip().lower()
            if key and key in _TASK_TYPE_MAP:
                return _TASK_TYPE_MAP[key]
        return None

    def _keyword_match(self, text: str) -> Optional[str]:
        """全文/行内关键词子串匹配(含运行时追加关键词,P2-03)。

        按 _ROUTING_KEYWORDS 顺序遍历,首次命中即返回;未命中再遍历
        实例级 _extra_keywords(运行时热更新追加)。
        匹配时英文统一转小写后做子串匹配(避免大小写差异漏匹配)。

        Args:
            text: 待匹配的文本

        Returns:
            命中的 expert_key;未命中返回 None
        """
        # 文本统一转小写(英文部分),中文不受影响
        text_lower = text.lower()
        # 1. 模块级默认关键词(保持原优先级)
        for expert_key, keywords in _ROUTING_KEYWORDS:
            for kw in keywords:
                # 关键词也转小写(英文),保持大小写归一化
                if kw.lower() in text_lower:
                    return expert_key
        # 2. 运行时追加关键词(P2-03 热更新)
        with self._lock:
            extra_snapshot = list(self._extra_keywords.items())
        for expert_key, keywords in extra_snapshot:
            for kw in keywords:
                if kw.lower() in text_lower:
                    return expert_key
        return None

    def _default_key(self) -> str:
        """取默认兜底专家的 expert_key。

        从 registry.get_default() 取,保证与注册表一致。
        """
        return self._registry.get_default().expert_key


# ---------------------------------------------------------------------------
# 模块级单例(双重检查锁)
# ---------------------------------------------------------------------------

_router_instance: Optional[ExpertRouter] = None
_router_lock = threading.Lock()


def get_router() -> ExpertRouter:
    """获取全局 ExpertRouter 单例(双重检查锁)。

    首次调用时创建实例,关联全局 ExpertRegistry 单例。

    Returns:
        ExpertRouter 单例
    """
    global _router_instance
    if _router_instance is None:
        with _router_lock:
            if _router_instance is None:
                _router_instance = ExpertRouter(registry=get_registry())
    return _router_instance


def reset_router() -> None:
    """重置全局单例(主要用于测试)。

    下次 get_router() 时重新创建(关联当前 registry 单例)。
    """
    global _router_instance
    with _router_lock:
        _router_instance = None


__all__ = [
    "ExpertRouter",
    "get_router",
    "reset_router",
]
