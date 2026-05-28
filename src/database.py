from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from src.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    # Import all models so SQLAlchemy knows about them
    from src.models import (  # noqa: F401
        User, UserRoleMap, UserProfile, UserLocation, FavoriteRider,
        Request, RequestAssignment,
        Billing, Transaction,
        PricingConfig, Rating, Notification, SystemLog,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
