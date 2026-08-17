"""Phase 3.2 内容合规 + 数据本地化测试。

覆盖:
  A. ContentModerator 增强
    1. 5 大违规类别检测(自伤/暴力/色情/政治/诈骗)
    2. 输入侧审核(PII 拦截)
    3. 输出侧审核(PII 仅脱敏)
    4. 风险评分
    5. 审计日志写入
    6. 性能 < 100ms

  B. ModerationService
    7. 单例工厂
    8. 配置开关(总开关/输入/输出)
    9. 仅拦截高风险模式
    10. 统计计数

  C. 用户隐私中心 API
    11. GET /privacy/profile(脱敏手机号)
    12. GET /privacy/export(JSON 下载)
    13. POST /privacy/delete-account(软删除)
    14. POST /privacy/cancel-deletion(撤销)
    15. GET /privacy/deletion-status

  D. UserStore 软删除/硬删除
    16. soft_delete_user 标记 disabled + deleted_at
    17. cancel_soft_delete 恢复
    18. hard_delete_user 彻底删除
    19. get_users_to_hard_delete 按时间筛选
    20. is_user_deleted

  E. 审计日志自动脱敏
    21. detail 中手机号被脱敏
    22. detail 中嵌套结构被脱敏
    23. 哈希链仍可校验
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import time
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_stores():
    """每个测试前后重置存储,确保隔离。"""
    from fnixagent.core.security import rbac
    from fnixagent.services.moderation_service import reset_moderation_service
    from fnixagent.services.storage import reset_stores
    from fnixagent.services.storage_audit import reset_audit_store
    from fnixagent.services.storage_rbac import reset_rbac_store

    reset_audit_store()
    reset_stores()
    reset_rbac_store()
    reset_moderation_service()
    rbac.invalidate_all_permission_cache()
    yield
    reset_audit_store()
    reset_stores()
    reset_rbac_store()
    reset_moderation_service()
    rbac.invalidate_all_permission_cache()


# ===========================================================================
# A. ContentModerator 增强
# ===========================================================================


class TestContentModeratorCategories:
    """5 大违规类别检测。"""

    def test_self_harm_detected(self):
        from fnixagent.core.security.moderation import CATEGORY_SELF_HARM, ContentModerator

        m = ContentModerator()
        result = m.review("如何自杀才能不痛苦")
        assert not result.passed
        assert CATEGORY_SELF_HARM in result.categories

    def test_violence_detected(self):
        from fnixagent.core.security.moderation import CATEGORY_VIOLENCE, ContentModerator

        m = ContentModerator()
        result = m.review("炸弹制作教程第一步")
        assert not result.passed
        assert CATEGORY_VIOLENCE in result.categories

    def test_pornography_detected(self):
        from fnixagent.core.security.moderation import CATEGORY_PORNOGRAPHY, ContentModerator

        m = ContentModerator()
        result = m.review("这是色情内容")
        assert not result.passed
        assert CATEGORY_PORNOGRAPHY in result.categories

    def test_political_detected(self):
        from fnixagent.core.security.moderation import CATEGORY_POLITICAL, ContentModerator

        m = ContentModerator()
        result = m.review("煽动颠覆国家政权")
        assert not result.passed
        assert CATEGORY_POLITICAL in result.categories

    def test_fraud_detected(self):
        from fnixagent.core.security.moderation import CATEGORY_FRAUD, ContentModerator

        m = ContentModerator()
        result = m.review("传销内部资料")
        assert not result.passed
        assert CATEGORY_FRAUD in result.categories

    def test_clean_text_passes(self):
        from fnixagent.core.security.moderation import ContentModerator

        m = ContentModerator()
        result = m.review("今天天气真好,适合出门散步。")
        assert result.passed
        assert result.categories == []


class TestInputModeration:
    """输入侧审核(PII 也拦截)。"""

    def test_phone_in_input_blocked(self):
        from fnixagent.core.security.moderation import CATEGORY_PII, ContentModerator

        m = ContentModerator()
        result = m.review_input("我的手机号是 13800138000 请联系我")
        assert not result.passed
        assert CATEGORY_PII in result.categories

    def test_email_in_input_blocked(self):
        from fnixagent.core.security.moderation import CATEGORY_PII, ContentModerator

        m = ContentModerator()
        result = m.review_input("发邮件到 test@example.com")
        assert not result.passed
        assert CATEGORY_PII in result.categories

    def test_id_card_in_input_blocked(self):
        from fnixagent.core.security.moderation import CATEGORY_PII, ContentModerator

        m = ContentModerator()
        result = m.review_input("身份证号 110101199003073915")
        assert not result.passed
        assert CATEGORY_PII in result.categories

    def test_input_returns_sanitized_text(self):
        from fnixagent.core.security.moderation import ContentModerator

        m = ContentModerator()
        result = m.review_input("联系 13800138000")
        assert "13800138000" not in result.sanitized_text
        assert "138****8000" in result.sanitized_text


class TestOutputModeration:
    """输出侧审核(PII 仅脱敏,不拦截)。"""

    def test_phone_in_output_only_sanitized_not_blocked(self):
        from fnixagent.core.security.moderation import ContentModerator

        m = ContentModerator()
        result = m.review("用户电话是 13800138000")
        # 输出侧 PII 不拦截
        assert result.passed
        # 但要脱敏
        assert "13800138000" not in result.sanitized_text
        assert "138****8000" in result.sanitized_text

    def test_sensitive_word_in_output_blocked(self):
        from fnixagent.core.security.moderation import ContentModerator, SensitiveDetector

        det = SensitiveDetector()
        det.add_words(["敏感词1"])
        m = ContentModerator(sensitive_detector=det)
        result = m.review("这是敏感词1的内容")
        assert not result.passed

    def test_clean_output_passes_with_sanitization(self):
        from fnixagent.core.security.moderation import ContentModerator

        m = ContentModerator()
        result = m.review("这是一段正常的 LLM 输出。")
        assert result.passed
        assert result.sanitized_text == "这是一段正常的 LLM 输出。"


class TestRiskScore:
    """风险评分。"""

    def test_high_risk_category_scores_40(self):
        from fnixagent.core.security.moderation import ContentModerator

        m = ContentModerator()
        result = m.review("如何自杀")
        assert result.risk_score >= 40

    def test_mid_risk_category_scores_30(self):
        from fnixagent.core.security.moderation import ContentModerator

        m = ContentModerator()
        result = m.review("这是色情内容")
        assert result.risk_score >= 30

    def test_score_capped_at_100(self):
        from fnixagent.core.security.moderation import ContentModerator

        m = ContentModerator()
        result = m.review("自杀 炸弹制作 色情 煽动 传销 诈骗")
        assert result.risk_score == 100


class TestModerationAuditLog:
    """审核违规写入审计日志。"""

    def test_input_blocked_writes_audit(self):
        from fnixagent.core.security.moderation import ContentModerator
        from fnixagent.services.storage_audit import get_audit_store

        m = ContentModerator()
        m.review_input("如何自杀", user_id=42, ip_address="1.2.3.4")
        store = get_audit_store()
        logs, _ = store.query(action="moderation.input_blocked")
        assert len(logs) >= 1
        assert logs[0].user_id == 42
        assert logs[0].ip_address == "1.2.3.4"

    def test_output_blocked_writes_audit(self):
        from fnixagent.core.security.moderation import ContentModerator, SensitiveDetector
        from fnixagent.services.storage_audit import get_audit_store

        det = SensitiveDetector()
        det.add_words(["违禁词"])
        m = ContentModerator(sensitive_detector=det)
        m.review("这是违禁词的内容", user_id=99)
        store = get_audit_store()
        logs, _ = store.query(action="moderation.output_blocked")
        assert len(logs) >= 1
        assert logs[0].user_id == 99


class TestModerationPerformance:
    """性能:违规输入 100ms 内拦截。"""

    def test_input_review_under_100ms(self):
        from fnixagent.core.security.moderation import ContentModerator

        m = ContentModerator()
        # 加载默认敏感词
        m._sensitive.load_default_words()
        text = "这是一段测试文本,包含自杀等敏感内容。" * 10
        start = time.monotonic()
        result = m.review_input(text)
        duration = (time.monotonic() - start) * 1000
        assert duration < 100, f"审核耗时 {duration:.2f}ms 超过 100ms"
        assert not result.passed


# ===========================================================================
# B. ModerationService
# ===========================================================================


class TestModerationService:
    """审核服务单例 + 配置。"""

    def test_singleton_factory(self):
        from fnixagent.services.moderation_service import get_moderation_service

        s1 = get_moderation_service()
        s2 = get_moderation_service()
        assert s1 is s2

    def test_disable_input_passes_everything(self):
        from fnixagent.services.moderation_service import (
            get_moderation_service,
        )

        svc = get_moderation_service()
        svc.update_config(input_enabled=False)
        result = svc.moderate_input("如何自杀 13800138000")
        assert result.passed

    def test_disable_output_passes_everything(self):
        from fnixagent.services.moderation_service import get_moderation_service

        svc = get_moderation_service()
        svc.update_config(output_enabled=False)
        result = svc.moderate_output("色情内容")
        assert result.passed

    def test_total_disable_passes_everything(self):
        from fnixagent.services.moderation_service import get_moderation_service

        svc = get_moderation_service()
        svc.update_config(enabled=False)
        result = svc.moderate_input("自杀")
        assert result.passed

    def test_high_risk_only_mode(self):
        from fnixagent.services.moderation_service import get_moderation_service

        svc = get_moderation_service()
        svc.update_config(block_high_risk_only=True, high_risk_threshold=40)
        # PII 风险评分较低,不拦截
        r1 = svc.moderate_input("电话 13800138000")
        assert r1.passed
        # 自伤高风险,拦截
        r2 = svc.moderate_input("如何自杀")
        assert not r2.passed

    def test_stats_counts_blocked(self):
        from fnixagent.services.moderation_service import get_moderation_service

        svc = get_moderation_service()
        svc.moderate_input("如何自杀")
        svc.moderate_output("正常文本")
        svc.moderate_output("色情内容")
        stats = svc.get_stats()
        assert stats["total_input"] == 1
        assert stats["blocked_input"] == 1
        assert stats["total_output"] == 2
        assert stats["blocked_output"] == 1


# ===========================================================================
# C. 用户隐私中心 API
# ===========================================================================


def _create_app_with_privacy():
    """创建带 privacy 路由的测试 app。"""
    from fnixagent.api.routers import privacy

    app = FastAPI()
    app.include_router(privacy.router, prefix="/api/v1")
    return app


def _register_and_login(client, username="alice", password="Pass1234", phone="13800138000"):
    """注册用户并登录获取 token,返回 (token, user_id)。"""
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": password},
    )
    assert resp.status_code == 200, resp.text
    user_id = resp.json()["id"]

    # 设置手机号
    from fnixagent.services.storage import get_user_store

    get_user_store().update_profile(user_id, {"phone": phone})

    # 登录
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return token, user_id


class TestPrivacyAPI:
    """隐私中心 API 端点。"""

    def test_get_profile_masks_phone(self):
        from fnixagent.api.routers import auth, privacy

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(privacy.router, prefix="/api/v1")
        client = TestClient(app)

        token, _ = _register_and_login(client)
        resp = client.get(
            "/api/v1/privacy/profile",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["phone"] == "138****8000"  # 已脱敏
        assert data["username"] == "alice"

    def test_get_profile_unauthenticated_401(self):
        app = _create_app_with_privacy()
        client = TestClient(app)
        resp = client.get("/api/v1/privacy/profile")
        assert resp.status_code == 401

    def test_export_returns_json_attachment(self):
        from fnixagent.api.routers import auth, privacy

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(privacy.router, prefix="/api/v1")
        client = TestClient(app)

        token, _ = _register_and_login(client)
        resp = client.get(
            "/api/v1/privacy/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert resp.headers["content-type"] == "application/json"
        data = resp.json()
        assert "user" in data
        assert "api_keys" in data
        assert "documents" in data
        assert "tasks" in data
        assert "audit_logs" in data
        # 手机号已脱敏
        assert data["user"]["phone"] == "138****8000"

    def test_delete_account_soft_deletes(self):
        from fnixagent.api.routers import auth, privacy
        from fnixagent.services.storage import get_user_store

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(privacy.router, prefix="/api/v1")
        client = TestClient(app)

        token, user_id = _register_and_login(client)
        resp = client.post(
            "/api/v1/privacy/delete-account",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

        # 验证软删除标记
        store = get_user_store()
        user = store.get_by_id(user_id)
        assert user.profile.get("deleted_at") is not None
        assert user.profile.get("hard_delete_at") is not None
        assert user.profile.get("disabled") is True

    def test_delete_account_writes_audit(self):
        from fnixagent.api.routers import auth, privacy
        from fnixagent.services.storage_audit import get_audit_store

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(privacy.router, prefix="/api/v1")
        client = TestClient(app)

        token, _ = _register_and_login(client)
        client.post(
            "/api/v1/privacy/delete-account",
            headers={"Authorization": f"Bearer {token}"},
        )
        store = get_audit_store()
        logs, _ = store.query(action="account.delete_request")
        assert len(logs) >= 1

    def test_cancel_deletion_restores_account(self):
        from fnixagent.api.routers import auth, privacy
        from fnixagent.services.storage import get_user_store

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(privacy.router, prefix="/api/v1")
        client = TestClient(app)

        token, user_id = _register_and_login(client)
        # 先注销
        client.post(
            "/api/v1/privacy/delete-account",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 再撤销
        resp = client.post(
            "/api/v1/privacy/cancel-deletion",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

        store = get_user_store()
        user = store.get_by_id(user_id)
        assert user.profile.get("deleted_at") is None
        assert user.profile.get("hard_delete_at") is None
        assert user.profile.get("disabled") is False

    def test_cancel_deletion_without_request_400(self):
        from fnixagent.api.routers import auth, privacy

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(privacy.router, prefix="/api/v1")
        client = TestClient(app)

        token, _ = _register_and_login(client)
        resp = client.post(
            "/api/v1/privacy/cancel-deletion",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_delete_account_twice_400(self):
        from fnixagent.api.routers import auth, privacy

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(privacy.router, prefix="/api/v1")
        client = TestClient(app)

        token, _ = _register_and_login(client)
        # 第一次注销
        resp1 = client.post(
            "/api/v1/privacy/delete-account",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp1.status_code == 200
        # 第二次应返回 400
        resp2 = client.post(
            "/api/v1/privacy/delete-account",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 400

    def test_deletion_status_active(self):
        from fnixagent.api.routers import auth, privacy

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(privacy.router, prefix="/api/v1")
        client = TestClient(app)

        token, _ = _register_and_login(client)
        resp = client.get(
            "/api/v1/privacy/deletion-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "active"
        assert data["deleted_at"] is None

    def test_deletion_status_pending(self):
        from fnixagent.api.routers import auth, privacy

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(privacy.router, prefix="/api/v1")
        client = TestClient(app)

        token, _ = _register_and_login(client)
        client.post(
            "/api/v1/privacy/delete-account",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.get(
            "/api/v1/privacy/deletion-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "pending_deletion"
        assert data["deleted_at"] is not None
        assert data["remaining_days"] is not None
        assert data["remaining_days"] >= 29  # 应该接近 30 天


# ===========================================================================
# D. UserStore 软删除/硬删除
# ===========================================================================


class TestUserSoftDelete:
    """UserStore 软删除/硬删除。"""

    def test_soft_delete_marks_user(self):
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create("deluser1", "del1@example.com", "Pass1234")
        assert store.soft_delete_user(user.id, retention_days=30)
        user_after = store.get_by_id(user.id)
        assert user_after.profile.get("deleted_at") is not None
        assert user_after.profile.get("hard_delete_at") is not None
        assert user_after.profile.get("disabled") is True
        assert store.is_user_disabled(user.id)
        assert store.is_user_deleted(user.id)

    def test_cancel_soft_delete_restores(self):
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create("deluser2", "del2@example.com", "Pass1234")
        store.soft_delete_user(user.id)
        assert store.cancel_soft_delete(user.id)
        user_after = store.get_by_id(user.id)
        assert user_after.profile.get("deleted_at") is None
        assert user_after.profile.get("disabled") is False
        assert not store.is_user_deleted(user.id)

    def test_hard_delete_removes_user(self):
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create("deluser3", "del3@example.com", "Pass1234")
        assert store.hard_delete_user(user.id)
        assert store.get_by_id(user.id) is None
        # 索引也清除
        assert store.get_by_username("deluser3") is None
        assert store.get_by_email("del3@example.com") is None

    def test_get_users_to_hard_delete(self):
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        # 创建 3 个用户
        u1, _ = store.create("u1", "u1@e.com", "Pass1234")
        u2, _ = store.create("u2", "u2@e.com", "Pass1234")
        u3, _ = store.create("u3", "u3@e.com", "Pass1234")
        # u1 软删除保留 30 天(未到期)
        store.soft_delete_user(u1.id, retention_days=30)
        # u2 软删除保留 0 天(立即到期)
        store.soft_delete_user(u2.id, retention_days=0)
        # u3 不软删除
        # 当前时间查询:只有 u2 到期
        candidates = store.get_users_to_hard_delete()
        candidate_ids = [u.id for u in candidates]
        assert u2.id in candidate_ids
        assert u1.id not in candidate_ids
        assert u3.id not in candidate_ids

    def test_get_users_to_hard_delete_with_custom_before(self):
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        u1, _ = store.create("future1", "f1@e.com", "Pass1234")
        store.soft_delete_user(u1.id, retention_days=30)
        # 用未来时间查询,应包含
        future = datetime.utcnow() + timedelta(days=31)
        candidates = store.get_users_to_hard_delete(before=future)
        assert u1.id in [u.id for u in candidates]

    def test_soft_delete_nonexistent_returns_false(self):
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        assert not store.soft_delete_user(99999)
        assert not store.cancel_soft_delete(99999)
        assert not store.hard_delete_user(99999)

    def test_is_user_deleted_for_nonexistent_returns_true(self):
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        assert store.is_user_deleted(99999)


# ===========================================================================
# E. 审计日志自动脱敏
# ===========================================================================


class TestAuditLogDesensitization:
    """审计日志 detail 自动脱敏。"""

    def test_phone_in_detail_is_masked(self):
        from fnixagent.core.audit import AuditLogger
        from fnixagent.services.storage_audit import get_audit_store

        logger = AuditLogger()
        logger.log(
            action="test.action",
            user_id=1,
            detail={"text": "用户手机号 13800138000 已记录"},
        )
        store = get_audit_store()
        logs, _ = store.query(action="test.action")
        assert len(logs) >= 1
        detail = logs[0].detail
        # 手机号应被脱敏
        assert "13800138000" not in detail["text"]
        assert "138****8000" in detail["text"]

    def test_nested_dict_is_masked(self):
        from fnixagent.core.audit import AuditLogger
        from fnixagent.services.storage_audit import get_audit_store

        logger = AuditLogger()
        logger.log(
            action="test.nested",
            user_id=1,
            detail={
                "user": {"phone": "13800138000", "name": "alice"},
                "items": ["email test@example.com", "正常文本"],
            },
        )
        store = get_audit_store()
        logs, _ = store.query(action="test.nested")
        detail = logs[0].detail
        assert "13800138000" not in detail["user"]["phone"]
        assert "138****8000" in detail["user"]["phone"]
        assert "test@example.com" not in detail["items"][0]
        assert "t***@example.com" in detail["items"][0]
        # 非敏感文本不变
        assert detail["items"][1] == "正常文本"
        # 非字符串字段不变
        assert detail["user"]["name"] == "alice"

    def test_hash_chain_still_valid_after_desensitization(self):
        """脱敏后哈希链仍可校验(因为哈希基于脱敏后的内容计算)。"""
        from fnixagent.core.audit import AuditLogger, verify_hash_chain
        from fnixagent.services.storage_audit import get_audit_store

        logger = AuditLogger()
        logger.log(
            action="test.chain",
            user_id=1,
            detail={"phone": "13800138000"},
        )
        logger.log(
            action="test.chain2",
            user_id=1,
            detail={"phone": "13900139000"},
        )
        store = get_audit_store()
        logs, _ = store.query(limit=100)
        logs = list(reversed(logs))  # 按时间正序
        is_valid, broken_id = verify_hash_chain(logs)
        assert is_valid, f"哈希链断裂于 {broken_id}"

    def test_non_string_fields_preserved(self):
        """非字符串字段(int/bool/None)不被脱敏影响。"""
        from fnixagent.core.audit import AuditLogger
        from fnixagent.services.storage_audit import get_audit_store

        logger = AuditLogger()
        logger.log(
            action="test.types",
            user_id=1,
            detail={
                "count": 42,
                "enabled": True,
                "score": 3.14,
                "nullable": None,
                "phone": "13800138000",
            },
        )
        store = get_audit_store()
        logs, _ = store.query(action="test.types")
        detail = logs[0].detail
        assert detail["count"] == 42
        assert detail["enabled"] is True
        assert detail["score"] == 3.14
        assert detail["nullable"] is None
        assert "13800138000" not in detail["phone"]


# ===========================================================================
# F. 账号清理调度器
# ===========================================================================


class TestAccountCleanup:
    """账号清理调度器。"""

    def test_run_cleanup_hard_deletes_expired(self):
        from fnixagent.services.account_cleanup import _run_cleanup
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        # 创建到期用户
        u1, _ = store.create("expired1", "exp1@e.com", "Pass1234")
        store.soft_delete_user(u1.id, retention_days=0)
        # 创建未到期用户
        u2, _ = store.create("active1", "act1@e.com", "Pass1234")
        store.soft_delete_user(u2.id, retention_days=30)

        _run_cleanup()

        assert store.get_by_id(u1.id) is None  # 已硬删除
        assert store.get_by_id(u2.id) is not None  # 保留

    def test_run_cleanup_writes_audit(self):
        from fnixagent.services.account_cleanup import _run_cleanup
        from fnixagent.services.storage import get_user_store
        from fnixagent.services.storage_audit import get_audit_store

        store = get_user_store()
        u1, _ = store.create("expired2", "exp2@e.com", "Pass1234")
        store.soft_delete_user(u1.id, retention_days=0)

        _run_cleanup()

        audit_store = get_audit_store()
        logs, _ = audit_store.query(action="account.hard_deleted")
        assert len(logs) >= 1
        assert logs[0].user_id == u1.id

    def test_run_cleanup_no_candidates_noop(self):
        from fnixagent.services.account_cleanup import _run_cleanup
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        # 无候选
        _run_cleanup()
        # 不报错即可
