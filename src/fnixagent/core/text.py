"""
文本处理算法库。

包含分词、分块(chunking)、n-gram、token 估算等纯算法,
服务于记忆分块、BM25 检索、prompt 预算控制等模块。
不依赖任何第三方 NLP 库,保证内核独立。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable

# ---------------------------------------------------------------------------
# 中英文混合分词
# ---------------------------------------------------------------------------

# 连续英文/数字作为一词, 单个中日韩字符各为一词
_CJK_RANGES = [
    (0x4E00, 0x9FFF),  # CJK 统一汉字
    (0x3400, 0x4DBF),  # CJK 扩展A
    (0x3000, 0x303F),  # CJK 符号与标点
    (0x3040, 0x309F),  # 平假名
    (0x30A0, 0x30FF),  # 片假名
    (0xFF00, 0xFFEF),  # 全角字符
]

# 预编译正则: 性能优化, 避免每次调用时重新编译
# 句末标点(中英文)+ 换行, 用于 split_sentences
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？；;\n])\s*")


def _is_cjk(ch: str) -> bool:
    """判断字符是否属于 CJK(中日韩)字符集。"""
    cp = ord(ch)
    for lo, hi in _CJK_RANGES:
        if lo <= cp <= hi:
            return True
    return False


def tokenize(text: str) -> list[str]:
    """轻量中英文分词。

    分词规则(中英文混合):
        - 英文/数字: 连续 alnum 片段作为一个 token(如 "GPT-4" → "gpt4" 因 '-' 非 alnum 会被切)
        - 中文: 每个字符作为一个 token (unigram, 适合 BM25)
        - 标点/空白: 忽略
        - 全部 token 小写化(便于去重与匹配)

    Args:
        text: 输入文本(可为中英文混合)

    Returns:
        小写化的 token 列表; 输入为空返回空列表

    Raises:
        TypeError: text 不是 str
    """
    # 输入校验: 必须为字符串
    if not isinstance(text, str):
        raise TypeError(f"text 必须为 str, 收到 {type(text).__name__}")
    if not text:
        return []
    tokens: list[str] = []
    buf: list[str] = []  # 缓冲连续的英文/数字字符
    for ch in text:
        if ch.isalnum() and not _is_cjk(ch):
            # 英文/数字字符: 累积到缓冲区
            buf.append(ch)
        else:
            # 遇到非英文/数字字符: 先把缓冲区的英文 token 落盘
            if buf:
                tokens.append("".join(buf).lower())
                buf = []
            # CJK 字符单独成 token(且必须是 alnum, 排除 CJK 标点)
            if _is_cjk(ch) and ch.isalnum():
                tokens.append(ch.lower())
    # 收尾: 处理缓冲区剩余字符
    if buf:
        tokens.append("".join(buf).lower())
    return tokens


def split_sentences(text: str) -> list[str]:
    """按句末标点(中英文)切句。保留非空结果。

    使用预编译正则, 避免每次调用重新编译(性能优化)。
    """
    if not text:
        return []
    # 使用预编译正则切分(lookbehind 不消费标点)
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# 文本分块 (chunking) —— 记忆入库核心
# ---------------------------------------------------------------------------


def chunk_by_chars(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """
    按字符数滑动窗口分块。
    overlap 必须小于 chunk_size, 否则降级为 0。
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须为正")
    if overlap < 0:
        overlap = 0
    if overlap >= chunk_size:
        overlap = 0
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    step = chunk_size - overlap
    i = 0
    while i < len(text):
        chunks.append(text[i : i + chunk_size])
        if i + chunk_size >= len(text):
            break
        i += step
    return chunks


def _is_mostly_ascii(s: str) -> bool:
    """判断字符串是否以 ASCII 字符为主(>50%)。

    用于决定分块拼接分隔符: ASCII 为主用空格, 否则直接拼接(中文无需空格)。
    """
    if not s:
        return True
    ascii_cnt = sum(1 for c in s if ord(c) < 128)
    return ascii_cnt > len(s) * 0.5


def _join_sentences(sentences: list[str]) -> str:
    """根据内容主语言选择分隔符拼接句子。

    ASCII 为主 → 用空格分隔(英文习惯); 否则直接拼接(中文习惯)。
    提取为函数避免在 chunk_by_sentences 中重复 join 调用(性能优化)。
    """
    joined = " ".join(sentences)
    if _is_mostly_ascii(joined):
        return joined
    return "".join(sentences)


