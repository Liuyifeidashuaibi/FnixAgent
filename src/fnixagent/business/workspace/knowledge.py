"""Knowledge Connector(P2-10)。

知识库能力:search/list_bases/get_doc/upload。
支持厂商:飞书知识库 / 语雀 / Notion / 企业微信知识库 / Confluence。
默认:StubProvider(本地开发占位)。

注:与 P2-5 Knowledge Pipeline 的区别:
  - P2-5 是 fnixagent 自有的知识抽取/向量化/检索管道(内部基础设施)
  - 此处 KnowledgeConnector 是对接外部知识库厂商的 API 抽象

性能与内存:
  - search 限制 top_k(默认 10,上限 100),避免一次性返回过多结果
  - list_bases / get_doc 异常捕获,统一转 ConnectorResult
  - 大文档 upload 由 Provider 内部流式上传(此处仅校验大小上限)

异常捕获:
  - Provider 调用包裹 try-except,捕获厂商 API(飞书/语雀/Notion/Confluence)异常
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass

from fnixagent.business.workspace.base import (
    BaseProvider,
    ConnectorResult,
    StubProvider,
    WorkspaceConnector,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 搜索结果 top_k 上限(避免一次性返回过多结果导致内存/响应体过大)
MAX_SEARCH_LIMIT = 100

# 上传文档内容大小上限(10 MB;超大文档应由 Provider 走流式/分片上传)
MAX_UPLOAD_CONTENT_BYTES = 10 * 1024 * 1024

# 支持的文档内容类型
_VALID_CONTENT_TYPES = {"markdown", "html", "wiki", "pdf"}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class KnowledgeBase:
    """知识库。"""

    base_id: str = ""
    name: str = ""
    description: str = ""
    owner: str = ""
    doc_count: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class KnowledgeDoc:
    """知识库文档。"""

    doc_id: str = ""
    base_id: str = ""
    title: str = ""
    content: str = ""
    content_type: str = "markdown"  # markdown / html / wiki / pdf
    author: str = ""
    tags: list[str] = None  # type: ignore
    created_at: str = ""
    updated_at: str = ""
    url: str = ""

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []


@dataclass
class SearchResult:
    """知识库搜索结果。"""

    doc: KnowledgeDoc
    score: float = 0.0
    snippet: str = ""
    matched_fields: list[str] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.matched_fields is None:
            self.matched_fields = []


# ---------------------------------------------------------------------------
# KnowledgeProvider 抽象
# ---------------------------------------------------------------------------


class KnowledgeProvider(BaseProvider):
    """知识库 Provider 抽象基类。

    具体实现(飞书/语雀/Notion/Confluence)应:
      - 持有 HTTP 客户端(支持 keep-alive 连接复用)
      - override close() 释放会话
      - 业务方法内部捕获厂商 API 异常,转为 ConnectorResult(success=False)
      - 大文档 upload 应走流式/分片上传,避免内存峰值
    """

    @abc.abstractmethod
    def search(
        self,
        query: str,
        base_ids: list[str] | None = None,
        limit: int = 10,
        filters: dict | None = None,
    ) -> ConnectorResult: ...

    @abc.abstractmethod
    def list_bases(self, owner: str | None = None) -> ConnectorResult: ...

    @abc.abstractmethod
    def get_doc(self, doc_id: str, base_id: str | None = None) -> ConnectorResult: ...

    @abc.abstractmethod
    def upload(
        self,
        base_id: str,
        title: str,
        content: str,
        content_type: str = "markdown",
        tags: list[str] | None = None,
        parent_doc_id: str | None = None,
    ) -> ConnectorResult: ...


# ---------------------------------------------------------------------------
# Stub 实现
# ---------------------------------------------------------------------------


class StubKnowledgeProvider(StubProvider, KnowledgeProvider):
    """知识库 stub 实现。

    返回值一致性:search/list_bases 空结果 data=[];upload 占位 ID 'stub-doc-<generated>'。
    """

    def search(
        self,
        query: str,
        base_ids: list[str] | None = None,
        limit: int = 10,
        filters: dict | None = None,
    ) -> ConnectorResult:
        # 空结果统一 data=[]
        return self._stub_result(
            data=[],
            query=query,
            base_ids=base_ids or [],
            limit=limit,
        )

    def list_bases(self, owner: str | None = None) -> ConnectorResult:
        # 空结果统一 data=[]
        return self._stub_result(data=[], owner=owner)

    def get_doc(self, doc_id: str, base_id: str | None = None) -> ConnectorResult:
        return self._stub_result(
            data=KnowledgeDoc(
                doc_id=doc_id,
                base_id=base_id or "",
                title="[stub] Sample knowledge doc",
                content="# Stub Document\n\nThis is a placeholder knowledge doc.",
                author="stub-author",
            ).__dict__,
        )

    def upload(
        self,
        base_id: str,
        title: str,
        content: str,
        content_type: str = "markdown",
        tags: list[str] | None = None,
        parent_doc_id: str | None = None,
    ) -> ConnectorResult:
        return self._stub_result(
            data=KnowledgeDoc(
                doc_id="stub-doc-<generated>",
                base_id=base_id,
                title=title,
                content=content,
                content_type=content_type,
                tags=tags or [],
            ).__dict__,
            action="upload",
        )


# ---------------------------------------------------------------------------
# KnowledgeConnector
# ---------------------------------------------------------------------------


class KnowledgeConnector(WorkspaceConnector):
    """外部知识库连接器(飞书知识库/语雀/Notion 等)。

    在委托 Provider 前校验参数(query/base_id/doc_id/title 非空、limit clamp、
    content_type 枚举、content 大小上限),并对厂商 API 调用统一捕获异常。
    """

    @property
    def name(self) -> str:
        return "knowledge"

    def _register_default_stub(self) -> None:
        self._providers["stub"] = StubKnowledgeProvider()

    # -- 业务方法 ------------------------------------------------------

    def search(
        self,
        query: str,
        base_ids: list[str] | None = None,
        limit: int = 10,
        filters: dict | None = None,
    ) -> ConnectorResult:
        """搜索知识库。

        Args:
            query: 搜索关键词(非空)
            base_ids: 限定知识库 ID 列表;None 搜索全部可访问的
            limit: 最多返回条数(top_k,自动 clamp 到 [1, 100])
            filters: 过滤条件 {tags: [...], author: ..., date_from: ..., date_to: ...}

        Returns:
            ConnectorResult(data=[SearchResult, ...]);空结果 data=[]
        """
        # 参数非空校验
        if not query or not query.strip():
            # 空查询直接返回空结果(BUG 修复:避免下游 NoneType 迭代)
            return ConnectorResult(
                success=True,
                data=[],
                metadata={"empty_query": True},
            )
        # top_k 限制
        safe_limit = max(1, min(limit, MAX_SEARCH_LIMIT))

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.search(
                query=query,
                base_ids=base_ids,
                limit=safe_limit,
                filters=filters,
            )
        except Exception as e:
            _logger.exception("knowledge.search failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"knowledge search failed: {type(e).__name__}: {e}",
            )

    def list_bases(self, owner: str | None = None) -> ConnectorResult:
        """列出知识库。

        Args:
            owner: 指定所有者;None 列出当前用户可访问的全部

        Returns:
            ConnectorResult(data=[KnowledgeBase, ...]);空结果 data=[]
        """
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.list_bases(owner=owner)
        except Exception as e:
            _logger.exception("knowledge.list_bases failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"knowledge list_bases failed: {type(e).__name__}: {e}",
            )

    def get_doc(
        self,
        doc_id: str,
        base_id: str | None = None,
    ) -> ConnectorResult:
        """获取知识库文档详情。

        Args:
            doc_id: 文档 ID(非空)
            base_id: 知识库 ID(部分厂商需要)

        Returns:
            ConnectorResult(data=KnowledgeDoc)
        """
        if not doc_id:
            return ConnectorResult(success=False, error="doc_id must not be empty")
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.get_doc(doc_id=doc_id, base_id=base_id)
        except Exception as e:
            _logger.exception("knowledge.get_doc failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"knowledge get_doc failed: {type(e).__name__}: {e}",
            )

    def upload(
        self,
        base_id: str,
        title: str,
        content: str,
        content_type: str = "markdown",
        tags: list[str] | None = None,
        parent_doc_id: str | None = None,
    ) -> ConnectorResult:
        """上传文档到知识库。

        Args:
            base_id: 目标知识库 ID(非空)
            title: 文档标题(非空)
            content: 文档内容(大小 ≤ 10MB;更大文档应由 Provider 流式上传)
            content_type: markdown / html / wiki / pdf
            tags: 标签列表
            parent_doc_id: 父文档 ID(知识树结构)

        Returns:
            ConnectorResult(data=KnowledgeDoc)
        """
        # 参数非空校验
        if not base_id:
            return ConnectorResult(success=False, error="base_id must not be empty")
        if not title or not title.strip():
            return ConnectorResult(success=False, error="title must not be empty")
        if not content:
            return ConnectorResult(success=False, error="content must not be empty")
        if content_type not in _VALID_CONTENT_TYPES:
            return ConnectorResult(
                success=False,
                error=f"unsupported content_type {content_type!r}, "
                f"must be one of {sorted(_VALID_CONTENT_TYPES)}",
            )
        # 内容大小校验
        content_size = len(content.encode("utf-8")) if isinstance(content, str) else len(content)
        if content_size > MAX_UPLOAD_CONTENT_BYTES:
            return ConnectorResult(
                success=False,
                error=f"content size ({content_size} bytes) exceeds limit "
                f"({MAX_UPLOAD_CONTENT_BYTES // 1024 // 1024}MB)",
            )

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.upload(
                base_id=base_id,
                title=title,
                content=content,
                content_type=content_type,
                tags=tags,
                parent_doc_id=parent_doc_id,
            )
        except Exception as e:
            _logger.exception("knowledge.upload failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"knowledge upload failed: {type(e).__name__}: {e}",
            )
