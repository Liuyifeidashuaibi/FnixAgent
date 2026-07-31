"""
智能信息采集引擎 — 多源情报收集

设计参考:
  - Hermes Agent: 技能自动创建 + GEPA遗传优化
  - OpenClaw: Self-Improving Agent Skill + ClawHub技能市场
  - SAGE: RL-based skill library + 强化学习自进化
  - GEPA (ICLR 2026 Oral): 遗传帕累托Prompt进化, 比RL好6%, 数据量仅1/35

采集策略:
  - 高频 (每天): GitHub Trending, arXiv新论文, HN讨论
  - 中频 (每周): 仓库Release, 技术博客, Reddit
  - 低频 (每月): 会议论文, 协议更新, 领域全景分析
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

logger = logging.getLogger(__name__)


# ============================================================
# 数据模型
# ============================================================


class SourceType(str, Enum):
    """信息源类型"""

    GITHUB_REPO = "github_repo"
    GITHUB_TRENDING = "github_trending"
    ARXIV = "arxiv"
    TECH_BLOG = "tech_blog"
    HACKER_NEWS = "hacker_news"
    REDDIT = "reddit"
    PROTOCOL = "protocol"
    CONFERENCE = "conference"


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IntelligenceCategory(str, Enum):
    """情报分类"""

    SELF_EVOLVING_AGENT = "self_evolving_agent"
    AGENT_FRAMEWORK = "agent_framework"
    MULTI_AGENT = "multi_agent"
    FRONTIER_RESEARCH = "frontier_research"
    AGENT_ENGINEERING = "agent_engineering"
    REINFORCEMENT_LEARNING = "reinforcement_learning"
    AGENT_PROTOCOL = "agent_protocol"
    TOOL_USE = "tool_use"
    MEMORY_SYSTEM = "memory_system"
    REASONING = "reasoning"
    PROMPT_ENGINEERING = "prompt_engineering"
    CODE_GENERATION = "code_generation"
    EVALUATION = "evaluation"


@dataclass
class IntelligenceItem:
    """单条情报"""

    id: str
    title: str
    source_type: SourceType
    source_name: str
    url: str
    category: IntelligenceCategory
    priority: Priority
    summary: str = ""
    key_insights: list[str] = field(default_factory=list)
    actionable: bool = False
    upgrade_suggestion: str = ""
    tags: list[str] = field(default_factory=list)
    collected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    raw_content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def generate_id(title: str, url: str) -> str:
        return hashlib.sha256(f"{title}{url}".encode()).hexdigest()[:16]


@dataclass
class CollectionResult:
    """一次采集结果"""

    source_type: SourceType
    source_name: str
    items: list[IntelligenceItem]
    collected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


# ============================================================
# 采集器基类
# ============================================================


class BaseCollector:
    """采集器基类"""

    def __init__(self, http_client: httpx.AsyncClient, config: dict[str, Any]):
        self.client = http_client
        self.config = config

    async def collect(self) -> CollectionResult:
        raise NotImplementedError

    async def _fetch(self, url: str, **kwargs) -> str:
        """带重试的HTTP请求"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self.client.get(url, timeout=30.0, follow_redirects=True, **kwargs)
                response.raise_for_status()
                return response.text
            except Exception:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)
        return ""


# ============================================================
# GitHub 采集器
# ============================================================


