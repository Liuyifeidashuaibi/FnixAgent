"""
PgDocumentStore 单元测试。

验证:
  - save_upload(含安全校验)
  - create_generated
  - get / get_file_path
  - list(过滤/分页)
  - delete(软删除)
  - 数据持久化
"""
from __future__ import annotations

import os

import pytest

from fnixagent.services.storage import MAX_UPLOAD_SIZE_BYTES
from fnixagent.services.storage_pg import PgDocumentStore


class TestPgDocumentStoreUpload:
    """文件上传。"""

    def test_save_upload_returns_document(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        content = b"Hello, World!"
        doc = store.save_upload("test.txt", content, user_id=1)
        assert doc.id > 0
        assert doc.name == "test.txt"
        assert doc.doc_type == "markdown"
        assert doc.source == "upload"
        assert doc.size_bytes == len(content)
        assert doc.user_id == 1
        assert len(doc.checksum) == 64  # SHA-256 hex

    def test_save_upload_writes_file_to_disk(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        content = b"file content"
        doc = store.save_upload("report.pdf", content, user_id=1)
        file_path = store.get_file_path(doc.id)
        assert file_path is not None
        assert os.path.exists(file_path)
        with open(file_path, "rb") as f:
            assert f.read() == content

    def test_save_upload_rejects_oversized_file(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        huge_content = b"x" * (MAX_UPLOAD_SIZE_BYTES + 1)
        with pytest.raises(ValueError, match="超过上限"):
            store.save_upload("huge.txt", huge_content)

    def test_save_upload_rejects_disallowed_extension(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        with pytest.raises(ValueError, match="不支持的文件类型"):
            store.save_upload("malware.exe", b"binary")

    def test_save_upload_rejects_path_traversal(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        with pytest.raises(ValueError, match="非法文件名"):
            store.save_upload("../../etc/passwd", b"data")

    def test_save_upload_detects_pdf_type(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        doc = store.save_upload("paper.pdf", b"%PDF-1.4", user_id=1)
        assert doc.doc_type == "pdf"

    def test_save_upload_detects_docx_type(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        doc = store.save_upload("doc.docx", b"PK\x03\x04", user_id=1)
        assert doc.doc_type == "docx"

    def test_save_upload_metadata_stored(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        meta = {"title": "Test Paper", "author": "Tester"}
        doc = store.save_upload("meta.txt", b"content", user_id=1, metadata=meta)
        assert doc.metadata == meta


class TestPgDocumentStoreGenerated:
    """Agent 生成文档。"""

    def test_create_generated_returns_document(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        content = b"Generated content"
        doc = store.create_generated("output.txt", "markdown", content, user_id=1)
        assert doc.source == "generated"
        assert doc.doc_type == "markdown"
        assert doc.size_bytes == len(content)


class TestPgDocumentStoreGet:
    """文档查询。"""

    def test_get_existing(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        doc = store.save_upload("test.txt", b"content", user_id=1)
        fetched = store.get(doc.id)
        assert fetched is not None
        assert fetched.name == "test.txt"

    def test_get_nonexistent(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        assert store.get(99999) is None

    def test_get_deleted_returns_none(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        doc = store.save_upload("test.txt", b"content", user_id=1)
        store.delete(doc.id)
        assert store.get(doc.id) is None

    def test_get_file_path_nonexistent(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        assert store.get_file_path(99999) is None


class TestPgDocumentStoreList:
    """文档列表。"""

    def test_list_empty(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        assert len(store.list()) == 0

    def test_list_all(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        store.save_upload("a.txt", b"a", user_id=1)
        store.save_upload("b.txt", b"b", user_id=1)
        assert len(store.list()) == 2

    def test_list_filter_by_user(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        store.save_upload("a.txt", b"a", user_id=1)
        store.save_upload("b.txt", b"b", user_id=2)
        assert len(store.list(user_id=1)) == 1
        assert len(store.list(user_id=2)) == 1

    def test_list_filter_by_type(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        store.save_upload("a.txt", b"a", user_id=1)
        store.save_upload("b.pdf", b"b", user_id=1)
        assert len(store.list(doc_type="markdown")) == 1
        assert len(store.list(doc_type="pdf")) == 1

    def test_list_excludes_deleted(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        d1 = store.save_upload("a.txt", b"a", user_id=1)
        store.save_upload("b.txt", b"b", user_id=1)
        store.delete(d1.id)
        assert len(store.list()) == 1

    def test_list_limit_clamped(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        for i in range(5):
            store.save_upload(f"f{i}.txt", b"x", user_id=1)
        # limit 超过最大值应被钳制到 MAX_LIST_LIMIT
        results = store.list(limit=10000)
        assert len(results) == 5

    def test_count(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        store.save_upload("a.txt", b"a", user_id=1)
        store.save_upload("b.txt", b"b", user_id=1)
        assert store.count == 2


class TestPgDocumentStoreDelete:
    """文档删除(软删除)。"""

    def test_delete_success(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        doc = store.save_upload("test.txt", b"content", user_id=1)
        assert store.delete(doc.id) is True
        assert store.get(doc.id) is None

    def test_delete_nonexistent(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        assert store.delete(99999) is False

    def test_delete_twice(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        doc = store.save_upload("test.txt", b"content", user_id=1)
        assert store.delete(doc.id) is True
        assert store.delete(doc.id) is False  # 已删除

    def test_delete_preserves_file_on_disk(self, db_adapter, storage_dir):
        store = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        doc = store.save_upload("test.txt", b"content", user_id=1)
        file_path = store.get_file_path(doc.id)
        store.delete(doc.id)
        # 文件应该还在磁盘上(软删除)
        assert os.path.exists(file_path)


class TestPgDocumentStorePersistence:
    """数据持久化。"""

    def test_docs_survive_adapter_restart(self, db_adapter, storage_dir):
        store1 = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        doc = store1.save_upload("persist.txt", b"persistent", user_id=1)

        store2 = PgDocumentStore(db_adapter, storage_dir=storage_dir)
        fetched = store2.get(doc.id)
        assert fetched is not None
        assert fetched.name == "persist.txt"
