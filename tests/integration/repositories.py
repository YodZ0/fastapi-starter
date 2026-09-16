"""
Concrete repositories over the test models.

Nothing here does any work of its own: declaring the generic arguments is the
whole point, because that is what `CRUDRepository.__init_subclass__` reads back
to build its model and schema mappings.
"""

from src.core.repositories import CRUDRepositoryInt, CRUDRepositoryUUID

from .models import (
    Car,
    CarCreateSchema,
    CarReadSchema,
    CarUpdateSchema,
    Gadget,
    GadgetCreateSchema,
    GadgetReadSchema,
    GadgetUpdateSchema,
    Truck,
    TruckCreateSchema,
    TruckReadSchema,
    TruckUpdateSchema,
    Vehicle,
    VehicleCreateSchema,
    VehicleReadSchema,
    VehicleUpdateSchema,
    Widget,
    WidgetCreateSchema,
    WidgetReadSchema,
    WidgetUpdateSchema,
)

__all__ = (
    "GadgetRepository",
    "VehicleRepository",
    "WidgetRepository",
)


class WidgetRepository(
    CRUDRepositoryInt[
        Widget,
        WidgetReadSchema,
        WidgetCreateSchema,
        WidgetUpdateSchema,
    ]
):
    search_fields = ("name", "description")


class GadgetRepository(
    CRUDRepositoryUUID[
        Gadget,
        GadgetReadSchema,
        GadgetCreateSchema,
        GadgetUpdateSchema,
    ]
):
    search_fields = ("name",)


class VehicleRepository(
    CRUDRepositoryInt[
        Vehicle,
        VehicleReadSchema,
        VehicleCreateSchema,
        VehicleUpdateSchema,
    ]
):
    # Left without `search_fields` on purpose: that is the configuration
    # `paginate(search=...)` has to refuse rather than quietly match nothing.
    __subtypes__ = (
        (Car, CarReadSchema, CarCreateSchema, CarUpdateSchema),
        (Truck, TruckReadSchema, TruckCreateSchema, TruckUpdateSchema),
    )
