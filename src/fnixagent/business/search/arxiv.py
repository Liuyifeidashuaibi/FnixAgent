"""
业务能力层 - 论文文献检索。

实现 arXiv / Semantic Scholar 等学术文献检索工具。

安全防护:
  - max_results 限制 top_k(上限 100,避免响应过大/被限流)
  - 使用 HTTPS(arxiv 改为 https,避免明文传输被中间人篡改)

异常捕获:
  - requests 网络异常(RequestException/Timeout/ConnectionError)统一捕获
  - XML 解析异常(ET.ParseError)单独捕获,返回空列表而非崩溃
  - JSON 解析异常(ValueError)单独捕获

性能优化:
  - 搜索结果限制 top_k,避免一次性返回过多
  - 跨源去重使用 dict O(1) 查找
"""

import logging
import re
import xml.etree.ElementTree as ET

from fnixagent.core.tools.protocol import ToolMetadata

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 单次搜索结果上限(避免响应过大/被限流)
MAX_RESULTS_LIMIT = 100

# arXiv Atom XML 命名空间
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


# ---------------------------------------------------------------------------
# arXiv 检索工具
# ---------------------------------------------------------------------------


def search_arxiv(
    query: str,
    max_results: int = 10,
    category: str | None = None,
) -> dict:
    """
    搜索 arXiv 论文。

    Args:
        query: 搜索关键词(非空)
        max_results: 最大返回数量(自动 clamp 到 [1, 100])
        category: arXiv 分类(如 cs.AI, cs.LG)

    Returns:
        论文列表: {success, source, query, count, results}
        空结果时 results=[](非 None)
    """
    # 参数非空校验
    if not query or not query.strip():
        return {
            "success": False,
            "error": "query must not be empty",
            "source": "arxiv",
            "query": query,
            "count": 0,
            "results": [],
        }
    # top_k 限制
    safe_max = max(1, min(max_results, MAX_RESULTS_LIMIT))

    import requests

    # 使用 HTTPS(原 http 明文传输存在安全风险)
    base_url = "https://export.arxiv.org/api/query"

    # 构建查询参数
    search_query = f"all:{query}"
    if category:
        search_query = f"cat:{category} AND {search_query}"

    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": safe_max,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        papers = parse_arxiv_response(response.text)

        return {
            "success": True,
            "source": "arxiv",
            "query": query,
            "count": len(papers),
            "results": papers,
        }

    except requests.Timeout:
        _logger.warning("arxiv search timeout: query=%r", query)
        return {
            "success": False,
            "error": "request timeout (15s)",
            "source": "arxiv",
            "query": query,
            "count": 0,
            "results": [],
        }
    except requests.RequestException as e:
        _logger.exception("arxiv search network error: %s: %s", type(e).__name__, e)
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "source": "arxiv",
            "query": query,
            "count": 0,
            "results": [],
        }
    except Exception as e:
        _logger.exception("arxiv search failed: %s: %s", type(e).__name__, e)
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "source": "arxiv",
            "query": query,
            "count": 0,
            "results": [],
        }


def parse_arxiv_response(xml_text: str) -> list[dict]:
    """
    解析 arXiv API 返回的 Atom XML。

    arXiv 使用 Atom 1.0 格式,每个 <entry> 是一篇论文。

    Args:
        xml_text: XML 文本

    Returns:
        论文列表,每篇包含: id, title, authors, abstract, pdf_url, published, category
        解析失败返回空列表(BUG 修复:不抛错给下游)
    """
    papers: list[dict] = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        # 用 logging 替代 print(避免污染 stdout)
        _logger.warning("arxiv XML parse failed: %s", e)
        return papers

    # 遍历所有 <entry> 元素
    for entry in root.findall("atom:entry", _ARXIV_NS):
        try:
            paper: dict = {}

            # arXiv ID (从 URL 提取: http://arxiv.org/abs/2301.00001v1)
            id_elem = entry.find("atom:id", _ARXIV_NS)
            if id_elem is not None and id_elem.text:
                raw_id = id_elem.text.strip()
                # 提取 arxiv ID (去掉版本号)
                paper["id"] = raw_id.split("/abs/")[-1].split("v")[0]
                paper["url"] = raw_id

            # 标题
            title_elem = entry.find("atom:title", _ARXIV_NS)
            if title_elem is not None and title_elem.text:
                # arXiv 标题常含多余空白,需清理
                paper["title"] = " ".join(title_elem.text.split())

            # 作者列表
            authors: list[str] = []
            for author in entry.findall("atom:author", _ARXIV_NS):
                name_elem = author.find("atom:name", _ARXIV_NS)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text.strip())
            paper["authors"] = authors

            # 摘要
            summary_elem = entry.find("atom:summary", _ARXIV_NS)
            if summary_elem is not None and summary_elem.text:
                paper["abstract"] = " ".join(summary_elem.text.split())

            # 发布日期
            published_elem = entry.find("atom:published", _ARXIV_NS)
            if published_elem is not None and published_elem.text:
                paper["published"] = published_elem.text.strip()[:10]  # YYYY-MM-DD

            # PDF 链接 (从 <link> 标签提取)
            pdf_url = ""
            for link in entry.findall("atom:link", _ARXIV_NS):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href", "")
                    break
            paper["pdf_url"] = pdf_url

            # 分类 (arXiv 分类标签)
            categories: list[str] = []
            for category_elem in entry.findall("{http://arxiv.org/schemas/atom}primary_category"):
                term = category_elem.get("term")
                if term:
                    categories.append(term)
            for category_elem in entry.findall("atom:category", _ARXIV_NS):
                term = category_elem.get("term")
                if term and term not in categories:
                    categories.append(term)
            paper["category"] = categories[0] if categories else ""
            paper["categories"] = categories

            papers.append(paper)

        except Exception as e:
            # 单篇解析失败不影响其他论文
            _logger.warning("arxiv parse single entry failed: %s: %s", type(e).__name__, e)
            continue

    return papers


