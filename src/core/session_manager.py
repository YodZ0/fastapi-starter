"""
Session and transaction management for async SQLAlchemy DB access.

Both context managers are re-entrant: if a transaction is already open,
it is reused instead of starting a nested one.
"""

from typing import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SessionManager:
    """
    Manage sessions and transactions for DB access.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def get_session(self, immediate: bool = True) -> AsyncIterator[AsyncSession]:
        """
        Get session for query execution.
        Use in low levels, for example Repository.

        Joins the current transaction if there is one, otherwise opens its own.
        """
        if self._session.in_transaction():
            yield self._session
        else:
            async with self._session.begin():
                if immediate:
                    await self._session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                yield self._session

    @asynccontextmanager
    async def transaction(self, immediate: bool = True) -> AsyncIterator[None]:
        """
        Creates global transaction.
        Use in upper levels, for example UseCase.

        Commits on exit, rolls back on error. No-op if a transaction is already open.
        """
        if self._session.in_transaction():
            yield
        else:
            async with self._session.begin():
                if immediate:
                    await self._session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                yield