def chunk_by_sentences(text: str, max_chars: int = 512, overlap_sentences: int = 1) -> list[str]:
    """按句子分块, 累积到接近 max_chars 时切分, 保留 overlap 句做衔接。

    Args:
        text:             输入文本
        max_chars:        单块最大字符数
        overlap_sentences: 块间重叠句数(用于上下文衔接)

    Returns:
        分块列表
    """
    sentences = split_sentences(text)
    if not sentences:
        return []
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for sent in sentences:
        sent_len = len(sent)
        # 累积超过上限 → 落盘当前块, 保留尾部 overlap 句做衔接
        if cur_len + sent_len > max_chars and cur:
            chunks.append(_join_sentences(cur))
            # 保留尾部 overlap 句, 实现块间衔接
            cur = cur[-overlap_sentences:] if overlap_sentences > 0 else []
            cur_len = sum(len(s) for s in cur)
        cur.append(sent)
        cur_len += sent_len
    # 收尾: 落盘最后一块
    if cur:
        chunks.append(_join_sentences(cur))
    return chunks


# ---------------------------------------------------------------------------
# n-gram (用于 BM25 / 关键词扩展)
# ---------------------------------------------------------------------------


def ngrams(tokens: Iterable[str], n: int) -> list[tuple[str, ...]]:
    """生成 n-gram。"""
    if n <= 0:
        return []
    toks = list(tokens)
    if len(toks) < n:
        return []
    return [tuple(toks[i : i + n]) for i in range(len(toks) - n + 1)]


def char_ngrams(text: str, n: int = 3) -> list[str]:
    """字符级 n-gram, 用于模糊匹配/中文检索。"""
    if n <= 0 or len(text) < n:
        return [text] if text else []
    return [text[i : i + n] for i in range(len(text) - n + 1)]


# ---------------------------------------------------------------------------
# Token 计数估算
# ---------------------------------------------------------------------------

# 经验比例: 中英文混合文本约 2.5 字符 ≈ 1 token (粗估, 用于预算控制)
_TOKEN_RATIO_CN = 1.8  # 中文约 1.8 字符/token
_TOKEN_RATIO_EN = 4.0  # 英文约 4 字符/token


def estimate_tokens(text: str) -> int:
    """
    估算 token 数(无 tokenizer 时的近似)。
    中文按字符 / 1.8, 英文按词 * 1.3。
    用于 prompt 预算裁剪, 精确计数由 LLM 层用真实 tokenizer 回填。
    """
    if not text:
        return 0
    cn_chars = sum(1 for c in text if _is_cjk(c))
    ascii_chars = sum(1 for c in text if c.isascii() and not c.isspace())
    cn_tokens = cn_chars / _TOKEN_RATIO_CN
    en_tokens = ascii_chars / _TOKEN_RATIO_EN
    return max(1, int(cn_tokens + en_tokens + 0.5))


def estimate_message_tokens(messages: Iterable) -> int:
    """估算消息列表总 token, 每条消息额外计 4 token 开销。"""
    total = 0
    for m in messages:
        # 兼容 dict 或 Message 对象
        content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
        total += estimate_tokens(str(content)) + 4
    return total


# ---------------------------------------------------------------------------
# 文本清洗
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def normalize_text(text: str) -> str:
    """规范化: NFKC + 压缩空白 + 去控制字符。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _CTRL_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def truncate(text: str, max_chars: int, ellipsis: str = "...") -> str:
    """安全截断, 超长追加省略号。"""
    if len(text) <= max_chars:
        return text
    if max_chars <= len(ellipsis):
        return ellipsis[:max_chars]
    return text[: max_chars - len(ellipsis)] + ellipsis


# ---------------------------------------------------------------------------
# 词频统计
# ---------------------------------------------------------------------------


def term_frequencies(tokens: Iterable[str]) -> Counter:
    """词频统计。"""
    return Counter(tokens)


def jaccard_similarity(a: Iterable[str], b: Iterable[str]) -> float:
    """集合 Jaccard 相似度, 用于去重。"""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)
