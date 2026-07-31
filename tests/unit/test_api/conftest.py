"""
API 路由单元测试公共夹具。

为 auth/documents/tasks 路由构建独立的 FastAPI 应用,
不依赖 AgentScheduler(这些路由只使用 services.storage)。
"""

import os
import sys

# 确保 src 在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fnixagent.api.routers import auth, documents, tasks
from fnixagent.services.storage import reset_stores


@pytest.fixture
def app():
    """构建只含 auth/documents/tasks 路由的 FastAPI 应用。"""
    application = FastAPI()
    application.include_router(auth.router, prefix="/api/v1")
    application.include_router(documents.router, prefix="/api/v1")
    application.include_router(tasks.router, prefix="/api/v1")
    return application


@pytest.fixture
def client(app):
    """TestClient,每个测试自动重置存储。"""
    reset_stores()
    with TestClient(app) as c:
        yield c
    reset_stores()


@pytest.fixture
def auth_token(client):
    """注册一个用户并返回其 JWT Token。"""
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "tester",
            "email": "tester@example.com",
            "password": "secret123",
            "role": "user",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "tester", "password": "secret123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    """带 Bearer Token 的请求头。"""
    return {"Authorization": f"Bearer {auth_token}"}
