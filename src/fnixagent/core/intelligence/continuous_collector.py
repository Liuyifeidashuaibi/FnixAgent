"""
∞ 无限信息采集引擎 — 语义级连续性情报收集

设计参考全球顶级项目:
  - GPT-Researcher (Columbia U, 28k stars): 多Agent协同, 分阶段研究, Tavily+LLM
  - AI-Researcher (HKU): 全自主科研, arXiv/IEEE/ACM/GitHub/HuggingFace多源
  - PaperOrchestra (Google): 多Agent论文写作, 专业分工
  - Semantic Scholar API: 语义级论文检索, 引用图谱, 推荐系统
  - Tavily Search API: 专为AI Agent优化的搜索, 实时 + 深度

架构:
  ┌─────────────────────────────────────────────────────┐
  │                 ∞ 采集引擎 (ContinuousCollector)    │
  ├─────────────────────────────────────────────────────┤
  │  GitHub API  │  arXiv API  │  Semantic Scholar      │
  │  Tavily API  │  RSS Feeds  │  HN/Reddit             │
  │  Tech Blogs  │  Newsletters│  Conference Papers     │
  ├─────────────────────────────────────────────────────┤
  │         LLM 提取 + 语义去重 + 相关性评分            │
  ├─────────────────────────────────────────────────────┤
  │         知识图谱增量更新 (KTG 拓扑注入)              │
  ├─────────────────────────────────────────────────────┤
  │         升级建议生成 → 飞轮闭环                      │
  └─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml

logger = logging.getLogger(__name__)


# ============================================================
# 信息源类型定义 (30+ 源)
# ============================================================

class SourceCategory(str, Enum):
    """信息源大类"""
    GITHUB = "github"              # GitHub 仓库 + Trending
    ARXIV = "arxiv"                # arXiv 预印本
    SEMANTIC_SCHOLAR = "semantic_scholar"  # Semantic Scholar 语义检索
    TAVILY = "tavily"              # Tavily AI 搜索
    TECH_BLOG = "tech_blog"        # 大厂技术博客
    RSS_FEED = "rss_feed"          # RSS 订阅源
    NEWSLETTER = "newsletter"      # AI 周刊/日报
    HACKER_NEWS = "hacker_news"    # Hacker News
    REDDIT = "reddit"              # Reddit 社区
    CONFERENCE = "conference"      # 学术会议
    PROTOCOL = "protocol"          # 协议标准
    HUGGINGFACE = "huggingface"    # Hugging Face 模型/数据集
    YOUTUBE = "youtube"            # 技术演讲/视频
    TWITTER = "twitter"            # 关键研究者动态


@dataclass
class SourceItem:
    """单条信息源原始数据"""
    source_id: str
    title: str
    url: str
    source_type: SourceCategory
    raw_text: str
    summary: str = ""
    authors: list[str] = field(default_factory=list)
    published_at: str = ""
    citation_count: int = 0
    star_count: int = 0
    relevance_score: float = 0.0
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================
# GitHub 深度采集器
# ============================================================

class GitHubDeepCollector:
    """GitHub 深度采集: API + Trending + Release Notes"""

    BASE_URL = "https://api.github.com"
    TRENDING_URL = "https://github.com/trending"

    def __init__(self, client: httpx.AsyncClient, token: str = ""):
        self.client = client
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}" if token else "",
            "User-Agent": "FnixAgent/1.0"
        }

    async def search_repos(self, query: str, per_page: int = 20) -> list[SourceItem]:
        """搜索 GitHub 仓库"""
        url = f"{self.BASE_URL}/search/repositories"
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": per_page
        }
        try:
            resp = await self.client.get(url, headers=self.headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            items = []
            for repo in data.get("items", []):
                items.append(SourceItem(
                    source_id=f"gh_{repo['id']}",
                    title=repo["full_name"],
                    url=repo["html_url"],
                    source_type=SourceCategory.GITHUB,
                    raw_text=repo.get("description", ""),
                    summary=repo.get("description", ""),
                    star_count=repo.get("stargazers_count", 0),
                    published_at=repo.get("updated_at", ""),
                    tags=repo.get("topics", []),
                    metadata={
                        "language": repo.get("language", ""),
                        "forks": repo.get("forks_count", 0),
                        "open_issues": repo.get("open_issues_count", 0),
                        "license": repo.get("license", {}).get("spdx_id", "") if repo.get("license") else ""
                    }
                ))
            return items
        except Exception as e:
            logger.warning(f"GitHub search failed: {e}")
            return []

    async def get_releases(self, owner: str, repo: str, count: int = 5) -> list[SourceItem]:
        """获取仓库最新 Release"""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/releases?per_page={count}"
        try:
            resp = await self.client.get(url, headers=self.headers, timeout=15)
            resp.raise_for_status()
            releases = resp.json()
            items = []
            for rel in releases:
                items.append(SourceItem(
                    source_id=f"gh_rel_{rel['id']}",
                    title=f"[{owner}/{repo}] {rel.get('name', rel['tag_name'])}",
                    url=rel.get("html_url", ""),
                    source_type=SourceCategory.GITHUB,
                    raw_text=rel.get("body", ""),
                    published_at=rel.get("published_at", ""),
                    tags=[owner, repo],
                    metadata={"tag": rel["tag_name"]}
                ))
            return items
        except Exception as e:
            logger.warning(f"GitHub releases {owner}/{repo} failed: {e}")
            return []

    async def get_trending(self, language: str = "python", since: str = "daily") -> list[SourceItem]:
        """获取 GitHub Trending"""
        url = f"{self.TRENDING_URL}/{language}?since={since}"
        try:
            resp = await self.client.get(url, timeout=15)
            html = resp.text
            items = []
            # 解析 Trending 页面
            repo_pattern = r'<h2[^>]*>\s*<a[^>]*href="(/[^"]+)"[^>]*>\s*<span[^>]*>([^<]+)</span>\s*/\s*<span[^>]*>([^<]+)</span>'
            matches = re.findall(repo_pattern, html)
            for owner_rel, owner_name, repo_name in matches:
                full_name = f"{owner_name.strip()}/{repo_name.strip()}"
                items.append(SourceItem(
                    source_id=f"gh_trend_{full_name.replace('/', '_')}",
                    title=full_name,
                    url=f"https://github.com/{full_name}",
                    source_type=SourceCategory.GITHUB,
                    raw_text="",
                    tags=["trending", since, language]
                ))
            return items
        except Exception as e:
            logger.warning(f"GitHub trending failed: {e}")
            return []


# ============================================================
# Semantic Scholar API 采集器
# ============================================================

class SemanticScholarCollector:
    """Semantic Scholar API: 语义级论文检索 + 引用图谱 + 推荐"""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    # AI Agent 领域核心检索词
    AI_AGENT_QUERIES = [
        "AI agent self-improving autonomous",
        "multi-agent LLM collaboration framework",
        "language model agent tool use reasoning",
        "self-evolving agent continual learning",
        "agent memory retrieval augmented generation",
        "reinforcement learning agent skill library",
        "agentic AI system architecture design",
        "LLM agent planning reflection execution",
    ]

    def __init__(self, client: httpx.AsyncClient, api_key: str = ""):
        self.client = client
        self.api_key = api_key

    async def search_papers(
        self, query: str, limit: int = 10, year: str = "2025-2026"
    ) -> list[SourceItem]:
        """语义搜索论文"""
        url = f"{self.BASE_URL}/paper/search"
        params = {
            "query": query,
            "limit": limit,
            "fields": "title,url,abstract,authors,year,citationCount,publicationTypes,externalIds,tldr",
            "year": year,
            "fieldsOfStudy": "Computer Science"
        }
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        try:
            resp = await self.client.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            items = []
            for paper in data.get("data", []):
                tldr = paper.get("tldr", {})
                items.append(SourceItem(
                    source_id=f"s2_{paper.get('paperId', '')}",
                    title=paper.get("title", ""),
                    url=paper.get("url", ""),
                    source_type=SourceCategory.SEMANTIC_SCHOLAR,
                    raw_text=paper.get("abstract", ""),
                    summary=tldr.get("text", paper.get("abstract", "")[:300]) if tldr else paper.get("abstract", "")[:300],
                    authors=[a.get("name", "") for a in paper.get("authors", [])],
                    published_at=str(paper.get("year", "")),
                    citation_count=paper.get("citationCount", 0),
                    metadata={
                        "paper_id": paper.get("paperId", ""),
                        "external_ids": paper.get("externalIds", {}),
                        "publication_types": paper.get("publicationTypes", []),
                    }
                ))
            return items
        except Exception as e:
            logger.warning(f"Semantic Scholar search failed: {e}")
            return []

    async def get_paper_recommendations(self, paper_id: str, limit: int = 5) -> list[SourceItem]:
        """基于论文获取推荐（引用 + 相似）"""
        url = f"{self.BASE_URL}/paper/{paper_id}/recommendations"
        params = {"limit": limit, "fields": "title,url,abstract,authors,year,citationCount"}
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        try:
            resp = await self.client.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            items = []
            for rec in data.get("recommendedPapers", []):
                items.append(SourceItem(
                    source_id=f"s2_rec_{rec.get('paperId', '')}",
                    title=rec.get("title", ""),
                    url=rec.get("url", ""),
                    source_type=SourceCategory.SEMANTIC_SCHOLAR,
                    raw_text=rec.get("abstract", ""),
                    authors=[a.get("name", "") for a in rec.get("authors", [])],
                    citation_count=rec.get("citationCount", 0),
                    metadata={"seed_paper": paper_id}
                ))
            return items
        except Exception as e:
            logger.warning(f"Recommendations failed: {e}")
            return []

    async def batch_search(self, queries: list[str] | None = None, limit: int = 10) -> list[SourceItem]:
        """批量搜索多个 AI Agent 相关查询"""
        queries = queries or self.AI_AGENT_QUERIES
        tasks = [self.search_papers(q, limit) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_items = []
        for r in results:
            if isinstance(r, list):
                all_items.extend(r)
        return self._deduplicate(all_items)

    def _deduplicate(self, items: list[SourceItem]) -> list[SourceItem]:
        seen = set()
        unique = []
        for item in items:
            if item.source_id not in seen:
                seen.add(item.source_id)
                unique.append(item)
        return unique


# ============================================================
# arXiv API 采集器 (增强版)
# ============================================================

class ArxivEnhancedCollector:
    """arXiv 增强采集: API + 语义扩展 + 自动分类"""

    ARXIV_API = "http://export.arxiv.org/api/query"

    CATEGORIES = [
        ("cs.AI", "Artificial Intelligence"),
        ("cs.CL", "Computation and Language"),
        ("cs.LG", "Machine Learning"),
        ("cs.MA", "Multiagent Systems"),
        ("cs.SE", "Software Engineering"),
    ]

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def search(self, query: str, max_results: int = 10) -> list[SourceItem]:
        """搜索 arXiv 论文"""
        url = f"{self.ARXIV_API}?search_query=all:{query}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
        try:
            resp = await self.client.get(url, timeout=15)
            resp.raise_for_status()
            return self._parse_xml(resp.text)
        except Exception as e:
            logger.warning(f"arXiv search failed: {e}")
            return []

    async def search_by_category(self, category: str, max_results: int = 10) -> list[SourceItem]:
        """按分类搜索最新论文"""
        url = f"{self.ARXIV_API}?search_query=cat:{category}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
        try:
            resp = await self.client.get(url, timeout=15)
            resp.raise_for_status()
            return self._parse_xml(resp.text)
        except Exception as e:
            logger.warning(f"arXiv category {category} failed: {e}")
            return []

    def _parse_xml(self, xml_text: str) -> list[SourceItem]:
        from xml.etree import ElementTree as ET
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        items = []
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            summary = entry.find("atom:summary", ns)
            link = entry.find("atom:id", ns)
            published = entry.find("atom:published", ns)
            authors = entry.findall("atom:author/atom:name", ns)
            cats = entry.findall("arxiv:primary_category", ns)

            title_text = title.text.strip() if title is not None and title.text else ""
            summary_text = summary.text.strip() if summary is not None and summary.text else ""
            link_text = link.text.strip() if link is not None and link.text else ""

            items.append(SourceItem(
                source_id=f"arxiv_{link_text.split('/')[-1]}",
                title=title_text,
                url=link_text,
                source_type=SourceCategory.ARXIV,
                raw_text=summary_text,
                summary=summary_text[:500],
                authors=[a.text.strip() for a in authors if a.text],
                published_at=published.text if published is not None else "",
                tags=[cat.get("term", "") for cat in cats],
                metadata={"categories": [cat.get("term", "") for cat in cats]}
            ))
        return items


# ============================================================
# RSS + 技术博客采集器
# ============================================================

class RSSFeedCollector:
    """RSS 订阅源采集 + 大厂技术博客"""

    AI_RSS_FEEDS = [
        # AI 研究直通车
        ("https://arxiv.org/rss/cs.AI", "arXiv cs.AI"),
        ("https://arxiv.org/rss/cs.CL", "arXiv cs.CL"),
        ("https://arxiv.org/rss/cs.LG", "arXiv cs.LG"),
        # 大厂技术博客
        ("https://openai.com/blog/rss.xml", "OpenAI Blog"),
        ("https://www.anthropic.com/research/feed", "Anthropic Research"),
        ("https://deepmind.google/discover/blog/feed/", "Google DeepMind"),
        ("https://ai.meta.com/blog/feed/", "Meta AI"),
        # 社区
        ("https://blog.langchain.dev/feed/", "LangChain Blog"),
        # 论文速递
        ("https://huggingface.co/blog/feed.xml", "Hugging Face Blog"),
    ]

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def fetch_feeds(self, feeds: list[tuple[str, str]] | None = None) -> list[SourceItem]:
        """批量拉取 RSS 订阅源"""
        feeds = feeds or self.AI_RSS_FEEDS
        tasks = [self._fetch_single(url, name) for url, name in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_items = []
        for r in results:
            if isinstance(r, list):
                all_items.extend(r)
        return all_items

    async def _fetch_single(self, url: str, source_name: str) -> list[SourceItem]:
        try:
            resp = await self.client.get(url, timeout=15)
            resp.raise_for_status()
            return self._parse_rss(resp.text, source_name)
        except Exception as e:
            logger.warning(f"RSS {source_name} failed: {e}")
            return []

    def _parse_rss(self, xml_text: str, source_name: str) -> list[SourceItem]:
        from xml.etree import ElementTree as ET
        # 尝试 RSS 2.0
        try:
            root = ET.fromstring(xml_text)
            items = []
            # RSS 2.0
            for item in root.iter("item"):
                title = item.find("title")
                link = item.find("link")
                desc = item.find("description")
                pub_date = item.find("pubDate")
                items.append(SourceItem(
                    source_id=f"rss_{hashlib.md5((link.text or '').encode()).hexdigest()[:12]}",
                    title=title.text if title is not None and title.text else "",
                    url=link.text if link is not None and link.text else "",
                    source_type=SourceCategory.RSS_FEED,
                    raw_text=desc.text if desc is not None and desc.text else "",
                    published_at=pub_date.text if pub_date is not None and pub_date.text else "",
                    tags=[source_name],
                    metadata={"source": source_name}
                ))
            return items
        except ET.ParseError:
            return []


# ============================================================
# ∞ 统一采集引擎
# ============================================================

class ContinuousCollector:
    """
    ∞ 无限采集引擎

    统一调度所有采集器, 按频率执行, 去重, 评分, 存储
    """

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or str(
            Path(__file__).parent.parent.parent.parent / "config" / "intelligence_sources.yaml"
        )
        self.config = self._load_config()
        self._client: Optional[httpx.AsyncClient] = None
        self.github_token = self.config.get("secrets", {}).get("github_token", "")
        self.s2_api_key = self.config.get("secrets", {}).get("semantic_scholar_api_key", "")

    def _load_config(self) -> dict:
        with open(self.config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": "FnixAgent-Intelligence/2.0"},
                timeout=30.0
            )
        return self._client

    async def collect_daily(self) -> list[SourceItem]:
        """每日采集: GitHub Trending + arXiv 最新 + RSS"""
        client = await self._get_client()
        all_items: list[SourceItem] = []

        # GitHub
        gh = GitHubDeepCollector(client, self.github_token)
        gh_items = await gh.get_trending("python", "daily")
        all_items.extend(gh_items)

        # arXiv 最新
        arxiv = ArxivEnhancedCollector(client)
        for cat, _ in ArxivEnhancedCollector.CATEGORIES[:3]:
            cat_items = await arxiv.search_by_category(cat, 5)
            all_items.extend(cat_items)

        # RSS
        rss = RSSFeedCollector(client)
        rss_items = await rss.fetch_feeds()
        all_items.extend(rss_items)

        return self._deduplicate(all_items)

    async def collect_weekly(self) -> list[SourceItem]:
        """每周采集: GitHub Release + Semantic Scholar + 仓库监控"""
        client = await self._get_client()
        all_items: list[SourceItem] = []

        # Semantic Scholar 深度搜索
        s2 = SemanticScholarCollector(client, self.s2_api_key)
        s2_items = await s2.batch_search(limit=10)
        all_items.extend(s2_items)

        # GitHub 仓库 Release
        gh = GitHubDeepCollector(client, self.github_token)
        repos = self.config.get("sources", {}).get("github_repos", [])
        for repo in repos[:8]:
            name = repo.get("url", "").replace("https://github.com/", "").strip("/")
            if "/" in name:
                owner, repo_name = name.split("/")
                releases = await gh.get_releases(owner, repo_name, 3)
                all_items.extend(releases)

        # GitHub 搜索最新 AI Agent 项目
        search_items = await gh.search_repos("AI agent autonomous self-improving", 10)
        all_items.extend(search_items)

        return self._deduplicate(all_items)

    async def collect_monthly(self) -> list[SourceItem]:
        """每月采集: 会议论文 + 领域全景分析"""
        client = await self._get_client()
        all_items: list[SourceItem] = []

        # Semantic Scholar 深度搜索 (全量)
        s2 = SemanticScholarCollector(client, self.s2_api_key)
        s2_items = await s2.batch_search(limit=20)
        all_items.extend(s2_items)

        # arXiv 全分类搜索
        arxiv = ArxivEnhancedCollector(client)
        for cat, _ in ArxivEnhancedCollector.CATEGORIES:
            cat_items = await arxiv.search_by_category(cat, 10)
            all_items.extend(cat_items)

        return self._deduplicate(all_items)

    async def collect_all(self, frequency: str = "daily") -> dict:
        """统一采集入口"""
        all_items: list[SourceItem] = []
        errors: list[str] = []

        try:
            if frequency == "daily":
                all_items = await self.collect_daily()
            elif frequency == "weekly":
                all_items = await self.collect_weekly()
            elif frequency == "monthly":
                all_items = await self.collect_monthly()
        except Exception as e:
            errors.append(str(e))

        return {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "frequency": frequency,
            "total_items": len(all_items),
            "errors": errors,
            "items": [
                {
                    "source_id": item.source_id,
                    "title": item.title,
                    "url": item.url,
                    "source_type": item.source_type.value,
                    "summary": item.summary,
                    "authors": item.authors,
                    "published_at": item.published_at,
                    "citation_count": item.citation_count,
                    "star_count": item.star_count,
                    "relevance_score": item.relevance_score,
                    "tags": item.tags,
                    "metadata": item.metadata
                }
                for item in all_items
            ]
        }

    def _deduplicate(self, items: list[SourceItem]) -> list[SourceItem]:
        seen = set()
        unique = []
        for item in items:
            if item.source_id not in seen:
                seen.add(item.source_id)
                unique.append(item)
        return unique

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()