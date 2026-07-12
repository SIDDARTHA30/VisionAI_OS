from abc import ABC, abstractmethod
from typing import Any, Dict
from pydantic import BaseModel


class BaseTool(ABC):
    """Abstract interface defining the blueprint for future plugin tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        pass

    @property
    @abstractmethod
    def input_schema(self) -> BaseModel:
        pass

    @property
    @abstractmethod
    def output_schema(self) -> BaseModel:
        pass

    @abstractmethod
    def validate(self, arguments: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass
