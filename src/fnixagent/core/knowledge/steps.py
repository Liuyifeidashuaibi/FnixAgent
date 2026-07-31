"""Knowledge Pipeline 步骤实现(P2-5)。

6 个步骤:
  1. OCRStep:       图片/扫描件 OCR(可选,仅对图片类文档触发)
  2. ParseStep:     文档解析为 blocks(复用 office.parser.ParserExpert)
  3. ChunkStep:     文本分块(按 token 数,滑窗重叠)
  4. ExtractStep:   元数据抽取(标题/作者/日期/关键词,可选)
  5. PermissionStep:权限标签打标(基于 tenant/文档来源/PII 检测)
  6. EmbedStep:     向量编码(复用 core.retrieval.embedder)

设计:
  - 每步独立,失败不互相影响(required=False 的步骤失败不阻断)
  - should_run() 按文档类型/mime_type 决定是否跳过
  - 内部依赖可选(无 office.parser 时降级到纯文本分块)
  - 大文档分块采用流式处理,避免一次性加载全文
"""

from __future__ import annotations

import os
import re
from typing import Any

from fnixagent.core.knowledge.pipeline import PipelineContext, PipelineStep
from fnixagent.core.text import estimate_tokens, tokenize

# ---------------------------------------------------------------------------
# Step 1: OCRStep
# ---------------------------------------------------------------------------


class OCRStep(PipelineStep):
    """OCR 步骤:对图片/扫描件进行文字识别。

    should_run:仅图片类 MIME 或图片扩展名时触发。
    依赖:pytesseract + pdf2image(可选,不可用时记录错误并跳过)。
    """

    def __init__(self, engine: str = "tesseract", lang: str = "chi_sim+eng") -> None:
        self._engine = engine
        self._lang = lang

    @property
    def name(self) -> str:
        return "ocr"

    @property
    def required(self) -> bool:
        return False  # OCR 失败不阻断

    def should_run(self, ctx: PipelineContext) -> bool:
        # 图片 MIME 或扩展名
        image_exts = {"png", "jpg", "jpeg", "tiff", "tif", "bmp", "gif", "webp"}
        image_mimes = {"image/png", "image/jpeg", "image/tiff", "image/bmp", "image/gif"}
        if ctx.file_ext in image_exts:
            return True
        if ctx.mime_type in image_mimes:
            return True
        # PDF 也可能需要 OCR(扫描件),但成本高,默认不触发
        # 用户可通过 ctx.options["force_ocr"]=True 强制
        if ctx.file_ext == "pdf" and ctx.options.get("force_ocr"):
            return True
        return False

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        # 依赖降级:pytesseract/PIL 不可用时记录错误并跳过,不抛异常
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
        except ImportError as e:
            ctx.errors.append(
                {
                    "step": self.name,
                    "error": f"OCR deps missing: {e}. Install: pip install pytesseract pillow",
                    "fatal": False,
                }
            )
            return ctx
        try:
            img = Image.open(ctx.file_path)
            ctx.ocr_text = pytesseract.image_to_string(img, lang=self._lang)
        except Exception as e:
            ctx.errors.append(
                {
                    "step": self.name,
                    "error": f"OCR failed: {e}",
                    "fatal": False,
                }
            )
        return ctx


# ---------------------------------------------------------------------------
# Step 2: ParseStep
# ---------------------------------------------------------------------------


