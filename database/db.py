from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool, QueuePool
from contextlib import asynccontextmanager
import os

# SQLite DB path
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./mydatabase.db"
)

# Determine if using SQLite or PostgreSQL
is_sqlite = 'sqlite' in DATABASE_URL

# Configure engine based on database type
if is_sqlite:
    # SQLite doesn't support connection pooling well
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,  # Set to True for SQL debugging
        future=True,
        poolclass=NullPool,
        connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL with connection pooling
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        future=True,
        pool_size=20,  # Number of connections to maintain
        max_overflow=40,  # Additional connections if pool is full
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,  # Recycle connections after 1 hour
        poolclass=QueuePool
    )

# Async session
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Base model
Base = declarative_base()

# Initialize tables
@asynccontextmanager
async def get_db():
    """Async context manager for database sessions"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Function to initialize the database
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Graceful shutdown
async def close_db():
    """Close database connections gracefully"""
    await engine.dispose()