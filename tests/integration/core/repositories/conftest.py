"""
Repository instances for the `CRUDRepository` tests.

Kept out of `tests/integration/conftest.py` on purpose: the session ladder there
knows nothing about repositories, so a future repository suite only has to ask
for `session_manager`.
"""

import pytest

from src.core.database.session_manager import SessionManager
from tests.integration.repositories import (
    GadgetRepository,
    VehicleRepository,
    WidgetRepository,
)


@pytest.fixture
def widget_repo(session_manager: SessionManager) -> WidgetRepository:
    return WidgetRepository(session_manager)


@pytest.fixture
def gadget_repo(session_manager: SessionManager) -> GadgetRepository:
    return GadgetRepository(session_manager)


@pytest.fixture
def vehicle_repo(session_manager: SessionManager) -> VehicleRepository:
    return VehicleRepository(session_manager)
