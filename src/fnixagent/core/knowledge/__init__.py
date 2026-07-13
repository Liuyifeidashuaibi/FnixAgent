"""Knowledge Pipeline(P2-5)。

文档处理管道:把原始文档(Word/Excel/PDF/图片/Markdown)处理为可检索的知识块。
6 步流水线:OCR → Parse → Chunk → Extract → Permission → Embed。

模块:
  - pipeline.py:PipelineContext / PipelineStep / KnowledgePipeline
  - steps.py:   6 个步骤实现(OCRStep/ParseStep/ChunkStep/ExtractStep/PermissionStep/EmbedStep)

用法:
    from fnixagent.core.knowledge import KnowledgePipeline, PipelineContext

    pipeline = KnowledgePipeline()
    ctx = PipelineContext(
        document_id="doc-001",
        tenant_id="tenant-001",
        file_path="/path/to/doc.docx",
        file_ext="docx",
    )
    ctx = pipeline.run(ctx)
    # ctx.chunks / ctx.embeddings / ctx.extracted_metadata 可用
"""
from fnixagent.core.knowledge.pipeline import (
    KnowledgePipeline,
    PipelineContext,
    PipelineStep,
)
from fnixagent.core.knowledge.steps import (
    ChunkStep,
    EmbedStep,
    ExtractStep,
    OCRStep,
    ParseStep,
    PermissionStep,
)

__all__ = [
    "KnowledgePipeline",
    "PipelineContext",
    "PipelineStep",
    # 6 个步骤
    "OCRStep",
    "ParseStep",
    "ChunkStep",
    "ExtractStep",
    "PermissionStep",
    "EmbedStep",
]
