"""
Models and schemas that exist only for the integration suite.

The project ships no concrete models yet, so `CRUDRepository` has nothing to be
tested against. These stand in for them, and they are built on the real
`BaseInt` / `BaseUUID` / `TimestampMixin` on purpose: the point is to exercise
the actual `Identity(always=True)` and `gen_random_uuid()` server defaults, not
a simplified copy of them.

Table names carry a `test_` prefix so they can never collide with an
application table that later joins the same `Base.metadata`.
"""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.base_model import BaseInt, BaseUUID
from src.core.database.mixins import TimestampMixin
from src.core.schemas import (
    CreateSchemaInt,
    CreateSchemaUUID,
    ReadSchemaInt,
    ReadSchemaUUID,
    UpdateSchemaInt,
    UpdateSchemaUUID,
)

__all__ = (
    "Car",
    "CarCreateSchema",
    "CarReadSchema",
    "CarUpdateSchema",
    "Gadget",
    "GadgetCreateSchema",
    "GadgetReadSchema",
    "GadgetUpdateSchema",
    "Truck",
    "TruckCreateSchema",
    "TruckReadSchema",
    "TruckUpdateSchema",
    "Vehicle",
    "VehicleCreateSchema",
    "VehicleReadSchema",
    "VehicleUpdateSchema",
    "Widget",
    "WidgetCreateSchema",
    "WidgetReadSchema",
    "WidgetUpdateSchema",
)


# --- MODELS ---


class Widget(BaseInt, TimestampMixin):
    """
    Plain integer-keyed model: database-generated ID, timestamps, a unique
    column to trip `ModelIntegrityError`, and a nullable one for partial
    updates.
    """

    __tablename__ = "test_widgets"

    name: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    weight: Mapped[int]
    description: Mapped[str | None] = mapped_column(String(256), default=None)


class Gadget(BaseUUID):
    """
    UUID-keyed model.

    `upsert` and any other test that needs to name an ID before the row exists
    lives here: `BaseInt.id` is `GENERATED ALWAYS`, so an explicit ID in its
    INSERT is a Postgres error, while a UUID key can be chosen client-side.
    """

    __tablename__ = "test_gadgets"

    name: Mapped[str] = mapped_column(String(64))
    code: Mapped[str] = mapped_column(String(64), unique=True)


class Vehicle(BaseInt):
    """
    Base of the joined-table-inheritance hierarchy.
    """

    __tablename__ = "test_vehicles"

    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))

    # `noqa` on every `__mapper_args__` here: ruff reads a dict class attribute
    # as a mutable default, but this is simply how declarative is configured,
    # and the annotation that would quiet the rule contradicts SQLAlchemy's own
    # stubs, which declare the attribute on the instance.
    __mapper_args__ = {  # noqa: RUF012
        "polymorphic_on": "kind",
        "polymorphic_identity": "vehicle",
    }


class Car(Vehicle):
    """
    Child table of `Vehicle`.

    `id` is redeclared without `Identity`: here it is a foreign key that
    `_bulk_create_with_model` fills in explicitly from the parent INSERT, and
    `GENERATED ALWAYS` would reject exactly that.

    Inheriting directly from `Vehicle` is also load-bearing - `_get_parent_model`
    reads `__bases__[0]`.
    """

    __tablename__ = "test_cars"

    id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("test_vehicles.id"),
        primary_key=True,
    )
    doors: Mapped[int]

    __mapper_args__ = {"polymorphic_identity": "car"}  # noqa: RUF012


class Truck(Vehicle):
    """
    Second child table, so that a delete or a bulk create has to fan out over
    more than one subtype.
    """

    __tablename__ = "test_trucks"

    id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("test_vehicles.id"),
        primary_key=True,
    )
    payload_kg: Mapped[int]

    __mapper_args__ = {"polymorphic_identity": "truck"}  # noqa: RUF012


# --- SCHEMAS ---


class WidgetReadSchema(ReadSchemaInt):
    name: str
    slug: str
    weight: int
    description: str | None
    created_at: datetime
    updated_at: datetime


class WidgetCreateSchema(CreateSchemaInt):
    name: str
    slug: str
    weight: int
    description: str | None = None


class WidgetUpdateSchema(UpdateSchemaInt):
    name: str | None = None
    slug: str | None = None
    weight: int | None = None
    description: str | None = None


class GadgetReadSchema(ReadSchemaUUID):
    name: str
    code: str


class GadgetCreateSchema(CreateSchemaUUID):
    name: str
    code: str


class GadgetUpdateSchema(UpdateSchemaUUID):
    name: str | None = None
    code: str | None = None


class VehicleReadSchema(ReadSchemaInt):
    name: str
    kind: str


class VehicleCreateSchema(CreateSchemaInt):
    name: str
    # The discriminator is carried by the create schema rather than left to the
    # ORM: the repository writes the parent table with a Core INSERT built from
    # this dump, which never sees the child mapper's polymorphic identity.
    kind: str = "vehicle"


class VehicleUpdateSchema(UpdateSchemaInt):
    name: str | None = None


class CarReadSchema(VehicleReadSchema):
    doors: int


class CarCreateSchema(VehicleCreateSchema):
    kind: str = "car"
    doors: int


class CarUpdateSchema(VehicleUpdateSchema):
    doors: int | None = None


class TruckReadSchema(VehicleReadSchema):
    payload_kg: int


class TruckCreateSchema(VehicleCreateSchema):
    kind: str = "truck"
    payload_kg: int


class TruckUpdateSchema(VehicleUpdateSchema):
    payload_kg: int | None = None