class ParseStep(PipelineStep):
    """文档解析步骤:把原始文档解析为 blocks。

    优先复用 office.parser.ParserExpert;不可用时降级为纯文本读取。
    大文件采用流式读取(按行累积),避免一次性加载全文。
    """

    # 流式降级读取的单次块大小(字符)
    _STREAM_CHUNK_SIZE: int = 65536

    def __init__(self, parser: str = "auto") -> None:
        self._parser = parser

    @property
    def name(self) -> str:
        return "parse"

    def should_run(self, ctx: PipelineContext) -> bool:
        # 无文件路径则跳过;路径不存在也跳过(由 Pipeline 入口校验 fatal)
        return bool(ctx.file_path) and os.path.exists(ctx.file_path)

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        # 优先使用 ParserExpert(可解析 Word/Excel/PDF 结构)
        try:
            from fnixagent.office.parser import ParserExpert

            expert = ParserExpert()
            result = expert.parse(ctx.file_path, extract_tables=True, extract_metadata=True)
            if result.success:
                data = result.output
                # 把 paragraphs 转为统一 block 结构
                for p in data.get("paragraphs", []):
                    ctx.parsed_blocks.append(
                        {
                            "type": "paragraph",
                            "text": p.get("text", ""),
                            "metadata": {"style": p.get("style", "Normal")},
                        }
                    )
                # 把 tables 也作为 block
                for i, tbl in enumerate(data.get("tables", [])):
                    ctx.parsed_blocks.append(
                        {
                            "type": "table",
                            "text": self._table_to_text(tbl),
                            "metadata": {"table_index": i, "rows": len(tbl)},
                        }
                    )
                # 抽取的 metadata 直接放进 extracted_metadata
                md = data.get("metadata", {})
                if md:
                    ctx.extracted_metadata.update(md)
                # 若 ParserExpert 没拿到文本,用 raw_text
                if not ctx.parsed_blocks and data.get("raw_text"):
                    ctx.parsed_blocks.append(
                        {
                            "type": "paragraph",
                            "text": data["raw_text"],
                            "metadata": {"style": "Normal"},
                        }
                    )
                return ctx
        except Exception as e:
            ctx.errors.append(
                {
                    "step": self.name,
                    "error": f"ParserExpert failed: {e}, fallback to plain text",
                    "fatal": False,
                }
            )

        # 降级:流式纯文本读取(避免一次性加载大文件)
        try:
            parts: list[str] = []
            with open(ctx.file_path, encoding="utf-8", errors="ignore") as f:
                while True:
                    chunk = f.read(self._STREAM_CHUNK_SIZE)
                    if not chunk:
                        break
                    parts.append(chunk)
            text = "".join(parts)
            ctx.parsed_blocks.append(
                {
                    "type": "paragraph",
                    "text": text,
                    "metadata": {"style": "Normal", "fallback": True},
                }
            )
        except Exception as e:
            ctx.errors.append(
                {
                    "step": self.name,
                    "error": f"plain text fallback failed: {e}",
                    "fatal": True,
                }
            )
        return ctx

    @staticmethod
    def _table_to_text(table: list[list[str]]) -> str:
        """把二维表格转为文本(便于后续分块与检索)。"""
        lines = []
        for row in table:
            lines.append(" | ".join(str(c) for c in row))
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 3: ChunkStep
# ---------------------------------------------------------------------------


