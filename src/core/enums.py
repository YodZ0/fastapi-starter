from enum import StrEnum, auto


class CascadeEnum(StrEnum):
    """
    Cascade behavior for SQLAlchemy.
    """

    ALL = "all"
    DELETE = "delete"
    DELETE_ORPHAN = "delete-orphan"
    EXPUNGE = "expunge"
    MERGE = "merge"
    REFRESH_EXPIRE = "refresh-expire"
    SAVE_UPDATE = "save-update"

    def __add__(self, value: str) -> str:
        return f"{self}, {value}"

    def __radd__(self, value: str) -> str:
        return f"{value}, {self}"


class ModelActionEnum(StrEnum):
    """
    Model actions.
    """

    INSERT = auto()
    UPDATE = auto()
    UPSERT = auto()
    DELETE = auto()

    BULK_INSERT = auto()
    BULK_UPDATE = auto()
