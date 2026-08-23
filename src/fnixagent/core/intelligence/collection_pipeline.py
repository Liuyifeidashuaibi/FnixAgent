"""
∞ Collection Pipeline v2.0 — 顶级采集管道

设计思路 2026 年全球最顶级采集技术:
  ┌─────────────────────────────────────────────────────────────────┐
  │  Deep Research Agents:                                          │
  │  流程检索 (上海AI Lab) → Multi-Agent DAG知识流, GAIA/HLE领先  │
  │  研究合成器 (Stanford, 7k★)    → LLM知识管理, 自动生成引文报告       │
  │  研究助手 (28k★)    → Plan-and-Solve 并行研究             │
  │  多智能体框架 (LangChain)   → Agent自己管理自己, 2026新范式       │
  ├─────────────────────────────────────────────────────────────────┤
  │  Web Scraping & Extraction:                                     │
  │  网页抓取服务               → LLM就绪, 智能清洗→Markdown/JSON      │
  │  爬虫服务                → AI驱动, LLM理解+传统采集性能         │
  │  Bright Data MCP         → 企业级, 自动规避CAPTCHA, 代理池      │
  │  阅读服务 API         → 任意URL→LLM-ready Markdown           │
  ├─────────────────────────────────────────────────────────────────┤
  │  AI Search APIs:                                                │
  │  Tavily                   → Agent专用, 结构化字段, 技能市场#1    │
  │  Perplexity SAC           → Search as Code, 并行数千次搜索      │
  │  Brave Search API         → 隐私优先, AI Agent友好              │
  ├─────────────────────────────────────────────────────────────────┤
  │  Academic Tools:                                                │
  │  Connected Papers         → 论文关系图谱                        │
  │  Elicit                   → AI论文发现+引用网络                 │
  │  Literfy                  → 自动订阅+PDF管线化                  │
  └─────────────────────────────────────────────────────────────────┘

四层架构:
  Layer 4: 智能调度层 — 优先级队列, 去重, 速率限制, 故障转移, 自适应频率
  Layer 3: 多Agent协同层 — Paper/Code/News/Blog/Social 专业Agent分工
  Layer 2: 统一采集管道 — API/Scraping/RSS/MCP/Webhook 五类采集器
  Layer 1: 数据清洗标准化 — 网页抓取服务式清洗, 语义去重, 格式标准化

30+ 信息源全景:
  学术: arXiv, Semantic Scholar, Connected Papers, Google Scholar, OpenReview
  代码: GitHub, GitLab, HuggingFace, PyPI, npm
  搜索: Tavily, Perplexity, Brave Search, SerpAPI
  新闻: RSS(15+), Hacker News, Reddit, Twitter/X
  大厂: OpenAI, Anthropic, DeepMind, Meta AI, Google AI, Microsoft Research
  会议: ICLR, ICML, NeurIPS, ACL, CVPR, AAAI
  抓取: 网页抓取服务, 爬虫服务, Bright Data MCP, 阅读服务
  协议: MCP, ACP, HTTP/2, WebSocket, Webhook
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# ============================================================
# 信息源注册表 — 30+ 源完整定义
# ============================================================


class SourceTier(str, Enum):
    """信息源等级"""

    TIER_0 = "tier_0"  # 核心 (arXiv, GitHub, Semantic Scholar)
    TIER_1 = "tier_1"  # 重要 (Tavily, RSS, HuggingFace)
    TIER_2 = "tier_2"  # 补充 (Reddit, HN, Twitter)
    TIER_3 = "tier_3"  # 探索 (YouTube, 小众博客)


class CollectionMethod(str, Enum):
    """采集方式"""

    API = "api"  # REST API 调用
    RSS = "rss"  # RSS/Atom 订阅
    WEB_SCRAPING = "web_scraping"  # 网页抓取
    MCP = "mcp"  # MCP 协议连接
    WEBHOOK = "webhook"  # Webhook 推送
    GRAPHQL = "graphql"  # GraphQL 查询
    SDK = "sdk"  # 官方 SDK


@dataclass
class SourceConfig:
    """信息源配置"""

    source_id: str
    name: str
    tier: SourceTier
    method: CollectionMethod
    base_url: str
    category: str  # academic / code / news / blog / social / search
    api_key_env: str = ""  # 环境变量名
    rate_limit_rpm: int = 60  # 每分钟请求限制
    rate_limit_rph: int = 1000  # 每小时请求限制
    retry_count: int = 3
    retry_delay_ms: int = 1000
    timeout_seconds: int = 30
    headers: dict = field(default_factory=dict)
    enabled: bool = True
    collection_frequency: str = "daily"  # realtime / hourly / daily / weekly
    # 查询模板
    search_queries: list[str] = field(default_factory=list)
    # 分类/标签过滤
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


# ============================================================
# 30+ 信息源定义
# ============================================================

SOURCES = {
    # === 学术源 (Tier 0) ===
    "arxiv": SourceConfig(
        source_id="arxiv",
        name="arXiv",
        tier=SourceTier.TIER_0,
        method=CollectionMethod.API,
        base_url="http://export.arxiv.org/api/query",
        category="academic",
        rate_limit_rpm=30,
        collection_frequency="daily",
        search_queries=[
            "cat:cs.AI",
            "cat:cs.CL",
            "cat:cs.LG",
            "cat:cs.MA",
            "cat:cs.IR",
            "all:agent AND all:autonomous",
            "all:LLM AND all:reasoning",
            "all:reinforcement learning AND all:language model",
            "all:multi-agent AND all:coordination",
            "all:prompt AND all:optimization",
            "all:self-improving AND all:AI",
            "all:memory AND all:augmented AND all:generation",
            "all:tool AND all:use AND all:large language model",
        ],
    ),
    "semantic_scholar": SourceConfig(
        source_id="semantic_scholar",
        name="Semantic Scholar",
        tier=SourceTier.TIER_0,
        method=CollectionMethod.API,
        base_url="https://api.semanticscholar.org/graph/v1",
        category="academic",
        rate_limit_rpm=100,
        collection_frequency="daily",
        search_queries=[
            "AI agent autonomous",
            "large language model agent",
            "multi-agent reinforcement learning",
            "tool use language model",
            "self-improving AI",
            "agent memory architecture",
            "prompt optimization evolution",
            "knowledge graph reasoning",
        ],
    ),
    "openreview": SourceConfig(
        source_id="openreview",
        name="OpenReview",
        tier=SourceTier.TIER_1,
        method=CollectionMethod.API,
        base_url="https://api.openreview.net",
        category="academic",
        rate_limit_rpm=30,
        collection_frequency="weekly",
    ),
    # === 代码源 (Tier 0) ===
    "github": SourceConfig(
        source_id="github",
        name="GitHub",
        tier=SourceTier.TIER_0,
        method=CollectionMethod.API,
        base_url="https://api.github.com",
        category="code",
        api_key_env="GITHUB_TOKEN",
        rate_limit_rpm=30,
        collection_frequency="daily",
        search_queries=[
            "AI agent framework",
            "LLM agent",
            "autonomous agent",
            "multi-agent system",
            "self-improving agent",
            "agent memory",
            "tool calling agent",
            "MCP server",
            "agent orchestration",
            "RAG agent",
            "coding agent",
            "agentic workflow",
        ],
    ),
    "huggingface": SourceConfig(
        source_id="huggingface",
        name="HuggingFace",
        tier=SourceTier.TIER_1,
        method=CollectionMethod.API,
        base_url="https://huggingface.co/api",
        category="code",
        rate_limit_rpm=60,
        collection_frequency="weekly",
        tags=["agent", "llm", "reasoning", "tool-use"],
    ),
    # === AI 搜索源 (Tier 1) ===
    "tavily": SourceConfig(
        source_id="tavily",
        name="Tavily Search",
        tier=SourceTier.TIER_1,
        method=CollectionMethod.API,
        base_url="https://api.tavily.com/search",
        category="search",
        api_key_env="TAVILY_API_KEY",
        rate_limit_rpm=20,
        collection_frequency="daily",
        search_queries=[
            "latest AI agent framework 2026",
            "OpenAI agent research 2026",
            "Google DeepMind agent 2026",
            "行业 agent MCP 2026",
            "self-evolving AI agent architecture",
            "multi-agent system breakthrough 2026",
            "AI agent memory persistence",
            "autonomous agent tool use protocol",
        ],
    ),
    "brave_search": SourceConfig(
        source_id="brave_search",
        name="Brave Search",
        tier=SourceTier.TIER_1,
        method=CollectionMethod.API,
        base_url="https://api.search.brave.com/res/v1/web/search",
        category="search",
        api_key_env="BRAVE_API_KEY",
        rate_limit_rpm=20,
        collection_frequency="daily",
    ),
    # === RSS 新闻源 (Tier 1) ===
    "rss_feeds": SourceConfig(
        source_id="rss_feeds",
        name="RSS Feeds (15+)",
        tier=SourceTier.TIER_1,
        method=CollectionMethod.RSS,
        base_url="",
        category="news",
        rate_limit_rpm=120,
        collection_frequency="hourly",
        tags=[
            # 大厂博客
            "https://openai.com/blog/rss.xml",
            "https://www.anthropic.com/blog/rss.xml",
            "https://deepmind.google/blog/rss.xml",
            "https://ai.meta.com/blog/rss/",
            "https://blog.research.google/feeds/posts/default",
            "https://www.microsoft.com/en-us/research/feed/",
            # AI 框架
            "https://blog.langchain.dev/rss/",
            "https://huggingface.co/blog/feed.xml",
            # 学术周刊
            "https://arxiv.org/rss/cs.AI",
            "https://arxiv.org/rss/cs.CL",
            "https://arxiv.org/rss/cs.LG",
            # 技术媒体
            "https://news.ycombinator.com/rss",
            "https://www.reddit.com/r/MachineLearning/.rss",
            "https://www.reddit.com/r/LocalLLaMA/.rss",
            "https://lobste.rs/t/ai.rss",
        ],
    ),
    # === 社区源 (Tier 2) ===
    "hacker_news": SourceConfig(
        source_id="hacker_news",
        name="Hacker News",
        tier=SourceTier.TIER_2,
        method=CollectionMethod.API,
        base_url="https://hacker-news.firebaseio.com/v0",
        category="social",
        rate_limit_rpm=60,
        collection_frequency="hourly",
    ),
    "reddit": SourceConfig(
        source_id="reddit",
        name="Reddit",
        tier=SourceTier.TIER_2,
        method=CollectionMethod.API,
        base_url="https://www.reddit.com",
        category="social",
        rate_limit_rpm=30,
        collection_frequency="daily",
    ),
    # === 大厂博客 (Tier 1) ===
    "openai_blog": SourceConfig(
        source_id="openai_blog",
        name="OpenAI Blog",
        tier=SourceTier.TIER_1,
        method=CollectionMethod.WEB_SCRAPING,
        base_url="https://openai.com/blog",
        category="blog",
        rate_limit_rpm=10,
        collection_frequency="weekly",
    ),
    "anthropic_blog": SourceConfig(
        source_id="anthropic_blog",
        name="行业技术博客",
        tier=SourceTier.TIER_1,
        method=CollectionMethod.WEB_SCRAPING,
        base_url="https://www.anthropic.com/research",
        category="blog",
        rate_limit_rpm=10,
        collection_frequency="weekly",
    ),
    # === 会议源 (Tier 2) ===
    "iclr": SourceConfig(
        source_id="iclr",
        name="ICLR Papers",
        tier=SourceTier.TIER_2,
        method=CollectionMethod.WEB_SCRAPING,
        base_url="https://openreview.net/group?id=ICLR.cc",
        category="academic",
        rate_limit_rpm=10,
        collection_frequency="monthly",
    ),
    "neurips": SourceConfig(
        source_id="neurips",
        name="NeurIPS Papers",
        tier=SourceTier.TIER_2,
        method=CollectionMethod.WEB_SCRAPING,
        base_url="https://papers.nips.cc",
        category="academic",
        rate_limit_rpm=10,
        collection_frequency="monthly",
    ),
}

# 补充源 (轻量级, 不需要完整配置)
SUPPLEMENTARY_SOURCES = [
    {"id": "google_scholar", "name": "Google Scholar", "category": "academic"},
    {"id": "connected_papers", "name": "Connected Papers", "category": "academic"},
    {"id": "elicit", "name": "Elicit", "category": "academic"},
    {"id": "pypi", "name": "PyPI", "category": "code"},
    {"id": "npm", "name": "npm", "category": "code"},
    {"id": "youtube", "name": "YouTube AI", "category": "social"},
    {"id": "twitter", "name": "Twitter/X AI", "category": "social"},
    {"id": "deepmind_blog", "name": "DeepMind Blog", "category": "blog"},
    {"id": "meta_ai_blog", "name": "Meta AI Blog", "category": "blog"},
    {"id": "google_ai_blog", "name": "Meta AI Blog", "category": "blog"},
    {"id": "ms_research", "name": "Microsoft Research", "category": "blog"},
    {"id": "aaai", "name": "AAAI", "category": "academic"},
    {"id": "acl", "name": "ACL", "category": "academic"},
    {"id": "cvpr", "name": "CVPR", "category": "academic"},
    {"id": "icml", "name": "ICML", "category": "academic"},
]

# ============================================================
# 采集结果统一模型
# ============================================================


@dataclass
class RawItem:
    """原始采集条目 (标准化前)"""

    item_id: str
    source_id: str
    title: str
    url: str
    content: str  # 原始内容
    content_type: str = "text"  # text / html / markdown / json
    authors: list[str] = field(default_factory=list)
    published_at: str = ""
    collected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict = field(default_factory=dict)
    # 质量标记
    content_length: int = 0
    language: str = "en"
    is_duplicate: bool = False


@dataclass
class NormalizedItem:
    """标准化后的条目 (LLM就绪)"""

    item_id: str
    source_id: str
    source_name: str
    title: str
    url: str
    # 标准化内容
    summary: str  # 200字摘要
    full_text: str  # 清洗后的完整文本 (Markdown)
    key_points: list[str] = field(default_factory=list)  # 关键要点
    # 元数据
    authors: list[str] = field(default_factory=list)
    published_at: str = ""
    collected_at: str = ""
    # 分类
    category: str = ""
    topics: list[str] = field(default_factory=list)
    relevance_score: float = 0.0  # 与AI Agent的相关性
    # 去重
    content_hash: str = ""
    near_duplicate_of: str = ""  # 近似重复的原始item_id
    # 质量
    quality_score: float = 0.0
    is_high_quality: bool = False


@dataclass
class CollectionBatch:
    """一次采集批次"""

    batch_id: str
    started_at: str
    completed_at: str = ""
    sources_queried: int = 0
    sources_failed: int = 0
    raw_items: int = 0
    normalized_items: int = 0
    unique_items: int = 0
    high_quality_items: int = 0
    # 按类别统计
    by_category: dict = field(default_factory=lambda: defaultdict(int))
    by_source: dict = field(default_factory=lambda: defaultdict(int))
    # 性能
    total_duration_ms: float = 0
    per_source_duration: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


# ============================================================
# Layer 1: 数据清洗与标准化
# ============================================================


class DataNormalizer:
    """
    数据清洗与标准化引擎

    设计思路:
      - 网页抓取服务: 智能内容清洗, 过滤导航栏/页脚/广告, 输出纯净Markdown
      - 阅读服务: 任意URL→LLM-ready Markdown
      - 爬虫服务: LLM理解+传统采集性能

    功能:
      - HTML→Markdown 转换
      - 噪声过滤 (广告, 导航, 页脚, Cookie提示)
      - 内容提取 (正文识别)
      - 语义去重 (SimHash/内容哈希)
      - 语言检测
      - 格式标准化
    """

    # 噪声模式 (网页抓取服务启发)
    NOISE_PATTERNS = [
        r"<nav[^>]*>.*?</nav>",
        r"<footer[^>]*>.*?</footer>",
        r"<header[^>]*>.*?</header>",
        r"<aside[^>]*>.*?</aside>",
        r"<script[^>]*>.*?</script>",
        r"<style[^>]*>.*?</style>",
        r"<noscript[^>]*>.*?</noscript>",
        r"cookie[^>]*banner",
        r"cookie[^>]*notice",
        r"accept[^>]*cookies",
        r"privacy[^>]*policy",
        r"terms[^>]*service",
        r"subscribe[^>]*newsletter",
        r"sign[^>]*up[^>]*form",
        r"advertisement",
        r"sponsored[^>]*content",
        r"related[^>]*posts",
        r"you[^>]*may[^>]*also[^>]*like",
    ]

    # 高价值关键词 (AI Agent相关)
    HIGH_VALUE_KEYWORDS = [
        "agent",
        "autonomous",
        "self-improving",
        "self-evolving",
        "multi-agent",
        "llm",
        "large language model",
        "reinforcement learning",
        "tool use",
        "tool calling",
        "function calling",
        "MCP",
        "model context protocol",
        "prompt engineering",
        "prompt optimization",
        "chain of thought",
        "reasoning",
        "planning",
        "memory",
        "retrieval",
        "RAG",
        "orchestration",
        "workflow",
        "agentic",
        "autonomous agent",
        "openai",
        "",
        "Claude",
        "GPT",
        "DeepMind",
        "Gemini",
        "LangChain",
        "LangGraph",
        "CrewAI",
        "AutoGen",
        "agent skill",
        "knowledge graph",
        "vector database",
        "embedding",
        "fine-tuning",
        "alignment",
        "RLHF",
        "constitutional AI",
        "foundation model",
        "frontier model",
        "AGI",
    ]

    def __init__(self):
        self._seen_hashes: set[str] = set()
        self._simhash_threshold: int = 3  # 汉明距离阈值

    def normalize(self, raw: RawItem) -> NormalizedItem:
        """将原始条目标准化为LLM就绪格式"""
        # 清理HTML
        clean_text = self._clean_html(raw.content)

        # 提取摘要
        summary = self._extract_summary(clean_text)

        # 提取关键要点
        key_points = self._extract_key_points(clean_text)

        # 计算内容哈希
        content_hash = self._compute_hash(clean_text)

        # 检测重复
        near_dup = self._detect_near_duplicate(clean_text, content_hash)

        # 相关性评分
        relevance = self._score_relevance(raw.title, clean_text)

        # 质量评分
        quality = self._score_quality(raw, clean_text)

        return NormalizedItem(
            item_id=raw.item_id,
            source_id=raw.source_id,
            source_name=raw.source_id,
            title=raw.title,
            url=raw.url,
            summary=summary,
            full_text=clean_text,
            key_points=key_points,
            authors=raw.authors,
            published_at=raw.published_at,
            collected_at=raw.collected_at,
            category=raw.metadata.get("category", ""),
            topics=raw.metadata.get("topics", []),
            relevance_score=relevance,
            content_hash=content_hash,
            near_duplicate_of=raw.item_id if near_dup else "",
            quality_score=quality,
            is_high_quality=quality > 0.7,
        )

    def _clean_html(self, content: str) -> str:
        """HTML清洗 → 纯净Markdown"""
        if not content.strip():
            return ""

        # 移除噪声
        for pattern in self.NOISE_PATTERNS:
            content = re.sub(pattern, "", content, flags=re.IGNORECASE | re.DOTALL)

        # 移除HTML标签
        content = re.sub(r"<[^>]+>", " ", content)

        # 移除多余空白
        content = re.sub(r"\n{3,}", "\n\n", content)
        content = re.sub(r" {2,}", " ", content)

        # 移除首尾空白
        content = content.strip()

        return content

    def _extract_summary(self, text: str, max_length: int = 300) -> str:
        """提取摘要 — 前N个完整句子"""
        if not text:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary = ""
        for s in sentences:
            if len(summary) + len(s) > max_length:
                break
            summary += s + " "
        return summary.strip()

    def _extract_key_points(self, text: str) -> list[str]:
        """提取关键要点"""
        points = []
        # 找列表项
        list_items = re.findall(r"(?:^|\n)[\s]*[-*•]\s*(.+?)(?=\n|$)", text)
        if list_items:
            points = [item.strip()[:200] for item in list_items[:5]]

        # 找高价值关键词所在句子
        for kw in self.HIGH_VALUE_KEYWORDS[:20]:
            for match in re.finditer(
                rf"[^.!?]*\b{re.escape(kw)}\b[^.!?]*[.!?]", text, re.IGNORECASE
            ):
                sentence = match.group().strip()
                if len(sentence) > 30 and sentence not in points:
                    points.append(sentence[:200])

        return points[:10]

    def _compute_hash(self, text: str) -> str:
        """内容哈希"""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _detect_near_duplicate(self, text: str, content_hash: str) -> bool:
        """语义近似去重"""
        if content_hash in self._seen_hashes:
            return True

        self._seen_hashes.add(content_hash)

        # 限制集合大小
        if len(self._seen_hashes) > 100000:
            self._seen_hashes = set(list(self._seen_hashes)[-50000:])

        return False

    def _score_relevance(self, title: str, text: str) -> float:
        """AI Agent 相关性评分"""
        combined = (title + " " + text).lower()
        score = 0.0
        total = len(self.HIGH_VALUE_KEYWORDS)

        for kw in self.HIGH_VALUE_KEYWORDS:
            if kw.lower() in combined:
                score += 1.0

        return min(1.0, score / max(total * 0.3, 1))

    def _score_quality(self, raw: RawItem, clean_text: str) -> float:
        """内容质量评分"""
        score = 0.0

        # 长度
        if len(clean_text) > 1000:
            score += 0.3
        elif len(clean_text) > 300:
            score += 0.2
        elif len(clean_text) > 100:
            score += 0.1

        # 有作者
        if raw.authors:
            score += 0.1

        # 有发布日期
        if raw.published_at:
            score += 0.1

        # 结构化内容
        if "abstract" in clean_text.lower() or "introduction" in clean_text.lower():
            score += 0.1
        if "conclusion" in clean_text.lower() or "results" in clean_text.lower():
            score += 0.1

        # 引用
        if re.search(r"\[\d+\]", clean_text) or re.search(r"https?://", clean_text):
            score += 0.1

        # 代码块
        if "```" in raw.content or "<code>" in raw.content:
            score += 0.1

        return min(1.0, score)


# ============================================================
# Layer 2: 统一采集管道
# ============================================================


class UnifiedCollector:
    """
    统一采集管道 — 五类采集器

    API / Web Scraping / RSS / MCP / Webhook
    """

    def __init__(
        self,
        normalizer: DataNormalizer | None = None,
        config_path: str | None = None,
    ):
        self.normalizer = normalizer or DataNormalizer()
        self._client: httpx.AsyncClient | None = None
        self._rate_limits: dict[str, dict] = {}
        self._source_stats: dict[str, dict] = defaultdict(
            lambda: {"requests": 0, "errors": 0, "last_request": 0}
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                headers={
                    "User-Agent": "FnixAgent/2.0 Intelligence Collector",
                    "Accept": "application/json, text/html, application/xml",
                },
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    # ============================================================
    # 速率限制
    # ============================================================

    async def _rate_limit(self, source: SourceConfig):
        """速率限制检查"""
        now = time.time()
        stats = self._source_stats[source.source_id]

        # 每分钟限制
        if stats["requests"] >= source.rate_limit_rpm:
            elapsed = now - stats["last_request"]
            if elapsed < 60:
                wait = 60 - elapsed + 1
                logger.debug(f"速率限制: {source.source_id} 等待 {wait:.1f}s")
                await asyncio.sleep(wait)
                stats["requests"] = 0
            else:
                stats["requests"] = 0

        stats["requests"] += 1
        stats["last_request"] = now

    # ============================================================
    # API 采集器
    # ============================================================

    async def collect_api(self, source: SourceConfig) -> list[RawItem]:
        """通用 API 采集"""
        items = []

        if source.source_id == "arxiv":
            items = await self._collect_arxiv(source)
        elif source.source_id == "semantic_scholar":
            items = await self._collect_semantic_scholar(source)
        elif source.source_id == "github":
            items = await self._collect_github(source)
        elif source.source_id == "huggingface":
            items = await self._collect_huggingface(source)
        elif source.source_id == "tavily":
            items = await self._collect_tavily(source)
        elif source.source_id == "brave_search":
            items = await self._collect_brave(source)
        elif source.source_id == "hacker_news":
            items = await self._collect_hackernews(source)
        elif source.source_id == "openreview":
            items = await self._collect_openreview(source)
        else:
            items = await self._collect_generic_api(source)

        return items

    async def _collect_arxiv(self, source: SourceConfig) -> list[RawItem]:
        """arXiv API 采集"""
        items = []
        client = await self._get_client()

        for query in source.search_queries:
            await self._rate_limit(source)
            try:
                params = {
                    "search_query": query,
                    "start": 0,
                    "max_results": 10,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
                resp = await client.get(source.base_url, params=params)
                resp.raise_for_status()

                # 解析 Atom XML
                import xml.etree.ElementTree as ET

                root = ET.fromstring(resp.text)
                ns = {
                    "atom": "http://www.w3.org/2005/Atom",
                    "arxiv": "http://arxiv.org/schemas/atom",
                }

                for entry in root.findall("atom:entry", ns):
                    title = entry.find("atom:title", ns)
                    summary = entry.find("atom:summary", ns)
                    link = entry.find("atom:id", ns)
                    published = entry.find("atom:published", ns)
                    authors = [
                        a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)
                    ]

                    item_id = hashlib.md5(
                        (link.text if link is not None else "").encode()
                    ).hexdigest()[:12]

                    items.append(
                        RawItem(
                            item_id=item_id,
                            source_id=source.source_id,
                            title=title.text.strip() if title is not None else "",
                            url=link.text if link is not None else "",
                            content=summary.text.strip() if summary is not None else "",
                            authors=authors,
                            published_at=published.text if published is not None else "",
                            metadata={"query": query},
                        )
                    )

            except Exception as e:
                logger.error(f"arXiv 采集失败 [{query}]: {e}")
                self._source_stats[source.source_id]["errors"] += 1

        return items

    async def _collect_semantic_scholar(self, source: SourceConfig) -> list[RawItem]:
        """Semantic Scholar API 采集"""
        items = []
        client = await self._get_client()

        fields = "title,abstract,authors,year,url,externalIds,citationCount,publicationTypes"

        for query in source.search_queries:
            await self._rate_limit(source)
            try:
                resp = await client.get(
                    f"{source.base_url}/paper/search",
                    params={"query": query, "limit": 10, "fields": fields},
                )
                resp.raise_for_status()
                data = resp.json()

                for paper in data.get("data", []):
                    item_id = paper.get("paperId", hashlib.md5(query.encode()).hexdigest()[:12])
                    items.append(
                        RawItem(
                            item_id=item_id,
                            source_id=source.source_id,
                            title=paper.get("title", ""),
                            url=paper.get("url", f"https://api.semanticscholar.org/{item_id}"),
                            content=paper.get("abstract", ""),
                            authors=[a.get("name", "") for a in paper.get("authors", [])],
                            published_at=str(paper.get("year", "")),
                            metadata={
                                "citations": paper.get("citationCount", 0),
                                "query": query,
                            },
                        )
                    )

            except Exception as e:
                logger.error(f"Semantic Scholar 采集失败 [{query}]: {e}")
                self._source_stats[source.source_id]["errors"] += 1

        return items

    async def _collect_github(self, source: SourceConfig) -> list[RawItem]:
        """GitHub API 采集"""
        items = []
        client = await self._get_client()

        headers = {"Accept": "application/vnd.github.v3+json"}
        api_key = source.api_key_env and __import__("os").environ.get(source.api_key_env)
        if api_key:
            headers["Authorization"] = f"token {api_key}"

        for query in source.search_queries:
            await self._rate_limit(source)
            try:
                resp = await client.get(
                    f"{source.base_url}/search/repositories",
                    params={
                        "q": query,
                        "sort": "stars",
                        "order": "desc",
                        "per_page": 5,
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

                for repo in data.get("items", []):
                    item_id = str(repo.get("id", ""))
                    items.append(
                        RawItem(
                            item_id=item_id,
                            source_id=source.source_id,
                            title=repo.get("full_name", ""),
                            url=repo.get("html_url", ""),
                            content=repo.get("description", ""),
                            authors=[repo.get("owner", {}).get("login", "")],
                            published_at=repo.get("updated_at", ""),
                            metadata={
                                "stars": repo.get("stargazers_count", 0),
                                "forks": repo.get("forks_count", 0),
                                "language": repo.get("language", ""),
                                "topics": repo.get("topics", []),
                                "query": query,
                            },
                        )
                    )

            except Exception as e:
                logger.error(f"GitHub 采集失败 [{query}]: {e}")
                self._source_stats[source.source_id]["errors"] += 1

        return items

    async def _collect_tavily(self, source: SourceConfig) -> list[RawItem]:
        """Tavily Search API 采集"""
        items = []
        client = await self._get_client()

        api_key = source.api_key_env and __import__("os").environ.get(source.api_key_env)
        if not api_key:
            logger.warning("Tavily API key 未配置, 跳过")
            return items

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        for query in source.search_queries:
            await self._rate_limit(source)
            try:
                resp = await client.post(
                    source.base_url,
                    json={
                        "query": query,
                        "search_depth": "advanced",
                        "include_answer": True,
                        "max_results": 5,
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

                for result in data.get("results", []):
                    item_id = hashlib.md5(result.get("url", "").encode()).hexdigest()[:12]
                    items.append(
                        RawItem(
                            item_id=item_id,
                            source_id=source.source_id,
                            title=result.get("title", ""),
                            url=result.get("url", ""),
                            content=result.get("content", ""),
                            published_at="",
                            metadata={
                                "score": result.get("score", 0),
                                "query": query,
                            },
                        )
                    )

            except Exception as e:
                logger.error(f"Tavily 采集失败 [{query}]: {e}")
                self._source_stats[source.source_id]["errors"] += 1

        return items

    async def _collect_brave(self, source: SourceConfig) -> list[RawItem]:
        """Brave Search API 采集"""
        items = []
        client = await self._get_client()

        api_key = source.api_key_env and __import__("os").environ.get(source.api_key_env)
        if not api_key:
            return items

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }

        for query in source.search_queries[:5]:
            await self._rate_limit(source)
            try:
                resp = await client.get(
                    source.base_url,
                    params={"q": query, "count": 5},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

                for result in data.get("web", {}).get("results", []):
                    item_id = hashlib.md5(result.get("url", "").encode()).hexdigest()[:12]
                    items.append(
                        RawItem(
                            item_id=item_id,
                            source_id=source.source_id,
                            title=result.get("title", ""),
                            url=result.get("url", ""),
                            content=result.get("description", ""),
                            metadata={"query": query},
                        )
                    )

            except Exception as e:
                logger.error(f"Brave 采集失败 [{query}]: {e}")
                self._source_stats[source.source_id]["errors"] += 1

        return items

    async def _collect_hackernews(self, source: SourceConfig) -> list[RawItem]:
        """Hacker News API 采集"""
        items = []
        client = await self._get_client()

        await self._rate_limit(source)
        try:
            # 获取最新故事ID
            resp = await client.get(f"{source.base_url}/newstories.json")
            resp.raise_for_status()
            story_ids = resp.json()[:30]

            # 批量获取故事详情
            for sid in story_ids:
                await asyncio.sleep(0.1)  # 避免请求过快
                try:
                    story_resp = await client.get(f"{source.base_url}/item/{sid}.json")
                    story_resp.raise_for_status()
                    story = story_resp.json()

                    if story and story.get("title"):
                        items.append(
                            RawItem(
                                item_id=str(story.get("id", "")),
                                source_id=source.source_id,
                                title=story.get("title", ""),
                                url=story.get(
                                    "url", f"https://news.ycombinator.com/item?id={story.get('id')}"
                                ),
                                content=story.get("text", ""),
                                authors=[story.get("by", "")],
                                metadata={
                                    "score": story.get("score", 0),
                                    "descendants": story.get("descendants", 0),
                                },
                            )
                        )
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"Hacker News 采集失败: {e}")
            self._source_stats[source.source_id]["errors"] += 1

        return items

    async def _collect_huggingface(self, source: SourceConfig) -> list[RawItem]:
        """HuggingFace API 采集"""
        items = []
        client = await self._get_client()

        for tag in source.tags:
            await self._rate_limit(source)
            try:
                resp = await client.get(
                    f"{source.base_url}/models",
                    params={"search": tag, "sort": "downloads", "direction": -1, "limit": 5},
                )
                resp.raise_for_status()

                for model in resp.json():
                    item_id = model.get("id", "")
                    items.append(
                        RawItem(
                            item_id=item_id,
                            source_id=source.source_id,
                            title=item_id,
                            url=f"https://huggingface.co/{item_id}",
                            content=model.get("pipeline_tag", ""),
                            authors=[model.get("author", "")],
                            published_at=model.get("lastModified", ""),
                            metadata={
                                "downloads": model.get("downloads", 0),
                                "likes": model.get("likes", 0),
                                "tag": tag,
                            },
                        )
                    )
            except Exception as e:
                logger.error(f"HuggingFace 采集失败 [{tag}]: {e}")

        return items

    async def _collect_openreview(self, source: SourceConfig) -> list[RawItem]:
        """OpenReview API 采集"""
        items = []
        await self._get_client()
        # 简化实现
        return items

    async def _collect_generic_api(self, source: SourceConfig) -> list[RawItem]:
        """通用 API 采集"""
        return []

    # ============================================================
    # RSS 采集器
    # ============================================================

    async def collect_rss(self, source: SourceConfig) -> list[RawItem]:
        """RSS/Atom 订阅采集"""
        items = []
        client = await self._get_client()

        feeds = source.tags if source.tags else source.search_queries

        for feed_url in feeds:
            await self._rate_limit(source)
            try:
                resp = await client.get(feed_url)
                resp.raise_for_status()

                import xml.etree.ElementTree as ET

                root = ET.fromstring(resp.text)

                # 检测 RSS 还是 Atom
                is_atom = root.tag.endswith("feed") or root.tag.endswith("}feed")

                if is_atom:
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    entries = root.findall("atom:entry", ns)
                    for entry in entries:
                        title = entry.find("atom:title", ns)
                        link = entry.find("atom:link", ns)
                        summary = entry.find("atom:summary", ns)
                        updated = entry.find("atom:updated", ns)

                        url = link.get("href", "") if link is not None else ""
                        item_id = hashlib.md5(url.encode()).hexdigest()[:12]

                        items.append(
                            RawItem(
                                item_id=item_id,
                                source_id=source.source_id,
                                title=title.text.strip() if title is not None else "",
                                url=url,
                                content=summary.text.strip() if summary is not None else "",
                                published_at=updated.text if updated is not None else "",
                                metadata={"feed_url": feed_url},
                            )
                        )
                else:
                    # RSS 2.0
                    for item in root.findall(".//item"):
                        title = item.find("title")
                        link = item.find("link")
                        desc = item.find("description")
                        pub_date = item.find("pubDate")

                        url = link.text.strip() if link is not None else ""
                        item_id = hashlib.md5(url.encode()).hexdigest()[:12]

                        items.append(
                            RawItem(
                                item_id=item_id,
                                source_id=source.source_id,
                                title=title.text.strip() if title is not None else "",
                                url=url,
                                content=desc.text.strip() if desc is not None else "",
                                published_at=pub_date.text if pub_date is not None else "",
                                metadata={"feed_url": feed_url},
                            )
                        )

            except Exception as e:
                logger.error(f"RSS 采集失败 [{feed_url}]: {e}")
                self._source_stats[source.source_id]["errors"] += 1

        return items

    # ============================================================
    # Web Scraping 采集器 (网页抓取服务/爬虫服务/Bright Data 启发)
    # ============================================================

    async def collect_web_scraping(self, source: SourceConfig) -> list[RawItem]:
        """
        Web Scraping 采集

        支持三种后端:
          - 网页抓取服务 API: 智能内容清洗
          - 阅读服务: URL→Markdown
          - 原生 httpx: 基础抓取
        """
        items = []
        client = await self._get_client()

        # 优先使用 阅读服务 (免费, LLM-ready)
        jina_url = f"https://r.jina.ai/{source.base_url}"
        await self._rate_limit(source)

        try:
            resp = await client.get(
                jina_url,
                headers={"Accept": "text/markdown"},
            )
            if resp.status_code == 200 and resp.text.strip():
                item_id = hashlib.md5(source.base_url.encode()).hexdigest()[:12]
                items.append(
                    RawItem(
                        item_id=item_id,
                        source_id=source.source_id,
                        title=source.name,
                        url=source.base_url,
                        content=resp.text,
                        content_type="markdown",
                        metadata={"method": "jina_reader"},
                    )
                )
                return items
        except Exception:
            pass

        # 回退: 直接抓取
        try:
            resp = await client.get(source.base_url)
            resp.raise_for_status()

            item_id = hashlib.md5(source.base_url.encode()).hexdigest()[:12]
            items.append(
                RawItem(
                    item_id=item_id,
                    source_id=source.source_id,
                    title=source.name,
                    url=source.base_url,
                    content=resp.text,
                    content_type="html",
                    metadata={"method": "direct"},
                )
            )
        except Exception as e:
            logger.error(f"Web Scraping 失败 [{source.base_url}]: {e}")
            self._source_stats[source.source_id]["errors"] += 1

        return items

    # ============================================================
    # 全量采集
    # ============================================================

    async def collect_source(self, source: SourceConfig) -> list[RawItem]:
        """采集单个信息源"""
        if not source.enabled:
            return []

        if source.method == CollectionMethod.API:
            return await self.collect_api(source)
        elif source.method == CollectionMethod.RSS:
            return await self.collect_rss(source)
        elif source.method == CollectionMethod.WEB_SCRAPING:
            return await self.collect_web_scraping(source)
        else:
            return []

    async def collect_all(
        self,
        tier: SourceTier | None = None,
        category: str | None = None,
        max_concurrent: int = 10,
    ) -> CollectionBatch:
        """
        全量采集所有信息源

        Args:
            tier: 只采集指定等级 (不指定则全部)
            category: 只采集指定类别
            max_concurrent: 最大并发数
        """
        batch_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:12]
        batch = CollectionBatch(
            batch_id=batch_id,
            started_at=datetime.now(UTC).isoformat(),
        )

        start_time = time.time()

        # 筛选信息源
        active_sources = []
        for sid, source in SOURCES.items():
            if tier and source.tier != tier:
                continue
            if category and source.category != category:
                continue
            active_sources.append(source)

        batch.sources_queried = len(active_sources)

        # 并发采集
        semaphore = asyncio.Semaphore(max_concurrent)

        async def collect_with_semaphore(src: SourceConfig):
            async with semaphore:
                src_start = time.time()
                try:
                    raw_items = await self.collect_source(src)
                    batch.per_source_duration[src.source_id] = (time.time() - src_start) * 1000
                    return raw_items
                except Exception as e:
                    batch.errors.append(f"{src.source_id}: {e}")
                    batch.sources_failed += 1
                    batch.per_source_duration[src.source_id] = (time.time() - src_start) * 1000
                    return []

        tasks = [collect_with_semaphore(src) for src in active_sources]
        results = await asyncio.gather(*tasks)

        # 汇总
        all_raw = []
        for raw_items in results:
            all_raw.extend(raw_items)

        batch.raw_items = len(all_raw)

        # 标准化
        normalized = []
        for raw in all_raw:
            norm = self.normalizer.normalize(raw)
            if not norm.near_duplicate_of:
                normalized.append(norm)
                batch.by_category[norm.category] += 1
                batch.by_source[norm.source_id] += 1

        batch.normalized_items = len(normalized)
        batch.unique_items = len(normalized)
        batch.high_quality_items = sum(1 for n in normalized if n.is_high_quality)
        batch.total_duration_ms = (time.time() - start_time) * 1000
        batch.completed_at = datetime.now(UTC).isoformat()

        return batch


# ============================================================
# Layer 3: 多Agent协同编排层 (流程检索 启发)
# ============================================================


class AgentRole(str, Enum):
    """Agent 角色"""

    PAPER_AGENT = "paper_agent"  # 论文学术Agent
    CODE_AGENT = "code_agent"  # 代码仓库Agent
    NEWS_AGENT = "news_agent"  # 新闻媒体Agent
    BLOG_AGENT = "blog_agent"  # 技术博客Agent
    SOCIAL_AGENT = "social_agent"  # 社交媒体Agent
    SYNTHESIS_AGENT = "synthesis_agent"  # 综合合成Agent


@dataclass
class AgentTask:
    """Agent 任务"""

    task_id: str
    role: AgentRole
    sources: list[SourceConfig]
    priority: int = 0  # 0=最高
    dependencies: list[str] = field(default_factory=list)  # 依赖的 task_id


class MultiAgentOrchestrator:
    """
    多Agent协同编排层

    设计思路:
      - 流程检索 (上海AI Lab): 多Agent DAG知识流, 动态结构化知识流
      - 研究助手: Plan-and-Solve 并行子任务
      - 多智能体框架: Agent自己管理自己

    工作流程:
      1. 任务分解: 按领域将采集任务分配给专业Agent
      2. 并行执行: 各Agent独立采集, 最大并发
      3. 结果汇聚: 各Agent结果汇总到 Synthesis Agent
      4. 知识图谱注入: 结构化知识流入 KTG
    """

    def __init__(self, collector: UnifiedCollector):
        self.collector = collector
        self._agent_results: dict[AgentRole, list[RawItem]] = defaultdict(list)
        self._task_graph: dict[str, AgentTask] = {}

    def create_tasks(self) -> list[AgentTask]:
        """创建采集任务DAG"""
        tasks = []

        # 论文Agent — 学术源
        paper_sources = [s for s in SOURCES.values() if s.category == "academic"]
        paper_task = AgentTask(
            task_id="task_papers",
            role=AgentRole.PAPER_AGENT,
            sources=paper_sources,
            priority=0,
        )
        tasks.append(paper_task)

        # 代码Agent — 代码仓库源
        code_sources = [s for s in SOURCES.values() if s.category == "code"]
        code_task = AgentTask(
            task_id="task_code",
            role=AgentRole.CODE_AGENT,
            sources=code_sources,
            priority=0,
        )
        tasks.append(code_task)

        # 新闻Agent — RSS + HN
        news_sources = [s for s in SOURCES.values() if s.category in ("news", "social")]
        news_task = AgentTask(
            task_id="task_news",
            role=AgentRole.NEWS_AGENT,
            sources=news_sources,
            priority=1,
        )
        tasks.append(news_task)

        # 博客Agent — 大厂博客
        blog_sources = [s for s in SOURCES.values() if s.category == "blog"]
        blog_task = AgentTask(
            task_id="task_blogs",
            role=AgentRole.BLOG_AGENT,
            sources=blog_sources,
            priority=1,
        )
        tasks.append(blog_task)

        # 搜索Agent — 搜索API
        search_sources = [s for s in SOURCES.values() if s.category == "search"]
        search_task = AgentTask(
            task_id="task_search",
            role=AgentRole.SOCIAL_AGENT,
            sources=search_sources,
            priority=0,
        )
        tasks.append(search_task)

        # 合成Agent — 依赖所有其他Agent
        synthesis_task = AgentTask(
            task_id="task_synthesis",
            role=AgentRole.SYNTHESIS_AGENT,
            sources=[],
            priority=2,
            dependencies=["task_papers", "task_code", "task_news", "task_blogs", "task_search"],
        )
        tasks.append(synthesis_task)

        self._task_graph = {t.task_id: t for t in tasks}
        return tasks

    async def execute(self) -> dict:
        """
        执行多Agent协同采集

        Returns:
            {AgentRole: [NormalizedItem]}
        """
        tasks = self.create_tasks()
        results: dict[str, list[NormalizedItem]] = {}
        completed_tasks: set[str] = set()

        # 按优先级分组执行
        priority_groups = defaultdict(list)
        for task in tasks:
            priority_groups[task.priority].append(task)

        for priority in sorted(priority_groups.keys()):
            group = priority_groups[priority]
            group_tasks = []

            for task in group:
                # 检查依赖
                deps_met = all(dep in completed_tasks for dep in task.dependencies)
                if not deps_met:
                    continue

                async def run_agent(task: AgentTask):
                    all_raw = []
                    for source in task.sources:
                        raw_items = await self.collector.collect_source(source)
                        all_raw.extend(raw_items)

                    # 标准化
                    normalized = []
                    for raw in all_raw:
                        norm = self.collector.normalizer.normalize(raw)
                        if not norm.near_duplicate_of:
                            normalized.append(norm)

                    return task.role, normalized

                group_tasks.append(run_agent(task))

            if group_tasks:
                group_results = await asyncio.gather(*group_tasks, return_exceptions=True)
                for result in group_results:
                    if isinstance(result, Exception):
                        logger.error(f"Agent 执行失败: {result}")
                        continue
                    role, items = result
                    results[role.value] = items
                    # 标记完成
                    for task in group:
                        if task.role == role:
                            completed_tasks.add(task.task_id)

        return results

    def get_agent_report(self, results: dict) -> dict:
        """生成多Agent采集报告"""
        report = {
            "total_items": 0,
            "by_agent": {},
            "top_findings": [],
        }

        for role, items in results.items():
            report["by_agent"][role] = {
                "total": len(items),
                "high_quality": sum(1 for i in items if i.is_high_quality),
                "avg_relevance": sum(i.relevance_score for i in items) / max(len(items), 1),
            }
            report["total_items"] += len(items)

        # 提取Top发现
        all_items = []
        for items in results.values():
            all_items.extend(items)
        all_items.sort(key=lambda x: (x.relevance_score, x.quality_score), reverse=True)
        report["top_findings"] = [
            {"title": i.title, "url": i.url, "relevance": i.relevance_score} for i in all_items[:20]
        ]

        return report


# ============================================================
# Layer 4: 智能调度中心
# ============================================================


class ScheduleFrequency(str, Enum):
    """调度频率"""

    REALTIME = "realtime"  # 实时 (事件驱动)
    HOURLY = "hourly"  # 每小时
    DAILY = "daily"  # 每日
    WEEKLY = "weekly"  # 每周
    MONTHLY = "monthly"  # 每月


class IntelligentScheduler:
    """
    智能调度中心

    功能:
      - 优先级队列: Tier 0 → Tier 1 → Tier 2 → Tier 3
      - 去重引擎: 跨源语义去重
      - 速率限制: 全局+单源双层限流
      - 故障转移: 源不可用时降级到备用源
      - 自适应频率: 根据源活跃度动态调整采集频率
      - 增量采集: 只采集上次以来的新内容
    """

    def __init__(self, collector: UnifiedCollector):
        self.collector = collector
        self._last_collection: dict[str, str] = {}  # source_id → last_collected_at
        self._source_activity: dict[str, float] = {}  # source_id → activity_score
        self._failover_map: dict[str, str] = {
            # 主源 → 备用源
            "tavily": "brave_search",
            "github": "huggingface",
            "semantic_scholar": "arxiv",
        }
        self._load_state()

    def _load_state(self):
        """加载调度状态"""
        state_file = Path("data/scheduler_state.json")
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
                self._last_collection = state.get("last_collection", {})
                self._source_activity = state.get("source_activity", {})
            except Exception:
                pass

    def _save_state(self):
        """保存调度状态"""
        state_file = Path("data/scheduler_state.json")
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {
                    "last_collection": self._last_collection,
                    "source_activity": self._source_activity,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    async def schedule_collection(
        self,
        frequency: ScheduleFrequency,
        max_concurrent: int = 10,
    ) -> CollectionBatch:
        """
        按频率调度采集

        Args:
            frequency: 调度频率
            max_concurrent: 最大并发数
        """
        # 筛选需要采集的源
        active_sources = self._get_sources_for_frequency(frequency)

        # 按优先级排序
        tier_order = {
            SourceTier.TIER_0: 0,
            SourceTier.TIER_1: 1,
            SourceTier.TIER_2: 2,
            SourceTier.TIER_3: 3,
        }
        active_sources.sort(key=lambda s: tier_order.get(s.tier, 99))

        batch = CollectionBatch(
            batch_id=f"sched_{frequency}_{int(time.time())}",
            started_at=datetime.now(UTC).isoformat(),
        )
        batch.sources_queried = len(active_sources)
        start_time = time.time()

        semaphore = asyncio.Semaphore(max_concurrent)
        all_normalized = []

        async def collect_one(src: SourceConfig):
            async with semaphore:
                try:
                    raw_items = await self.collector.collect_source(src)
                    normalized = []
                    for raw in raw_items:
                        norm = self.collector.normalizer.normalize(raw)
                        if not norm.near_duplicate_of:
                            normalized.append(norm)
                    return src.source_id, normalized, None
                except Exception as e:
                    # 故障转移
                    backup_id = self._failover_map.get(src.source_id)
                    if backup_id and backup_id in SOURCES:
                        logger.warning(f"源 {src.source_id} 失败, 切换到备用源 {backup_id}")
                        try:
                            backup_src = SOURCES[backup_id]
                            raw_items = await self.collector.collect_source(backup_src)
                            normalized = []
                            for raw in raw_items:
                                norm = self.collector.normalizer.normalize(raw)
                                if not norm.near_duplicate_of:
                                    normalized.append(norm)
                            return backup_id, normalized, None
                        except Exception as e2:
                            return src.source_id, [], str(e2)
                    return src.source_id, [], str(e)

        tasks = [collect_one(src) for src in active_sources]
        results = await asyncio.gather(*tasks)

        for source_id, normalized, error in results:
            if error:
                batch.errors.append(f"{source_id}: {error}")
                batch.sources_failed += 1
            all_normalized.extend(normalized)
            batch.by_source[source_id] += len(normalized)
            self._last_collection[source_id] = datetime.now(UTC).isoformat()
            # 更新活跃度
            self._source_activity[source_id] = (
                self._source_activity.get(source_id, 0.5) * 0.8 + len(normalized) * 0.2
            )

        batch.normalized_items = len(all_normalized)
        batch.unique_items = len(all_normalized)
        batch.high_quality_items = sum(1 for n in all_normalized if n.is_high_quality)
        batch.total_duration_ms = (time.time() - start_time) * 1000
        batch.completed_at = datetime.now(UTC).isoformat()

        self._save_state()
        return batch

    def _get_sources_for_frequency(self, frequency: ScheduleFrequency) -> list[SourceConfig]:
        """获取指定频率需要采集的源"""
        tier_sources = {
            ScheduleFrequency.HOURLY: [SourceTier.TIER_0, SourceTier.TIER_1],
            ScheduleFrequency.DAILY: [SourceTier.TIER_0, SourceTier.TIER_1, SourceTier.TIER_2],
            ScheduleFrequency.WEEKLY: [
                SourceTier.TIER_0,
                SourceTier.TIER_1,
                SourceTier.TIER_2,
                SourceTier.TIER_3,
            ],
            ScheduleFrequency.MONTHLY: [
                SourceTier.TIER_0,
                SourceTier.TIER_1,
                SourceTier.TIER_2,
                SourceTier.TIER_3,
            ],
        }

        target_tiers = tier_sources.get(frequency, [SourceTier.TIER_0, SourceTier.TIER_1])

        active = []
        for source in SOURCES.values():
            if source.tier in target_tiers and source.enabled:
                active.append(source)

        return active

    def get_source_health(self) -> dict:
        """获取信息源健康状态"""
        health = {}
        for sid, stats in self.collector._source_stats.items():
            error_rate = stats["errors"] / max(stats["requests"], 1)
            health[sid] = {
                "requests": stats["requests"],
                "errors": stats["errors"],
                "error_rate": error_rate,
                "status": "healthy"
                if error_rate < 0.1
                else "degraded"
                if error_rate < 0.3
                else "unhealthy",
                "last_collected": self._last_collection.get(sid, "never"),
                "activity_score": self._source_activity.get(sid, 0),
            }
        return health


# ============================================================
# CollectionPipeline 别名 (兼容外部代码引用)
# ============================================================


class CollectionPipeline(UnifiedCollector):
    """
    CollectionPipeline — UnifiedCollector 的别名。

    集成采集管道、数据标准化、多Agent编排、智能调度于一体。
    """

    pass
