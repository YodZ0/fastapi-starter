from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_async_engine(
    url: URL | str,
    *,
    echo: bool = False,
    echo_pool: bool = False,
    pool_size: int = 10,
    max_overflow: int = 5,
    pool_timeout: float = 30.0,
    pool_recycle: int = 1800,
    pool_pre_ping: bool = True,
    statement_timeout_ms: int = 10_000,
) -> AsyncEngine:
    """
    Create async SQLAlchemy engine.

    The engine owns the connection pool, so exactly one is created per process
    and it has to be disposed on shutdown - see CoreProvider.

    `statement_timeout_ms` is delivered as an asyncpg server setting: the stack
    is Postgres-only by design, so there is no portable-driver requirement to
    work around here.
    """
    return create_async_engine(
        url,
        echo=echo,
        echo_pool=echo_pool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_pre_ping=pool_pre_ping,
        connect_args={
            "server_settings": {"statement_timeout": str(statement_timeout_ms)},
        },
    )


def make_async_session_factory(
    engine: AsyncEngine,
    *,
    autoflush: bool = False,
    expire_on_commit: bool = False,
) -> async_sessionmaker[AsyncSession]:
    """
    Create async session factory bound to an existing engine.

    Takes the engine instead of a URL so that its lifetime is owned by the
    caller: building it in here left no handle to dispose() on shutdown.
    """
    return async_sessionmaker(
        bind=engine,
        autoflush=autoflush,
        expire_on_commit=expire_on_commit,
    )