# ---------------------------------------------------------------------------
# Semantic Scholar 检索工具
# ---------------------------------------------------------------------------


def search_semantic_scholar(
    query: str,
    max_results: int = 10,
    year_range: str | None = None,
) -> dict:
    """
    搜索 Semantic Scholar 论文。

    Args:
        query: 搜索关键词(非空)
        max_results: 最大返回数量(自动 clamp 到 [1, 100],API 上限 100)
        year_range: 年份范围(如 2020-2023)

    Returns:
        论文列表;空结果 results=[](非 None)
    """
    # 参数非空校验
    if not query or not query.strip():
        return {
            "success": False,
            "error": "query must not be empty",
            "source": "semantic_scholar",
            "query": query,
            "count": 0,
            "results": [],
        }
    safe_max = max(1, min(max_results, MAX_RESULTS_LIMIT))

    import requests

    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"

    params = {
        "query": query,
        "limit": min(safe_max, 100),  # API 上限 100
        "fields": "title,authors,abstract,year,url,venue,citationCount",
    }

    if year_range:
        params["year"] = year_range

    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        papers = data.get("data", [])

        # 标准化字段
        normalized = []
        for p in papers:
            normalized.append(
                {
                    "id": str(p.get("paperId", "")),
                    "title": p.get("title", ""),
                    "authors": [a.get("name", "") for a in p.get("authors", [])],
                    "abstract": p.get("abstract", ""),
                    "year": p.get("year"),
                    "url": p.get("url", ""),
                    "venue": p.get("venue", ""),
                    "citation_count": p.get("citationCount", 0),
                }
            )

        return {
            "success": True,
            "source": "semantic_scholar",
            "query": query,
            "count": len(normalized),
            "results": normalized,
        }

    except requests.Timeout:
        _logger.warning("semantic_scholar search timeout: query=%r", query)
        return {
            "success": False,
            "error": "request timeout (15s)",
            "source": "semantic_scholar",
            "query": query,
            "count": 0,
            "results": [],
        }
    except requests.RequestException as e:
        _logger.exception("semantic_scholar network error: %s: %s", type(e).__name__, e)
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "source": "semantic_scholar",
            "query": query,
            "count": 0,
            "results": [],
        }
    except ValueError as e:
        # JSON 解析失败
        _logger.exception("semantic_scholar JSON parse failed: %s: %s", type(e).__name__, e)
        return {
            "success": False,
            "error": f"JSON parse failed: {type(e).__name__}: {e}",
            "source": "semantic_scholar",
            "query": query,
            "count": 0,
            "results": [],
        }
    except Exception as e:
        _logger.exception("semantic_scholar search failed: %s: %s", type(e).__name__, e)
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "source": "semantic_scholar",
            "query": query,
            "count": 0,
            "results": [],
        }


# ---------------------------------------------------------------------------
# 论文去重与排序
# ---------------------------------------------------------------------------


def _normalize_title(title: str) -> str:
    """归一化标题(小写 + 去除标点和多余空格),用于去重比较。"""
    # 转小写
    t = title.lower()
    # 去除标点
    t = re.sub(r"[^\w\s]", "", t)
    # 压缩空白
    t = " ".join(t.split())
    return t


def deduplicate_papers(papers: list[dict]) -> list[dict]:
    """
    跨源论文去重。

    去重策略:
      1. 标题归一化后完全匹配 → 视为同一篇
      2. arXiv ID 匹配 → 视为同一篇
      3. 保留信息最完整的记录

    Args:
        papers: 多源聚合的论文列表

    Returns:
        去重后的论文列表
    """
    seen_titles: dict[str, int] = {}  # normalized_title -> index
    seen_ids: dict[str, int] = {}  # paper_id -> index
    result: list[dict] = []

    for paper in papers:
        title = paper.get("title", "")
        paper_id = paper.get("id", "")
        norm_title = _normalize_title(title)

        # 检查是否重复(dict O(1) 查找)
        dup_idx: int | None = None
        if norm_title and norm_title in seen_titles:
            dup_idx = seen_titles[norm_title]
        elif paper_id and paper_id in seen_ids:
            dup_idx = seen_ids[paper_id]

        if dup_idx is not None:
            # 重复: 合并信息(保留字段更多的)
            existing = result[dup_idx]
            for key, value in paper.items():
                if not existing.get(key) and value:
                    existing[key] = value
            # 合并来源
            sources = existing.get("sources", [existing.get("source", "")])
            if paper.get("source") and paper["source"] not in sources:
                sources.append(paper["source"])
            existing["sources"] = sources
        else:
            # 新论文
            if norm_title:
                seen_titles[norm_title] = len(result)
            if paper_id:
                seen_ids[paper_id] = len(result)
            paper["sources"] = [paper.get("source", "")]
            result.append(paper)

    return result


def sort_papers(papers: list[dict], by: str = "relevance") -> list[dict]:
    """
    论文排序。

    Args:
        papers: 论文列表
        by: 排序方式 (relevance/year/citations)

    Returns:
        排序后的论文列表
    """
    if by == "year":
        return sorted(papers, key=lambda p: p.get("year", 0) or 0, reverse=True)
    elif by == "citations":
        return sorted(papers, key=lambda p: p.get("citation_count", 0) or 0, reverse=True)
    else:  # relevance (保持原顺序)
        return papers


# ---------------------------------------------------------------------------
# 综合检索工具
# ---------------------------------------------------------------------------


def search_paper(
    query: str,
    sources: list[str] | None = None,
    max_results: int = 10,
) -> dict:
    """
    多源论文检索(聚合 arXiv / Semantic Scholar / 知网等)。

    自动去重 + 排序。

    Args:
        query: 搜索关键词(非空)
        sources: 数据源列表(默认 ["arxiv", "semantic_scholar"])
        max_results: 每个源最大返回数量(自动 clamp 到 [1, 100])

    Returns:
        聚合后的论文列表;空结果 results=[](非 None)
    """
    # 参数非空校验
    if not query or not query.strip():
        return {
            "success": False,
            "error": "query must not be empty",
            "query": query,
            "sources": sources or [],
            "source_status": [],
            "total_raw": 0,
            "total_deduplicated": 0,
            "count": 0,
            "results": [],
        }
    # BUG 修复:原 `sources: list = None` 默认值用 None 而非可变默认,
    # 此处显式判断 None → 默认列表(避免可变默认参数陷阱)
    if sources is None:
        sources = ["arxiv", "semantic_scholar"]
    safe_max = max(1, min(max_results, MAX_RESULTS_LIMIT))

    all_results: list[dict] = []
    source_status: list[dict] = []

    for source in sources:
        if source == "arxiv":
            res = search_arxiv(query, safe_max)
        elif source == "semantic_scholar":
            res = search_semantic_scholar(query, safe_max)
        else:
            source_status.append(
                {
                    "source": source,
                    "success": False,
                    "error": f"未知数据源: {source}",
                }
            )
            continue

        source_status.append(
            {
                "source": source,
                "success": res.get("success", False),
                "count": res.get("count", 0),
                "error": res.get("error", ""),
            }
        )

        if res.get("success"):
            all_results.extend(res.get("results", []))

    # 跨源去重
    deduplicated = deduplicate_papers(all_results)

    # 排序(默认按相关性)
    sorted_results = sort_papers(deduplicated, by="relevance")

    return {
        "success": True,
        "query": query,
        "sources": sources,
        "source_status": source_status,
        "total_raw": len(all_results),
        "total_deduplicated": len(sorted_results),
        "count": len(sorted_results),
        "results": sorted_results,
    }


# ---------------------------------------------------------------------------
# 工具元数据(注册到 ToolRegistry)
# ---------------------------------------------------------------------------


TOOL_METADATA = {
    "search_arxiv": ToolMetadata(
        name="search_arxiv",
        description="搜索 arXiv 学术论文库(物理/数学/计算机科学等)",
        category="search",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "max_results": {"type": "integer", "default": 10, "description": "最大返回数量"},
                "category": {"type": "string", "description": "arXiv分类(如 cs.AI, cs.LG)"},
            },
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "results": {"type": "array"},
            },
        },
    ),
    "search_semantic_scholar": ToolMetadata(
        name="search_semantic_scholar",
        description="搜索 Semantic Scholar 学术论文库(全学科覆盖)",
        category="search",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "max_results": {"type": "integer", "default": 10},
                "year_range": {"type": "string", "description": "年份范围(如 2020-2023)"},
            },
            "required": ["query"],
        },
    ),
    "search_paper": ToolMetadata(
        name="search_paper",
        description="多源论文检索(聚合 arXiv + Semantic Scholar,自动去重)",
        category="search",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "数据源列表",
                },
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    ),
}


def register_search_tools(registry) -> None:
    """注册论文检索工具到工具注册中心。"""
    registry.register(TOOL_METADATA["search_arxiv"], search_arxiv)
    registry.register(TOOL_METADATA["search_semantic_scholar"], search_semantic_scholar)
    registry.register(TOOL_METADATA["search_paper"], search_paper)
