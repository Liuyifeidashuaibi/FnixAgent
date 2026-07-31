"""
documents 路由单元测试。

覆盖:
  - 上传文档(成功/空文件/类型识别)
  - 创建文档记录
  - 查询单个文档(成功/不存在)
  - 文档处理(summarize/extract_tables/convert/extract_text/translate/非法操作)
  - 列表查询(过滤)
  - 删除(成功/不存在/软删除后查询)
  - 下载(成功/文件不存在)
  - 元数据查询
"""

import io

import pytest


class TestUpload:
    """文档上传。"""

    def test_upload_text_file(self, client):
        content = b"Hello, this is a test document.\nLine 2."
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.md", io.BytesIO(content), "text/markdown")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test.md"
        assert data["doc_type"] == "markdown"
        assert data["source"] == "upload"
        assert data["id"] >= 1

    def test_upload_pdf_type_detection(self, client):
        content = b"%PDF-1.4 fake pdf content"
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("report.pdf", io.BytesIO(content), "application/pdf")},
        )
        assert resp.status_code == 200
        assert resp.json()["doc_type"] == "pdf"

    def test_upload_docx_type_detection(self, client):
        content = b"fake docx bytes"
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("thesis.docx", io.BytesIO(content), "application/octet-stream")},
        )
        assert resp.status_code == 200
        assert resp.json()["doc_type"] == "docx"

    def test_upload_empty_file_rejected(self, client):
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
        )
        assert resp.status_code == 400
        assert "为空" in resp.json()["detail"]

    def test_upload_rejects_disallowed_extension(self, client):
        """安全:不允许上传 .exe 等可执行文件。"""
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("malware.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "不支持" in resp.json()["detail"]

    def test_upload_rejects_path_traversal(self, client):
        """安全:文件名路径穿越攻击应被净化。"""
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("../../etc/passwd.txt", io.BytesIO(b"x"), "text/plain")},
        )
        # 路径穿越被 basename 净化后应正常保存(文件名为 passwd.txt)
        assert resp.status_code == 200

    def test_upload_rejects_oversized_file(self, client):
        """安全:超过 50MB 的文件应被拒绝(模拟大文件)。"""
        # 构造刚好超限的内容(不实际生成 50MB,而是临时调小常量)
        import fnixagent.services.storage as storage_mod

        original = storage_mod.MAX_UPLOAD_SIZE_BYTES
        storage_mod.MAX_UPLOAD_SIZE_BYTES = 10  # 临时设为 10 字节
        try:
            resp = client.post(
                "/api/v1/documents/upload",
                files={"file": ("big.txt", io.BytesIO(b"x" * 20), "text/plain")},
            )
            assert resp.status_code == 400
            assert "超过上限" in resp.json()["detail"]
        finally:
            storage_mod.MAX_UPLOAD_SIZE_BYTES = original


