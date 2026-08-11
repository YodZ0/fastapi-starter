from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(tz=UTC).replace(tzinfo=None)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )


class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        default=utcnow,
        server_default=func.now(),
        onupdate=utcnow,
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin, UpdatedAtMixin):
    pass