class GitHubCollector(BaseCollector):
    """GitHub 仓库监控 + Trending 采集"""

    GITHUB_API = "https://api.github.com"
    TRENDING_URL = "https://github.com/trending/python?since=daily"

    async def collect(self) -> CollectionResult:
        items: list[IntelligenceItem] = []
        errors: list[str] = []
        start = time.monotonic()

        repos = self.config.get("github_repos", [])
        tasks = [self._collect_repo(repo) for repo in repos]
        tasks.append(self._collect_trending())

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
            elif isinstance(result, list):
                items.extend(result)

        return CollectionResult(
            source_type=SourceType.GITHUB_REPO,
            source_name="GitHub",
            items=items,
            errors=errors,
            duration_ms=(time.monotonic() - start) * 1000,
        )

    async def _collect_repo(self, repo: dict) -> list[IntelligenceItem]:
        """采集单个仓库最新动态"""
        items: list[IntelligenceItem] = []
        repo_name = urlparse(repo["url"]).path.strip("/")
        try:
            # 获取最新 Release
            releases_url = f"{self.GITHUB_API}/repos/{repo_name}/releases?per_page=3"
            releases_text = await self._fetch(
                releases_url, headers={"Accept": "application/vnd.github+json"}
            )
            releases = json.loads(releases_text)
            for rel in releases:
                items.append(
                    IntelligenceItem(
                        id=IntelligenceItem.generate_id(
                            f"{repo_name}-{rel['tag_name']}", rel.get("html_url", "")
                        ),
                        title=f"[{repo['name']}] {rel.get('name', rel['tag_name'])}",
                        source_type=SourceType.GITHUB_REPO,
                        source_name=repo["name"],
                        url=rel.get("html_url", ""),
                        category=IntelligenceCategory(repo.get("category", "agent_framework")),
                        priority=Priority(repo.get("priority", "medium")),
                        summary=rel.get("body", "")[:500] if rel.get("body") else "",
                        key_insights=self._extract_insights(rel.get("body", "")),
                        tags=repo.get("watch", []),
                        metadata={
                            "repo": repo_name,
                            "tag": rel["tag_name"],
                            "published_at": rel.get("published_at", ""),
                            "stars": repo.get("stars", 0),
                        },
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to collect {repo_name}: {e}")
        return items

    async def _collect_trending(self) -> list[IntelligenceItem]:
        """采集 GitHub Trending"""
        items: list[IntelligenceItem] = []
        ai_keywords = [
            "agent",
            "llm",
            "ai",
            "gpt",
            "claude",
            "langchain",
            "rag",
            "autonomous",
            "self-improving",
            "multi-agent",
            "mcp",
            "a2a",
        ]
        try:
            html = await self._fetch(self.TRENDING_URL)
            pattern = r'<h2[^>]*>\s*<a[^>]*href="(/[^"]+)"[^>]*>\s*<span[^>]*>([^<]+)</span>\s*/\s*<span[^>]*>([^<]+)</span>'
            matches = re.findall(pattern, html)
            for owner, repo_name in matches:
                full_name = f"{owner.strip('/')}/{repo_name}"
                desc_pattern = rf"<p[^>]*>\s*({full_name}[^<]*|[^<]*{full_name}[^<]*)</p>"
                desc_match = re.search(desc_pattern, html, re.IGNORECASE)
                description = desc_match.group(1).strip() if desc_match else ""
                if any(kw in full_name.lower() or kw in description.lower() for kw in ai_keywords):
                    items.append(
                        IntelligenceItem(
                            id=IntelligenceItem.generate_id(
                                full_name, f"https://github.com/{full_name}"
                            ),
                            title=f"[Trending] {full_name}",
                            source_type=SourceType.GITHUB_TRENDING,
                            source_name="GitHub Trending",
                            url=f"https://github.com/{full_name}",
                            category=IntelligenceCategory.AGENT_FRAMEWORK,
                            priority=Priority.HIGH,
                            summary=description[:300],
                            tags=["trending"],
                            metadata={"repo": full_name},
                        )
                    )
        except Exception as e:
            logger.warning(f"Failed to fetch trending: {e}")
        return items

    def _extract_insights(self, text: str) -> list[str]:
        """从 Release Notes 提取关键信息"""
        if not text:
            return []
        insights = []
        lines = text.split("\n")
        for line in lines:
            line = line.strip().lstrip("-*# ")
            if not line:
                continue
            if any(
                kw in line.lower()
                for kw in [
                    "feature",
                    "improve",
                    "add",
                    "fix",
                    "new",
                    "breaking",
                    "deprecate",
                    "self-improving",
                    "skill",
                    "memory",
                    "auto",
                    "evolve",
                    "learn",
                ]
            ):
                insights.append(line[:200])
        return insights[:8]


# ============================================================
# arXiv 采集器
# ============================================================


class ArxivCollector(BaseCollector):
    """arXiv 论文采集"""

    ARXIV_API = "http://export.arxiv.org/api/query"

    async def collect(self) -> CollectionResult:
        items: list[IntelligenceItem] = []
        errors: list[str] = []
        start = time.monotonic()

        categories = self.config.get("arxiv_categories", [])
        for cat in categories:
            try:
                cat_items = await self._collect_category(cat)
                items.extend(cat_items)
            except Exception as e:
                errors.append(f"arXiv {cat['category']}: {e}")

        return CollectionResult(
            source_type=SourceType.ARXIV,
            source_name="arXiv",
            items=items,
            errors=errors,
            duration_ms=(time.monotonic() - start) * 1000,
        )

    async def _collect_category(self, cat: dict) -> list[IntelligenceItem]:
        items: list[IntelligenceItem] = []
        keywords = " OR ".join(f'all:"{kw}"' for kw in cat.get("keywords", []))
        query = f"search_query={keywords}&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending"
        cat_filter = cat.get("category", "cs.AI")
        query += f"&cat:{cat_filter}"

        try:
            xml_text = await self._fetch(f"{self.ARXIV_API}?{query}")
            from xml.etree import ElementTree as ET

            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                link = entry.find("atom:id", ns)
                published = entry.find("atom:published", ns)

                title_text = title.text.strip() if title is not None and title.text else ""
                summary_text = (
                    summary.text.strip()[:500] if summary is not None and summary.text else ""
                )
                link_text = link.text.strip() if link is not None and link.text else ""

                items.append(
                    IntelligenceItem(
                        id=IntelligenceItem.generate_id(title_text, link_text),
                        title=title_text,
                        source_type=SourceType.ARXIV,
                        source_name=f"arXiv:{cat_filter}",
                        url=link_text,
                        category=IntelligenceCategory.AGENT_FRAMEWORK,
                        priority=Priority(cat.get("priority", "medium")),
                        summary=summary_text,
                        key_insights=self._extract_paper_insights(summary_text),
                        tags=[cat_filter],
                        metadata={
                            "category": cat_filter,
                            "published": published.text if published is not None else "",
                        },
                    )
                )
        except Exception as e:
            logger.warning(f"arXiv {cat_filter} failed: {e}")
        return items

    def _extract_paper_insights(self, abstract: str) -> list[str]:
        """从论文摘要提取关键发现"""
        insights = []
        sentences = abstract.split(". ")
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if any(
                kw in sent.lower()
                for kw in [
                    "propose",
                    "achieve",
                    "improve",
                    "outperform",
                    "novel",
                    "state-of-the-art",
                    "self-improving",
                    "self-evolving",
                    "continual",
                    "autonomous",
                    "agent",
                ]
            ):
                sent = sent[:200]
                if sent and sent[-1] != ".":
                    sent += "."
                insights.append(sent)
        return insights[:5]


# ============================================================
# 技术博客采集器
# ============================================================


class TechBlogCollector(BaseCollector):
    """大厂技术博客采集"""

    async def collect(self) -> CollectionResult:
        items: list[IntelligenceItem] = []
        errors: list[str] = []
        start = time.monotonic()

        blogs = self.config.get("tech_blogs", [])
        ai_keywords = [
            "agent",
            "llm",
            "gpt",
            "claude",
            "gemini",
            "autonomous",
            "self-improving",
            "multi-agent",
            "tool",
            "reasoning",
            "memory",
            "multi-modal",
            "safety",
            "alignment",
        ]

        for blog in blogs:
            try:
                html = await self._fetch(blog["url"])
                # 提取标题和链接
                link_pattern = r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:agent|Agent|LLM|llm|GPT|Claude|Gemini|autonomous|self-improving|multi-agent|tool|reasoning|memory)[^<]*)</a>'
                matches = re.findall(link_pattern, html, re.IGNORECASE)
                seen = set()
                for href, text in matches:
                    text = re.sub(r"<[^>]+>", "", text).strip()
                    if not text or text in seen:
                        continue
                    seen.add(text)
                    if any(kw in text.lower() for kw in ai_keywords):
                        full_url = (
                            href
                            if href.startswith("http")
                            else f"{blog['url'].rstrip('/')}/{href.lstrip('/')}"
                        )
                        items.append(
                            IntelligenceItem(
                                id=IntelligenceItem.generate_id(text, full_url),
                                title=f"[{blog['name']}] {text}",
                                source_type=SourceType.TECH_BLOG,
                                source_name=blog["name"],
                                url=full_url,
                                category=IntelligenceCategory(
                                    blog.get("category", "frontier_research")
                                ),
                                priority=Priority(blog.get("priority", "high")),
                                summary=text,
                                tags=[blog["name"]],
                                metadata={"blog": blog["name"]},
                            )
                        )
            except Exception as e:
                errors.append(f"{blog['name']}: {e}")

        return CollectionResult(
            source_type=SourceType.TECH_BLOG,
            source_name="Tech Blogs",
            items=items,
            errors=errors,
            duration_ms=(time.monotonic() - start) * 1000,
        )