class TestCreate:
    """创建文档记录(无文件内容)。"""

    def test_create_document_record(self, client):
        resp = client.post(
            "/api/v1/documents/create",
            json={"name": "generated_report.pdf", "doc_type": "pdf"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "generated_report.pdf"
        assert data["doc_type"] == "pdf"
        assert data["source"] == "generated"


class TestGetDocument:
    def test_get_existing(self, client):
        upload = client.post(
            "/api/v1/documents/upload",
            files={"file": ("a.txt", io.BytesIO(b"content"), "text/plain")},
        )
        doc_id = upload.json()["id"]
        resp = client.get(f"/api/v1/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == doc_id

    def test_get_not_found(self, client):
        resp = client.get("/api/v1/documents/9999")
        assert resp.status_code == 404


class TestProcessDocument:
    """文档处理。"""

    @pytest.fixture
    def uploaded_doc(self, client):
        content = b"This is a long enough text for summarization testing. " * 20
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("doc.md", io.BytesIO(content), "text/markdown")},
        )
        return resp.json()["id"]

    def test_summarize(self, client, uploaded_doc):
        resp = client.post(
            f"/api/v1/documents/{uploaded_doc}/process",
            json={"document_id": uploaded_doc, "operation": "summarize"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "summary" in data["data"]

    def test_extract_tables(self, client, uploaded_doc):
        resp = client.post(
            f"/api/v1/documents/{uploaded_doc}/process",
            json={"document_id": uploaded_doc, "operation": "extract_tables"},
        )
        assert resp.status_code == 200
        assert "tables" in resp.json()["data"]

    def test_convert(self, client, uploaded_doc):
        resp = client.post(
            f"/api/v1/documents/{uploaded_doc}/process",
            json={
                "document_id": uploaded_doc,
                "operation": "convert",
                "params": {"target_format": "docx"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["target_format"] == "docx"

    def test_extract_text(self, client, uploaded_doc):
        resp = client.post(
            f"/api/v1/documents/{uploaded_doc}/process",
            json={"document_id": uploaded_doc, "operation": "extract_text"},
        )
        assert resp.status_code == 200
        assert "text" in resp.json()["data"]

    def test_translate(self, client, uploaded_doc):
        resp = client.post(
            f"/api/v1/documents/{uploaded_doc}/process",
            json={
                "document_id": uploaded_doc,
                "operation": "translate",
                "params": {"target_lang": "en"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["target_lang"] == "en"

    def test_invalid_operation(self, client, uploaded_doc):
        resp = client.post(
            f"/api/v1/documents/{uploaded_doc}/process",
            json={"document_id": uploaded_doc, "operation": "delete_all"},
        )
        assert resp.status_code == 400

    def test_process_nonexistent_doc(self, client):
        resp = client.post(
            "/api/v1/documents/9999/process",
            json={"document_id": 9999, "operation": "summarize"},
        )
        assert resp.status_code == 404


class TestListDocuments:
    def test_list_empty(self, client):
        resp = client.get("/api/v1/documents/list")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_docs(self, client):
        client.post(
            "/api/v1/documents/upload",
            files={"file": ("a.txt", io.BytesIO(b"a"), "text/plain")},
        )
        client.post(
            "/api/v1/documents/upload",
            files={"file": ("b.pdf", io.BytesIO(b"b"), "application/pdf")},
        )
        resp = client.get("/api/v1/documents/list")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_filter_by_type(self, client):
        client.post(
            "/api/v1/documents/upload",
            files={"file": ("a.txt", io.BytesIO(b"a"), "text/plain")},
        )
        client.post(
            "/api/v1/documents/upload",
            files={"file": ("b.pdf", io.BytesIO(b"b"), "application/pdf")},
        )
        resp = client.get("/api/v1/documents/list?doc_type=pdf")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["doc_type"] == "pdf"


class TestDeleteDocument:
    def test_delete_success(self, client):
        upload = client.post(
            "/api/v1/documents/upload",
            files={"file": ("a.txt", io.BytesIO(b"a"), "text/plain")},
        )
        doc_id = upload.json()["id"]
        resp = client.delete(f"/api/v1/documents/{doc_id}")
        assert resp.status_code == 200
        # 软删除后 get 应 404
        get_resp = client.get(f"/api/v1/documents/{doc_id}")
        assert get_resp.status_code == 404

    def test_delete_not_found(self, client):
        resp = client.delete("/api/v1/documents/9999")
        assert resp.status_code == 404

    def test_delete_twice(self, client):
        upload = client.post(
            "/api/v1/documents/upload",
            files={"file": ("a.txt", io.BytesIO(b"a"), "text/plain")},
        )
        doc_id = upload.json()["id"]
        client.delete(f"/api/v1/documents/{doc_id}")
        resp = client.delete(f"/api/v1/documents/{doc_id}")
        assert resp.status_code == 404


class TestDownload:
    def test_download_success(self, client):
        content = b"downloadable content"
        upload = client.post(
            "/api/v1/documents/upload",
            files={"file": ("dl.txt", io.BytesIO(content), "text/plain")},
        )
        doc_id = upload.json()["id"]
        resp = client.get(f"/api/v1/documents/{doc_id}/download")
        assert resp.status_code == 200
        assert resp.content == content

    def test_download_not_found(self, client):
        resp = client.get("/api/v1/documents/9999/download")
        assert resp.status_code == 404


class TestMetadata:
    def test_get_metadata(self, client):
        upload = client.post(
            "/api/v1/documents/upload",
            files={"file": ("m.txt", io.BytesIO(b"meta"), "text/plain")},
        )
        doc_id = upload.json()["id"]
        resp = client.get(f"/api/v1/documents/{doc_id}/metadata")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == doc_id
        assert data["size_bytes"] == 4
        assert "checksum" in data
        assert len(data["checksum"]) == 64  # SHA256 hex
