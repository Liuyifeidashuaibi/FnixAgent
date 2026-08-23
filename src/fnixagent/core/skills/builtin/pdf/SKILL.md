---
name: pdf
description: PDF 文档处理 — 提取/合并/分割/标注/加密/OCR，对应 PDFExpert
version: 1.0.0
license: Apache-2.0
level: BASIC
output_format: pdf
tags:
  - pdf
  - office
  - work
  - extract
  - merge
resources:
  - office/pdf.py
  - office/converter.py
---

# PDF Skill

本机 PDF 处理技能，基于 `PDFExpert` (PyPDF2 / pdfplumber 可选依赖)。所有写盘产物落 `.fnix/artifacts/`，遵循 Work 模式「先交产物再写盘」契约。

## 何时使用

- 用户提到「PDF 提取文字 / 拆分 / 合并 / 加水印 / 加密 / 转 Word」
- 工作流需要从扫描件中做 OCR 提取
- 需要把多个 PDF 拼装成单一报告交付
- 需要给 PDF 加批注/水印/密码保护后归档

不要用于：纯文本生成（用 docx）、表格数据处理（用 xlsx）、PPT 制作（用 pptx）。

## 工作流程

1. **意图识别**：判断操作类型（提取 / 合并 / 分割 / 标注 / 加密 / OCR），从用户输入中收集 source path(s)、target name、操作参数。
2. **参数校验**：确认源文件存在且可读，目标路径在 `.fnix/artifacts/` 下；若涉及 OCR，确认 `paddleocr` 可用，否则降级到纯文本提取。
3. **执行**：调用 `PDFExpert.extract_text` / `merge` / `split` / `add_watermark` / `encrypt` / `ocr`。每一步返回 `ExpertResult`，含 `output_path` 与 `meta`。
4. **质量自检**：对产物做基础检查（页数、文件大小、可打开性），失败则进入「look → fix」闭环（最多 2 轮）。
5. **交付**：返回产物的绝对路径与摘要元数据；Work 模式下写入 `.fnix/artifacts/<name>.pdf` 并在对话中给出下载链接。

## 输出契约

- `output_format: pdf`
- 产物路径：`.fnix/artifacts/<task_slug>.pdf`（或用户指定名）
- 元数据：`{ "pages": int, "size_bytes": int, "encrypted": bool }`
- 失败时返回 `ExpertResult(success=False, error=<原因>)`，不写盘

## Fnix 集成点

- 底层实现：`fnixagent.office.pdf.PDFExpert`
- 工具注册：通过 `ToolRegistry` 暴露为 `pdf.extract` / `pdf.merge` / `pdf.split` / `pdf.watermark` / `pdf.encrypt` / `pdf.ocr`
- 写盘契约：Work 模式 → `.fnix/artifacts/`；Code 模式不直接写盘，由用户审阅 diff 后决定
- 模板：`office/template.py` 可加载 PDF 模板套用

## 示例

**用户**：把 `report_q1.pdf` 和 `report_q2.pdf` 合并成 `report_h1.pdf`，加「机密」水印。

**Skill 执行**：
1. 调用 `pdf.merge(sources=[...], output=".fnix/artifacts/report_h1.pdf")`
2. 调用 `pdf.watermark(source=<上一步产物>, text="机密", opacity=0.2)`
3. 返回 `{"output_path": ".fnix/artifacts/report_h1.pdf", "pages": 42, "size_bytes": 184320}`
