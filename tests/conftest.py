"""
Shared fixtures for unit and API tests.

Environment variables are set before any `src.*` import so Settings picks up
test configuration instead of the local `.env`.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable
from uuid import uuid4


@asynccontextmanager
async def _noop_lifespan(_app):
    yield

# Must run before importing application modules.
os.environ["APP_ENV"] = "test"
os.environ["DEBUG"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-ci-cd-not-for-production"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "7"
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ridedelivery_test",
)
os.environ["DATABASE_URL_SYNC"] = os.getenv(
    "TEST_DATABASE_URL_SYNC",
    "postgresql://postgres:postgres@localhost:5432/ridedelivery_test",
)
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/1"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/2"
os.environ["MPESA_CONSUMER_KEY"] = ""
os.environ["MPESA_CONSUMER_SECRET"] = ""
os.environ["MPESA_PASSKEY"] = "test-passkey"
os.environ["MPESA_SHORTCODE"] = "174379"
os.environ["MPESA_ENV"] = "sandbox"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from src.database import Base, get_db
from src.main import app
from src.models import (  # noqa: F401 — register metadata
    AssignmentConfig,
    Billing,
    FavoriteRider,
    Notification,
    PricingConfig,
    Rating,
    Request,
    RequestAssignment,
    SystemLog,
    Transaction,
    User,
    UserLocation,
    UserProfile,
    UserRoleMap,
)
from src.models.enums import UserRole
from src.schemas.user import UserCreate
from src.services.auth_service import AuthService

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest_asyncio.fixture(scope="session")
async def engine():
    # NullPool avoids checked-out connections surviving across await boundaries.
    eng = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Per-test session. Commits are real within the test DB; tables are truncated
    after each test so cases stay isolated without nested-transaction tricks.
    """
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with session_factory() as session:
        yield session
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    # httpx ASGITransport has no lifespan= kwarg in 0.28.x; tables are created
    # by the engine fixture, so skip the app lifespan (avoids a second init_db).
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def register_user(db_session: AsyncSession) -> Callable:
    async def _register(
        *,
        email: str | None = None,
        phone: str | None = None,
        password: str = "SecurePass123!",
        role: UserRole = UserRole.customer,
        first_name: str = "Test",
        last_name: str = "User",
    ) -> User:
        suffix = uuid4().hex[:8]
        payload = UserCreate(
            email=email or f"user_{suffix}@example.com",
            phone=phone or f"+2547{suffix[:8]}",
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role,
        )
        user = await AuthService.register_user(payload, db_session)
        await db_session.commit()
        return user

    return _register


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, register_user) -> Callable:
    async def _headers(
        *,
        role: UserRole = UserRole.customer,
        email: str | None = None,
        password: str = "SecurePass123!",
    ) -> dict[str, str]:
        user = await register_user(email=email, password=password, role=role)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": password},
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _headers
