import os
# Mock required settings variables for test environment execution before imports
os.environ.setdefault("JWT_SECRET", "fb8bde564ee1c9b31d2ba51082c3f81e370a256e297121b6d91cd68b75249cf4")

import asyncio
import pytest
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.db.database import Base, get_db
from app.main import app

# Test database URL (SQLite in-memory for testing isolation)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create async engine for test database
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

# Async session factory for tests
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


@pytest.fixture(autouse=True)
async def setup_test_db():
    """Create database tables and clean up after the test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional test database session."""
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture(autouse=True)
async def override_get_db(db_session: AsyncSession):
    """Override main get_db dependency with test database session."""
    async def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)
