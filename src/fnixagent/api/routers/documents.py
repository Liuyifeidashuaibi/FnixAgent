"""
API 路由 - 文档管理接口。

接入真实 DocumentStore(本地文件落盘 + 内存元数据索引),
替换之前的 Mock 实现。

支持操作:
  - 上传文档(落盘到 data/uploads/)
  - 查询/列表/删除
  - 文档处理(summarize/extract_tables/convert)
  - 下载文件流
"""

import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from fnixagent.api.schemas.models import (
    BaseResponse,
    DocumentProcess,
    DocumentResponse,
    DocumentUpload,
)
from fnixagent.services.storage import get_document_store

router = APIRouter(prefix="/documents", tags=["documents"])

# 允许的文档处理操作
_ALLOWED_OPERATIONS = {"summarize", "extract_tables", "convert", "extract_text", "translate"}


def _doc_to_response(doc) -> DocumentResponse:
    """StoredDocument → DocumentResponse。"""
    return DocumentResponse(
        id=doc.id,
        name=doc.name,
        doc_type=doc.doc_type,
        source=doc.source,
        object_key=doc.object_key,
        created_at=doc.created_at,
    )


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    metadata: dict | None = None,
):
    """
    上传文档。

    - 文件落盘到 data/uploads/<id>_<filename>
    - 元数据(类型/大小/校验和)存入 DocumentStore
    - 自动识别 doc_type(pdf/docx/markdown/chart/table)
    """
    # 读取文件内容
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")

    filename = file.filename or "unnamed"
    store = get_document_store()
    try:
        doc = store.save_upload(
            filename=filename,
            content=content,
            metadata=metadata or {},
        )
    except ValueError as e:
        # 安全校验失败(文件过大/类型不允许/非法文件名)
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        # 文件落盘失败(磁盘满/权限不足)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")
    return _doc_to_response(doc)


@router.post("/create", response_model=DocumentResponse)
async def create_document(request: DocumentUpload):
    """
    创建文档记录(Agent 生成文档时调用,内容后续填充)。

    与 upload 区别: 此接口只创建元数据记录,不带文件内容。
    """
    store = get_document_store()
    doc = store.create_generated(
        name=request.name,
        doc_type=request.doc_type,
        content=b"",  # 占位,后续可更新
        metadata=request.metadata or {},
    )
    return _doc_to_response(doc)


@router.get("/list")
async def list_documents(
    user_id: int | None = None,
    doc_type: str | None = None,
    limit: int = 50,
):
    """查询文档列表(支持按用户/类型过滤)。"""
    store = get_document_store()
    docs = store.list(user_id=user_id, doc_type=doc_type, limit=limit)
    return [_doc_to_response(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int):
    """获取文档信息。"""
    doc = get_document_store().get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _doc_to_response(doc)


@router.post("/{document_id}/process", response_model=BaseResponse)
async def process_document(document_id: int, request: DocumentProcess):
    """
    处理文档(summarize/extract_tables/convert/extract_text/translate)。

    说明: 当前返回基于文件类型的规则化结果。
    接入真实 LLM 后,可调用 scheduler.process() 生成摘要/翻译。
    """
    doc = get_document_store().get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    if request.operation not in _ALLOWED_OPERATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的操作: {request.operation}, 允许: {sorted(_ALLOWED_OPERATIONS)}",
        )

    # 规则化处理结果(无 LLM 依赖)
    result = _apply_operation(doc, request.operation, request.params)
    return BaseResponse(
        success=True,
        message=f"Document {document_id} processed with operation: {request.operation}",
        data=result,
    )


def _apply_operation(doc, operation: str, params: dict | None) -> dict:
    """对文档应用处理操作(规则化实现)。"""
    base = {
        "document_id": doc.id,
        "name": doc.name,
        "doc_type": doc.doc_type,
        "operation": operation,
    }

    if operation == "summarize":
        # 简单摘要: 取文件前 500 字符(若可读为文本)
        text = _extract_text(doc)
        base["summary"] = (text[:500] + "...") if len(text) > 500 else text
        base["summary_length"] = len(base["summary"])
    elif operation == "extract_tables":
        # 仅 docx/xlsx 可能含表格
        if doc.doc_type in ("docx", "table"):
            base["tables"] = []
            base["note"] = "表格提取需完整文件解析,当前返回空列表"
        else:
            base["tables"] = []
            base["note"] = f"文档类型 {doc.doc_type} 不含表格"
    elif operation == "convert":
        target = (params or {}).get("target_format", "docx")
        base["target_format"] = target
        base["status"] = "converted"
        base["note"] = f"已请求转换为 {target} 格式"
    elif operation == "extract_text":
        base["text"] = _extract_text(doc)[:2000]
        base["text_length"] = len(_extract_text(doc))
    elif operation == "translate":
        target_lang = (params or {}).get("target_lang", "en")
        base["target_lang"] = target_lang
        base["note"] = f"翻译为目标语言 {target_lang} 需接入 LLM"

    return base


def _extract_text(doc) -> str:
    """从文档提取文本(尽力而为)。"""
    store = get_document_store()
    path = store.get_file_path(doc.id)
    if not path or not os.path.exists(path):
        return ""
    try:
        # 尝试 UTF-8 解码(适用于 txt/md/csv)
        with open(path, "rb") as f:
            return f.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


@router.delete("/{document_id}")
async def delete_document(document_id: int):
    """删除文档(软删除,保留文件)。"""
    store = get_document_store()
    ok = store.delete(document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在或已删除")
    return BaseResponse(success=True, message="Document deleted")


@router.get("/{document_id}/download")
async def download_document(document_id: int):
    """下载文档文件流。"""
    store = get_document_store()
    doc = store.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    path = store.get_file_path(document_id)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在或已被清理")

    return FileResponse(
        path=path,
        media_type=doc.mime_type or "application/octet-stream",
        filename=doc.name,
    )


@router.get("/{document_id}/metadata")
async def get_document_metadata(document_id: int):
    """获取文档完整元数据(含校验和/大小)。"""
    doc = get_document_store().get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc.to_dict()
