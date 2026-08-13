from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.database import make_async_engine, make_async_session_factory
from src.core.session_manager import SessionManager
from src.settings import Settings
from src.settings import settings as app_settings


class CoreProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        # The module-level singleton, not a fresh Settings(): constructing a
        # second one re-parses .env and leaves the container holding a config
        # object that is not the one the rest of the code imports.
        return app_settings

    # --- DATABASE ---

    @provide(scope=Scope.APP)
    async def get_async_engine(
        self,
        settings: Settings,
    ) -> AsyncIterable[AsyncEngine]:
        """
        Engine holds the connection pool, so it lives for the whole application
        and is disposed on shutdown - otherwise every restart of the container
        leaves its pooled connections open on the server until they time out.

        Disposal runs when the lifespan closes the dishka container.
        """
        engine = make_async_engine(
            settings.db.url,
            echo=settings.db.echo,
            echo_pool=settings.db.echo_pool,
            pool_size=settings.db.pool_size,
            max_overflow=settings.db.max_overflow,
            pool_timeout=settings.db.pool_timeout,
            pool_recycle=settings.db.pool_recycle,
            pool_pre_ping=settings.db.pool_pre_ping,
            statement_timeout_ms=settings.db.statement_timeout_ms,
        )
        try:
            yield engine
        finally:
            await engine.dispose()

    @provide(scope=Scope.APP)
    def get_async_session_maker(
        self,
        engine: AsyncEngine,
    ) -> async_sessionmaker[AsyncSession]:
        return make_async_session_factory(engine)

    @provide
    async def get_session(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncIterable[AsyncSession]:
        async with session_factory() as session:
            yield session

    @provide
    async def get_session_manager(
        self,
        session: AsyncSession,
    ) -> SessionManager:
        return SessionManager(session)
