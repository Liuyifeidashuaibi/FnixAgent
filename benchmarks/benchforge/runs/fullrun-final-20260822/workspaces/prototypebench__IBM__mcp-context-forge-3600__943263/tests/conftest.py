import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request object"""
    from fastapi import Request
    
    class MockReceive:
        def __init__(self):
            self.called = False
        
        async def __call__(self):
            if not self.called:
                self.called = True
                return {"type": "http.request", "body": b""}
            return {"type": "http.disconnect"}
    
    request = Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
        },
        receive=MockReceive(),
        send=AsyncMock()
    )
    return request


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession"""
    from sqlalchemy.ext.asyncio import AsyncSession
    
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Create a mock session factory"""
    return AsyncMock(return_value=mock_session)