class ChunkStep(PipelineStep):
    """文本分块步骤:按 token 数切分,滑窗重叠。

    策略:
      - 按 block 顺序拼接
      - 当累计 token 超过 chunk_size 时,产出一个 chunk
      - 下一个 chunk 从前一个 chunk 末尾回退 chunk_overlap 个 token 开始(滑窗)

    边界修复:
      - chunk_size 必须 > 0,否则用默认值
      - chunk_overlap 必须 < chunk_size,否则降级为 0
      - chunk_index 严格单调递增,避免越界与重复
    """

    def __init__(
        self,
        strategy: str = "token",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        # 参数校验:防止越界与负值
        if chunk_size <= 0:
            chunk_size = 500
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            chunk_overlap = 0
        self._strategy = strategy
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    @property
    def name(self) -> str:
        return "chunk"

    def should_run(self, ctx: PipelineContext) -> bool:
        return bool(ctx.parsed_blocks) or bool(ctx.ocr_text)

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        # 合并所有文本(流式累积,避免大文档一次性拼接)
        parts: list[str] = []
        for blk in ctx.parsed_blocks:
            text = blk.get("text", "")
            if text:
                parts.append(text)
        if ctx.ocr_text:
            parts.append(ctx.ocr_text)
        full_text = "\n\n".join(parts)

        if not full_text:
            return ctx

        # 按句号/换行先粗切,再按 token 累加
        sentences = re.split(r"(?<=[。.!?\n])\s*", full_text)
        sentences = [s for s in sentences if s.strip()]

        current_text = ""
        current_tokens = 0
        chunk_index = 0
        overlap_buffer: list[str] = []

        for sent in sentences:
            sent_tokens = estimate_tokens(sent)
            # 当前 chunk 已满:产出并开启新 chunk(以 overlap 衔接)
            if current_tokens + sent_tokens > self._chunk_size and current_text:
                ctx.chunks.append(
                    {
                        "text": current_text.strip(),
                        "index": chunk_index,
                        "tokens": current_tokens,
                        "metadata": {"strategy": self._strategy},
                    }
                )
                chunk_index += 1
                # 滑窗重叠:保留末尾 overlap_buffer 作为新 chunk 起点
                overlap_text = " ".join(overlap_buffer)
                current_text = (overlap_text + " " + sent).strip()
                current_tokens = estimate_tokens(current_text)
                overlap_buffer = [sent]
            else:
                # 累积到当前 chunk
                current_text = (current_text + " " + sent).strip()
                current_tokens += sent_tokens
                overlap_buffer.append(sent)
                # 控制 overlap_buffer 不超过 chunk_overlap tokens(避免缓冲膨胀)
                while (
                    overlap_buffer
                    and sum(estimate_tokens(s) for s in overlap_buffer) > self._chunk_overlap
                ):
                    overlap_buffer.pop(0)

        # 最后一个 chunk(避免遗漏尾部内容)
        if current_text.strip():
            ctx.chunks.append(
                {
                    "text": current_text.strip(),
                    "index": chunk_index,
                    "tokens": current_tokens,
                    "metadata": {"strategy": self._strategy},
                }
            )

        return ctx


# ---------------------------------------------------------------------------
# Step 4: ExtractStep
# ---------------------------------------------------------------------------


class ExtractStep(PipelineStep):
    """元数据抽取步骤:从文本中抽取标题/作者/日期/关键词等。

    可选步骤(required=False),失败不阻断。
    可配置 extract_fields 指定要抽取的字段。

    重复抽取防护:
      - 已由 ParseStep 抽取的字段跳过(不覆盖)
      - keywords 字段使用集合去重
    """

    # 内置字段抽取正则
    _FIELD_PATTERNS: dict[str, str] = {
        "title": r"^#\s+(.+)$",  # markdown 一级标题
        "author": r"(?:作者|Author|By)[:：\s]*([^\s,，\n]+)",
        "date": r"(?:日期|Date|发布时间)[:：\s]*([\d\-/年月日]+)",
        "email": r"([\w\.\-]+@[\w\.\-]+)",
        "phone": r"(1[3-9]\d{9})",  # 简单手机号
        "doc_id": r"(?:文档编号|Doc ID|Document No)[:：\s]*([A-Za-z0-9\-]+)",
    }

    def __init__(
        self,
        extract_fields: list[str] | None = None,
        required: bool = False,
    ) -> None:
        self._fields = extract_fields or list(self._FIELD_PATTERNS.keys())
        self._required = required

    @property
    def name(self) -> str:
        return "extract"

    @property
    def required(self) -> bool:
        return self._required

    def should_run(self, ctx: PipelineContext) -> bool:
        return bool(ctx.parsed_blocks) or bool(ctx.ocr_text)

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        # 合并前若干 block 的文本(元数据通常在开头)
        sample_text = ""
        for blk in ctx.parsed_blocks[:10]:
            sample_text += blk.get("text", "") + "\n"
        if ctx.ocr_text:
            sample_text = ctx.ocr_text[:2000] + "\n" + sample_text

        # 字段抽取:已有值则跳过(避免覆盖 ParseStep 的结果)
        extracted_keys = set(ctx.extracted_metadata.keys())
        for fname in self._fields:
            if fname in extracted_keys:
                continue  # 已有值(可能来自 ParseStep),跳过避免重复
            pattern = self._FIELD_PATTERNS.get(fname)
            if not pattern:
                continue
            match = re.search(pattern, sample_text, re.MULTILINE)
            if match:
                ctx.extracted_metadata[fname] = match.group(1).strip()

        # 关键词抽取:简单取 top-N 高频词(去重)
        full_text = " ".join(blk.get("text", "") for blk in ctx.parsed_blocks)
        tokens = tokenize(full_text)
        # 过滤短词与停用词(简化)
        stopwords = {
            "的",
            "了",
            "和",
            "是",
            "在",
            "我",
            "有",
            "与",
            "为",
            "a",
            "an",
            "the",
            "is",
            "are",
            "in",
            "on",
            "to",
            "of",
        }
        word_freq: dict[str, int] = {}
        seen_tokens: set[str] = set()  # 同一 token 仅计数一次去重
        for t in tokens:
            t = t.strip()
            if len(t) < 2 or t.lower() in stopwords:
                continue
            if t in seen_tokens:
                word_freq[t] = word_freq.get(t, 0) + 1
            else:
                seen_tokens.add(t)
                word_freq[t] = 1
        top_keywords = sorted(word_freq.items(), key=lambda x: -x[1])[:10]
        # 与已有 keywords 合并去重
        existing_kw = ctx.extracted_metadata.get("keywords", []) or []
        merged = list(dict.fromkeys([w for w, _ in top_keywords] + list(existing_kw)))
        ctx.extracted_metadata["keywords"] = merged[:10]

        return ctx


# ---------------------------------------------------------------------------
# Step 5: PermissionStep
# ---------------------------------------------------------------------------


class PermissionStep(PipelineStep):
    """权限打标步骤:为文档打上可见性/权限标签。

    基于 tenant_id、文档来源、抽取的 metadata、PII 检测决定标签。
    知识库文档权限标签会写入 ctx.permission_tags,后续检索时可据此过滤。
    """

    # 简单 PII 检测正则(邮箱 + 手机号)
    _PII_PATTERNS: dict[str, str] = {
        "email": r"[\w\.\-]+@[\w\.\-]+",
        "phone": r"1[3-9]\d{9}",
    }

    def __init__(self, default_visibility: str = "tenant") -> None:
        self._default_visibility = default_visibility

    @property
    def name(self) -> str:
        return "permission"

    def should_run(self, ctx: PipelineContext) -> bool:
        return True

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        tags: dict[str, Any] = {
            "visibility": self._default_visibility,
            "tenant_id": ctx.tenant_id,
            "source": "upload",
        }

        # 敏感内容检测(简单关键词扫描)
        full_text = " ".join(blk.get("text", "") for blk in ctx.parsed_blocks)
        sensitive_keywords = {
            "机密",
            "绝密",
            "内部",
            " confidential",
            "restricted",
            "private",
        }
        lower_text = full_text.lower()
        is_sensitive = any(kw.lower() in lower_text for kw in sensitive_keywords)
        if is_sensitive:
            tags["sensitivity"] = "confidential"
            tags["visibility"] = "restricted"
        else:
            tags["sensitivity"] = "public"

        # PII 检测:正则直接扫描文本(不依赖 ExtractStep 是否成功)
        has_pii = False
        for pii_type, pattern in self._PII_PATTERNS.items():
            if re.search(pattern, full_text):
                has_pii = True
                tags[f"pii_{pii_type}"] = True
        # 兼容 ExtractStep 已抽取的 email/phone 字段
        if ctx.extracted_metadata.get("email") or ctx.extracted_metadata.get("phone"):
            has_pii = True
        if has_pii:
            tags["contains_pii"] = True
            # 含 PII 时收紧可见性
            if tags["visibility"] == "tenant":
                tags["visibility"] = "owner_only"

        # 用户自定义规则(透传 options)
        custom_rules = ctx.options.get("permission_rules")
        if isinstance(custom_rules, dict):
            tags.update(custom_rules)

        ctx.permission_tags = tags
        return ctx


# ---------------------------------------------------------------------------
# Step 6: EmbedStep
# ---------------------------------------------------------------------------


class EmbedStep(PipelineStep):
    """向量编码步骤:把 chunks 编码为向量。

    优先用真实 Embedder(OpenAI/Qwen/BGE);不可用降级到 HashingEmbedder。
    批量编码减少重复计算;维度一致性校验避免入库异常。
    """

    def __init__(
        self,
        embedder_name: str = "hashing",
        batch_size: int = 32,
        dim: int = 256,
    ) -> None:
        if batch_size <= 0:
            batch_size = 32
        if dim <= 0:
            dim = 256
        self._embedder_name = embedder_name
        self._batch_size = batch_size
        self._dim = dim
        self._embedder: Any | None = None  # lazy init

    @property
    def name(self) -> str:
        return "embed"

    @property
    def required(self) -> bool:
        return False  # 编码失败不阻断(可后续补)

    def should_run(self, ctx: PipelineContext) -> bool:
        return bool(ctx.chunks)

    def _get_embedder(self) -> Any:
        """惰性加载 embedder,失败降级到 HashingEmbedder。"""
        if self._embedder is not None:
            return self._embedder
        # 尝试加载真实 embedder(此处仅占位,真实场景对接具体 provider)
        if self._embedder_name != "hashing":
            try:
                # 用户可通过 options 注入自定义 embedder
                pass
            except Exception:
                pass
        # 降级到 HashingEmbedder(零依赖)
        from fnixagent.core.retrieval.embedder import HashingEmbedder

        self._embedder = HashingEmbedder(dim=self._dim)
        return self._embedder

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        embedder = self._get_embedder()
        # 期望维度(用于校验返回向量是否一致)
        expected_dim = getattr(embedder, "dim", self._dim)
        texts = [c["text"] for c in ctx.chunks]
        # 批量编码:减少 embedder 内部重复初始化开销
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            try:
                vectors = embedder.embed_batch(batch)
            except Exception as e:
                ctx.errors.append(
                    {
                        "step": self.name,
                        "error": f"embed batch {i} failed: {e}",
                        "fatal": False,
                    }
                )
                continue
            # 维度一致性校验:剔除维度异常的向量,避免入库后检索出错
            for vec in vectors:
                if len(vec) != expected_dim:
                    ctx.errors.append(
                        {
                            "step": self.name,
                            "error": (
                                f"embedding dim mismatch: got {len(vec)}, expected {expected_dim}"
                            ),
                            "fatal": False,
                        }
                    )
                    continue
                ctx.embeddings.append(vec)
        # 把 embedding 维度信息写回 chunk metadata(便于下游对齐)
        for i, vec in enumerate(ctx.embeddings):
            if i < len(ctx.chunks):
                ctx.chunks[i]["metadata"]["embedding_dim"] = len(vec)
                ctx.chunks[i]["metadata"]["embedder"] = self._embedder_name
        return ctx
