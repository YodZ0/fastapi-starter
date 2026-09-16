"""
Tests for the fixture machinery itself, not for any repository.

If these two pass in either order, the transaction-per-test scheme works: a
write from one test is invisible to the next, without anything being torn down
and rebuilt in between.
"""

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.session_manager import SessionManager

from .models import Widget

LEAK_SLUG = "isolation-leak-probe"


async def _count_probe_rows(session: AsyncSession) -> int:
    statement = sa.select(sa.func.count()).select_from(
        sa.select(Widget).where(Widget.slug == LEAK_SLUG).subquery()
    )
    return (await session.execute(statement)).scalar_one()


class TestTransactionIsolation:
    async def test_a_row_written_by_a_test_is_visible_to_that_test(
        self,
        session: AsyncSession,
    ) -> None:
        """
        The savepoint is not so isolating that a test cannot read its own write.
        """
        session.add(Widget(name="Probe", slug=LEAK_SLUG, weight=1))
        await session.commit()

        assert await _count_probe_rows(session) == 1

    async def test_that_row_is_gone_by_the_next_test(
        self,
        session: AsyncSession,
    ) -> None:
        """
        The companion above committed - through a savepoint - and the row still
        has to be gone, because the outer transaction was rolled back.

        Named so that it sorts after its companion, but it passes on its own
        too: the assertion is that the row is absent either way.
        """
        assert await _count_probe_rows(session) == 0

    async def test_seeded_rows_do_not_accumulate_across_tests(
        self,
        seed,
        session: AsyncSession,
    ) -> None:
        """
        `seed` runs for every test that asks for it. If its rows survived the
        rollback, this count would grow with each such test in the run.
        """
        statement = sa.select(sa.func.count()).select_from(Widget)
        assert (await session.execute(statement)).scalar_one() == len(seed.widgets)


class TestSavepointNesting:
    async def test_the_session_starts_each_test_without_an_open_transaction(
        self,
        seed,
        session: AsyncSession,
    ) -> None:
        """
        `SessionManager` only opens a savepoint when nothing is running. If the
        seed left its transaction open, every repository call would silently
        join it instead - and one integrity error would poison the whole test.
        """
        assert not session.in_transaction()

    async def test_consecutive_session_manager_blocks_see_each_other(
        self,
        seed,
        session: AsyncSession,
    ) -> None:
        """
        Savepoints have to nest inside the test's transaction, not isolate the
        calls from one another: two repository calls in a row are the normal
        case, and the second must see what the first wrote.
        """
        session_manager = SessionManager(session)

        async with session_manager.get_session() as s:
            await s.execute(
                sa.insert(Widget).values(name="Nested", slug="nested", weight=5)
            )

        async with session_manager.get_session() as s:
            statement = sa.select(Widget.name).where(Widget.slug == "nested")
            assert (await s.execute(statement)).scalar_one() == "Nested"
