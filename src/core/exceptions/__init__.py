"""
Base exceptions module.
"""

from .business_error import BusinessLogicException as BusinessLogicException
from .repository import ModelIntegrityError as ModelIntegrityError
from .repository import ModelNotFoundError as ModelNotFoundError
from .repository import SortingFieldNotFoundError as SortingFieldNotFoundError
