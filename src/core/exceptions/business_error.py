import traceback
from abc import ABC, abstractmethod

from pydantic.alias_generators import to_snake

from src.core.schemas import BusinessLogicExceptionSchema

__all__ = ("BusinessLogicException",)


class BusinessLogicException(Exception, ABC):
    @property
    def type(self) -> str:
        """
        Error type.
        """
        return to_snake(type(self).__name__.removesuffix("Error"))

    @property
    @abstractmethod
    def msg(self) -> str:
        """
        Error message.
        """
        ...

    def __str__(self) -> str:
        return self.msg

    def get_schema(self, debug: bool) -> BusinessLogicExceptionSchema:
        """
        Get exception schema.
        """
        return BusinessLogicExceptionSchema(
            type=self.type,
            msg=self.msg,
            traceback=(
                "".join(
                    traceback.format_exception(type(self), self, self.__traceback__)
                )
                if debug
                else None
            ),
        )