# ============================================================
# 采集引擎
# ============================================================


class IntelligenceCollector:
    """智能信息采集引擎 — 统一调度所有采集器"""

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or str(
            Path(__file__).parent.parent.parent.parent / "config" / "intelligence_sources.yaml"
        )
        self.config = self._load_config()
        self._client: httpx.AsyncClient | None = None
        self._collectors: dict[SourceType, BaseCollector] = {}

    def _load_config(self) -> dict[str, Any]:
        with open(self.config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": "FnixAgent-Intelligence/1.0"}, timeout=30.0
            )
        return self._client

    def _init_collectors(self) -> dict[str, BaseCollector]:
        """初始化所有采集器"""
        client = asyncio.get_event_loop().run_until_complete(self._get_client())
        return {
            "github": GitHubCollector(client, self.config.get("sources", {})),
            "arxiv": ArxivCollector(client, self.config.get("sources", {})),
            "tech_blogs": TechBlogCollector(client, self.config.get("sources", {})),
        }

    async def collect_all(self, frequency: str = "daily") -> list[CollectionResult]:
        """按频率执行全量采集"""
        client = await self._get_client()
        sources = self.config.get("sources", {})

        strategy = self.config.get("collection_strategy", {}).get(frequency, [])
        source_map = {
            "github_trending": GitHubCollector(client, sources),
            "github_repo_releases": GitHubCollector(client, sources),
            "arxiv_new_papers": ArxivCollector(client, sources),
            "tech_blog_posts": TechBlogCollector(client, sources),
            "hn_ai_threads": TechBlogCollector(client, sources),
        }

        tasks = []
        for source_key in strategy:
            collector = source_map.get(source_key)
            if collector:
                tasks.append(collector.collect())

        results = await asyncio.gather(*tasks, return_exceptions=True)
        output: list[CollectionResult] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Collection failed: {result}")
            else:
                output.append(result)
        return output

    async def collect_and_save(
        self, frequency: str = "daily", output_dir: str | None = None
    ) -> int:
        """采集并保存到文件"""
        if output_dir is None:
            output_dir = str(Path(__file__).parent.parent.parent.parent / "assets" / "intelligence")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        results = await self.collect_all(frequency)
        total_items = 0
        for result in results:
            total_items += len(result.items)

        # 保存原始数据
        data = {
            "collected_at": datetime.now(UTC).isoformat(),
            "frequency": frequency,
            "total_items": total_items,
            "results": [
                {
                    "source_type": r.source_type.value,
                    "source_name": r.source_name,
                    "items_count": len(r.items),
                    "errors": r.errors,
                    "items": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "url": item.url,
                            "category": item.category.value,
                            "priority": item.priority.value,
                            "summary": item.summary,
                            "key_insights": item.key_insights,
                            "tags": item.tags,
                            "metadata": item.metadata,
                        }
                        for item in r.items
                    ],
                }
                for r in results
            ],
        }

        date_str = datetime.now(UTC).strftime("%Y%m%d")
        output_path = Path(output_dir) / f"intelligence_{frequency}_{date_str}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Collected {total_items} items, saved to {output_path}")
        return total_items

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
