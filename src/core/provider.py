from typing import AsyncIterable

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import make_async_session_factory
from src.core.session_manager import SessionManager
from src.settings import Settings


class CoreProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        return Settings()

    # --- DATABASE ---

    @provide(scope=Scope.APP)
    def get_async_session_maker(
        self,
        settings: Settings,
    ) -> async_sessionmaker[AsyncSession]:
        return make_async_session_factory(
            url=settings.db.dsn,
            echo=settings.db.echo,
        )

    @provide
    async def get_session(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncIterable[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    @provide
    async def get_session_manager(
        self,
        session: AsyncSession,
    ) -> SessionManager:
        return SessionManager(session)
