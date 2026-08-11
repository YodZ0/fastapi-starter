from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_async_engine(
    url: str,
    *,
    echo: bool = False,
) -> AsyncEngine:
    """
    Create async SQLAlchemy engine.
    """
    return create_async_engine(
        url,
        echo=echo,
        connect_args={"server_settings": {"statement_timeout": "10000"}},
    )


def make_async_session_factory(
    url: str,
    *,
    echo: bool = False,
    autoflush: bool = False,
    autocommit: bool = False,
    expire_on_commit: bool = False,
) -> async_sessionmaker[AsyncSession]:
    """
    Create async session factory for SQLAlchemy.
    """
    async_engine = make_async_engine(url, echo=echo)
    return async_sessionmaker(
        bind=async_engine,
        autoflush=autoflush,
        autocommit=autocommit,
        expire_on_commit=expire_on_commit,
    )
